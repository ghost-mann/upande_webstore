import frappe
from frappe import _
from frappe.utils import add_days, flt, formatdate, get_url_to_form, getdate, nowdate

from upande_webstore.api.cart import _get_open_cart, _recompute_boxes, _require_login
from upande_webstore.services import dropoff
from upande_webstore.services.pricing import get_customer, get_item_price, get_price_list
from upande_webstore.services.settings import get_settings
from upande_webstore.services.stock import get_source_warehouse, get_stock_qty
from upande_webstore.theme.features import enabled, guard

QUOTATION = "quotation"
ORDER = "order"
MODES = (QUOTATION, ORDER)

# Sales Order requires a delivery date. The webstore has no per-item lead times,
# so it books a nominal week out; the sales team adjusts on confirmation.
DEFAULT_DELIVERY_DAYS = 7


@frappe.whitelist(methods=["POST"])
@guard("cart")
def place_order(
	address_name=None,
	po_reference=None,
	notes=None,
	mode=QUOTATION,
	shipping_date=None,
	dropoff_points=None,
	delivery_point=None,
	box_type=None,
):
	"""Turn the open cart into a Quotation (price confirmation first) or a
	Sales Order (commit now). Sales Orders are left as drafts for the sales
	team to confirm."""
	mode = (mode or QUOTATION).strip().lower()
	if mode not in MODES:
		frappe.throw(_("Unknown checkout mode {0}.").format(mode), frappe.ValidationError)
	if mode == ORDER and not enabled()["direct_order"]:
		frappe.throw(_("Direct ordering is not enabled."), frappe.PermissionError)

	_require_login()
	customer = get_customer()
	if not customer:
		frappe.throw(_("Your account is not linked to a customer. Please contact us."), frappe.ValidationError)
	cart = _get_open_cart()
	if not cart or not cart.items:
		frappe.throw(_("Your cart is empty."), frappe.ValidationError)

	_apply_box_type(cart, box_type)
	_assert_available(cart)
	_assert_packable(cart)
	_assert_shipping_date(shipping_date)

	settings = get_settings()
	price_list = get_price_list()
	contact_name = frappe.db.get_value("Contact", {"user": frappe.session.user}, "name")

	# All inputs above are resolved from the session user; the document itself
	# is system-constructed, so create it under elevated context (ERPNext's
	# account permission check has no bypass flag for website users).
	build = _create_sales_order if mode == ORDER else _create_quotation
	session_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		doc = build(
			cart, customer, settings, price_list, contact_name, address_name,
			po_reference, notes, shipping_date, dropoff_points, delivery_point,
		)
	finally:
		frappe.set_user(session_user)

	cart.status = "Ordered"
	if mode == ORDER:
		cart.sales_order = doc.name
	else:
		cart.quotation = doc.name
	cart.save(ignore_permissions=True)

	_notify_sales_team(doc)

	result = {"doctype": doc.doctype, "name": doc.name}
	# legacy key, kept so existing callers keep working
	result["sales_order" if mode == ORDER else "quotation"] = doc.name
	return result


def _assert_available(cart):
	unavailable = []
	for row in cart.items:
		item = frappe.get_cached_doc("Item", row.item_code)
		if item.is_stock_item and flt(row.qty) > get_stock_qty(row.item_code):
			unavailable.append(item.item_name)
	if unavailable:
		frappe.throw(
			_("These items are no longer available in the requested quantity: {0}. Please adjust your cart.").format(", ".join(unavailable)),
			frappe.ValidationError,
		)


def _apply_box_type(cart, box_type):
	"""The box chosen in the checkout form wins.

	One box type per order, so this lands on the cart rather than per line. The
	cart may already carry a choice made earlier on the basket page; a value
	posted with the order overrides it.
	"""
	from upande_webstore.services import packing

	if not packing.packing_enabled():
		return
	if box_type:
		if not packing.is_usable_box(box_type):
			frappe.throw(_("That box type is not available."), frappe.ValidationError)
		cart.box_type = box_type
	if not cart.box_type or not packing.is_usable_box(cart.box_type):
		cart.box_type = packing.get_default_box_type() or None
	# the per-line box counts were derived against whatever box was set before,
	# so they have to be re-derived against this one
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)


def _assert_packable(cart):
	"""Whole-box fill per box-type group, and the order minimum.

	Inert unless the farm has switched packing on AND entered pack rates, so
	this cannot break a site that has done neither.
	"""
	from upande_webstore.services import packing

	if not packing.packing_enabled():
		return
	groups = packing.group_by_box_type(
		[{"item_code": row.item_code, "qty": row.qty, "box_type": cart.box_type} for row in cart.items]
	)
	total_stems = sum(flt(row.qty) for row in cart.items)
	problems = packing.find_problems(
		groups, total_stems, packing.get_minimum_order_stems()
	)
	if problems:
		frappe.throw("<br>".join(problems), frappe.ValidationError)


def _earliest_delivery_date():
	"""Today plus the farm's lead time, falling back to the shipped default so a
	site that has never set it behaves as before."""
	from upande_webstore.services.settings import get_settings

	lead_days = int(flt(get_settings().get("default_lead_days"))) or DEFAULT_DELIVERY_DAYS
	return add_days(nowdate(), lead_days)


