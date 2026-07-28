import frappe
from frappe import _
from frappe.utils import add_days, flt, get_url_to_form, nowdate

from upande_webstore.api.cart import _get_open_cart, _require_login
from upande_webstore.services.pricing import get_customer, get_item_price, get_price_list
from upande_webstore.services.settings import get_settings
from upande_webstore.services.stock import get_stock_qty
from upande_webstore.theme.features import guard


@frappe.whitelist(methods=["POST"])
@guard("cart")
def place_order(address_name=None, po_reference=None, notes=None):
	_require_login()
	customer = get_customer()
	if not customer:
		frappe.throw(_("Your account is not linked to a customer. Please contact us."), frappe.ValidationError)
	cart = _get_open_cart()
	if not cart or not cart.items:
		frappe.throw(_("Your cart is empty."), frappe.ValidationError)

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

	settings = get_settings()
	price_list = get_price_list()
	contact_name = frappe.db.get_value("Contact", {"user": frappe.session.user}, "name")

	# All inputs above are resolved from the session user; the quotation itself
	# is system-constructed, so create it under elevated context (ERPNext's
	# account permission check has no bypass flag for website users).
	session_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		quotation = _create_quotation(cart, customer, settings, price_list, contact_name, address_name, po_reference, notes)
	finally:
		frappe.set_user(session_user)

	cart.status = "Ordered"
	cart.quotation = quotation.name
	cart.save(ignore_permissions=True)

	_notify_sales_team(quotation)
	return {"quotation": quotation.name}


def _create_quotation(cart, customer, settings, price_list, contact_name, address_name, po_reference, notes):
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
		"items": [
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"rate": get_item_price(row.item_code, qty=row.qty)["rate"],
			}
			for row in cart.items
		],
	})
	quotation.flags.ignore_permissions = True
	quotation.insert()
	quotation.submit()
	return quotation


def _notify_sales_team(quotation):
	settings = get_settings()
	recipients = [e.strip() for e in (settings.notification_emails or "").split(",") if e.strip()]
	if not recipients:
		return
	frappe.sendmail(
		recipients=recipients,
		subject=_("New webstore quotation {0} from {1}").format(quotation.name, quotation.party_name),
		message=_("A new quotation request was placed on the webstore.<br>Review it here: {0}").format(
			get_url_to_form("Quotation", quotation.name)
		),
	)