def _assert_shipping_date(shipping_date):
	"""Reject a requested date the farm cannot ship.

	The cart's date input carries a min= attribute, but that is client-side only;
	this is the check that actually holds. A past date is necessarily inside the
	lead window, so one comparison covers both.

	Deliberately does not substitute a default: webstore_shipping_date records
	what the buyer asked for, and stamping a derived date into it would claim a
	request they never made.
	"""
	if not shipping_date:
		return
	earliest = _earliest_delivery_date()
	if getdate(shipping_date) < getdate(earliest):
		frappe.throw(
			_("The earliest shipping date we can accept is {0}.").format(
				formatdate(earliest)
			),
			frappe.ValidationError,
		)


def _store_delivery_point(doc, delivery_point):
	"""Written after insert, and only where it can be stored.

	The field is another app's, and on Mona live it Links to a Delivery Point
	doctype that is not installed — writing to it there would fail validation.
	"""
	stored = dropoff.resolve(delivery_point)
	if stored and _present(doc.doctype, "custom_delivery_point"):
		doc.db_set("custom_delivery_point", stored)


def _present(doctype, fieldname):
	return bool(frappe.get_meta(doctype).get_field(fieldname))


def _cart_items(cart):
	from upande_webstore.services import packing

	include_boxes = packing.packing_enabled()
	rows = []
	for row in cart.items:
		line = {
			"item_code": row.item_code,
			"qty": row.qty,
			"rate": get_item_price(row.item_code, qty=row.qty)["rate"],
		}
		if include_boxes and cart.box_type:
			line["custom_box_type"] = cart.box_type
			line["custom_pack_rate"] = packing.get_pack_rate(cart.box_type)
			# a line sharing a mixed box has no whole-box count of its own
			line["custom_number_of_boxes"] = row.number_of_boxes or 0
		rows.append(line)
	return rows


def _has_mixed_boxes(cart):
	"""True when some line has to share a box with another.

	A line whose quantity is a whole number of boxes packs on its own; anything
	else must share, which is what tells the desk this order needs mixed-box
	handling. Two lines of 600 at 300/box are not mixed; 150 + 150 are.
	"""
	from upande_webstore.services import packing

	if not packing.packing_enabled():
		return 0
	pack_rate = packing.get_pack_rate(cart.box_type)
	if not pack_rate or len(cart.items) < 2:
		return 0
	return int(any(flt(row.qty) % pack_rate for row in cart.items))


def _create_quotation(
	cart, customer, settings, price_list, contact_name, address_name,
	po_reference, notes, shipping_date=None, dropoff_points=None,
	delivery_point=None,
):
	quotation = frappe.get_doc({
		"doctype": "Quotation",
		"quotation_to": "Customer",
		"party_name": customer,
		"order_type": "Shopping Cart",
		"company": settings.company,
		"selling_price_list": price_list,
		"valid_till": add_days(nowdate(), settings.quotation_validity_days or 14),
		"contact_person": contact_name,
		"customer_address": address_name,
		"shipping_address_name": address_name,
		"customer_po_reference": po_reference,
		"webstore_notes": notes,
		"webstore_shipping_date": shipping_date or None,
		"webstore_dropoff_points": dropoff_points or None,
		"items": _cart_items(cart),
	})
	quotation.flags.ignore_permissions = True
	quotation.insert()
	quotation.submit()
	_store_delivery_point(quotation, delivery_point)
	return quotation


def _create_sales_order(
	cart, customer, settings, price_list, contact_name, address_name,
	po_reference, notes, shipping_date=None, dropoff_points=None,
	delivery_point=None,
):
	"""Left as a draft on purpose: the customer has committed, but the sales
	team confirms freight and stock before it is submitted."""
	# the customer's requested shipping date is the Sales Order's delivery date,
	# which is what ERPNext plans and picks against
	# validated in place_order; falls back to the farm's lead time
	delivery_date = shipping_date or _earliest_delivery_date()
	order = frappe.get_doc({
		"doctype": "Sales Order",
		"customer": customer,
		"order_type": "Shopping Cart",
		"company": settings.company,
		"selling_price_list": price_list,
		"transaction_date": nowdate(),
		"delivery_date": delivery_date,
		"contact_person": contact_name,
		"customer_address": address_name,
		"shipping_address_name": address_name,
		# Sales Order has its own standard field for the customer's PO
		"po_no": po_reference,
		"webstore_notes": notes,
		"webstore_dropoff_points": dropoff_points or None,
		"custom_has_mixed_boxes": _has_mixed_boxes(cart),
		# Sales Order needs a warehouse per stock item; availability is summed
		# across the configured webstore warehouses, so name the one holding it.
		"items": [
			dict(row, delivery_date=delivery_date, warehouse=get_source_warehouse(row["item_code"]))
			for row in _cart_items(cart)
		],
	})
	order.flags.ignore_permissions = True
	order.insert()
	_store_delivery_point(order, delivery_point)
	return order


def _notify_sales_team(doc):
	settings = get_settings()
	recipients = [e.strip() for e in (settings.notification_emails or "").split(",") if e.strip()]
	if not recipients:
		return
	party = doc.get("party_name") or doc.get("customer")
	if doc.doctype == "Sales Order":
		subject = _("New webstore order {0} from {1}").format(doc.name, party)
		body = _("A customer placed an order directly on the webstore. It is a draft awaiting your confirmation.<br>Review it here: {0}")
	else:
		subject = _("New webstore quotation {0} from {1}").format(doc.name, party)
		body = _("A new quotation request was placed on the webstore.<br>Review it here: {0}")
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=body.format(get_url_to_form(doc.doctype, doc.name)),
	)
