import frappe
from frappe import _

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_qty
from upande_webstore.theme.features import guard


def _require_login():
	if frappe.session.user in (None, "", "Guest"):
		frappe.throw(_("Please log in to use the cart."), frappe.PermissionError)


def _get_open_cart(create=False):
	from upande_webstore.services.store import current_store

	store = current_store()
	filters = {
		"user": frappe.session.user,
		"status": "Open",
		"webstore": store.name if store else "",
	}
	name = frappe.db.get_value("Webstore Cart", filters)
	if name:
		return frappe.get_doc("Webstore Cart", name)
	if not create:
		return None
	cart = frappe.get_doc({"doctype": "Webstore Cart", **filters})
	cart.insert(ignore_permissions=True)
	return cart


def _validate_stock(item_code, qty):
	# Item is not readable by Guest/Customer on newer frappe; the storefront
	# must not require exposing it, so read only the fields this needs.
	item = frappe.db.get_value("Item", item_code, ["is_stock_item", "item_name"], as_dict=True)
	if not item.is_stock_item:
		return
	available = get_stock_qty(item_code)
	if qty > available:
		frappe.throw(
			_("{0} is not available in the requested quantity.").format(item.item_name),
			frappe.ValidationError,
		)


def line_length(row, spec_map):
	"""The stem length a line is priced at: its spec's, when it has one."""
	spec = spec_map.get(row.get("specification")) if row.get("specification") else None
	return spec.price_length if spec else None


def _reprice(cart):
	"""Re-resolve every rate server-side; never trust stored/client prices."""
	spec_map = _cart_specs(cart)
	for row in cart.items:
		price = get_item_price(row.item_code, qty=row.qty, length=line_length(row, spec_map))
		row.rate = price["rate"]
		row.amount = row.rate * row.qty
		# Item is not readable by Guest/Customer on newer frappe; the storefront
		# must not require exposing it, so this reads the field directly.
		row.item_name = frappe.db.get_value("Item", row.item_code, "item_name")


def _find_row(cart, item_code, specification=None):
	"""A line is a variety under one specification, or under none: the same
	variety may sit in the cart both plain and as part of a spec."""
	specification = specification or ""
	return next(
		(
			row
			for row in cart.items
			if row.item_code == item_code and (row.get("specification") or "") == specification
		),
		None,
	)


def _cart_specs(cart):
	"""{name: spec} for the specs this cart's lines were ordered under, as the
	session customer may still order them. A spec that has since expired or
	been reassigned is simply absent, which checkout then refuses."""
	from upande_webstore.services import specs

	# checkout resolves this before building the document as Administrator,
	# who has no customer and so no specs of their own
	if cart.flags.get("webstore_spec_map") is not None:
		return cart.flags.webstore_spec_map
	names = frozenset(row.specification for row in cart.items if row.get("specification"))
	if not names or not specs.module_on():
		return {}
	# reprice, box recompute and the summary all ask within one request
	memo = cart.flags.get("webstore_spec_memo")
	if memo and memo[0] == names:
		return memo[1]
	out = {}
	for name in names:
		spec = specs.get_for_customer(name)
		if spec:
			out[name] = spec
	cart.flags.webstore_spec_memo = (names, out)
	return out


def _recompute_boxes(cart):
	"""Keep each line's box choice honest and derive its box count.

	The product supplies the default — it knows a 120cm stem needs a tall box —
	but the buyer may override it per line, so a usable existing choice is left
	alone. A spec line has no choice at all: its box is the spec's. Only the
	box *count* is never a client input, same as _reprice and rates.
	"""
	from upande_webstore.services import packing, specs

	spec_map = _cart_specs(cart)
	for row in cart.items:
		if not row.get("specification"):
			continue
		spec = spec_map.get(row.specification)
		row.box_type = spec.box_type if spec else row.box_type
		row.number_of_boxes = specs.boxes_in(spec, row.qty) if spec else 0

	if not packing.packing_enabled():
		return
	for row in cart.items:
		if row.get("specification"):
			continue
		if not row.box_type or not packing.is_usable_box(row.box_type):
			row.box_type = packing.get_product_box_type(row.item_code)
		info = packing.compute_boxes(row.qty, packing.get_pack_rate(row.box_type))
		# a line that shares a box with others has no whole-box count of its own
		row.number_of_boxes = info["boxes"] if info["pack_rate"] and info["is_full"] else 0


def packing_summary(cart):
	"""Box groups and blocking problems for a cart, or None when neither the
	packing module nor any spec line has anything to say.

	One function for the cart page and for checkout, so what the buyer is shown
	and what place_order refuses cannot disagree.
	"""
	from frappe.utils import flt

	from upande_webstore.services import packing, specs

	if not cart:
		return None
	plain = [row for row in cart.items if not row.get("specification")]
	spec_rows = [row for row in cart.items if row.get("specification")]
	on = packing.packing_enabled()
	if not on and not spec_rows:
		return None

	groups = []
	problems = []
	total_stems = sum(flt(row.qty) for row in cart.items)
	if on:
		by_box = packing.group_by_box_type(
			[{"item_code": row.item_code, "qty": row.qty, "box_type": row.box_type} for row in plain]
		)
		for g in sorted(by_box.values(), key=lambda g: (g["box_type"] or "")):
			groups.append(
				{
					"box_type": g["box_type"],
					"box_name": packing.box_label(g["box_type"]),
					"specification": None,
					"pack_rate": g["pack_rate"],
					"stems": g["stems"],
					"boxes": g["boxes"],
					"is_full": g["is_full"],
					"nearest_down": g["nearest_down"],
					"nearest_up": g["nearest_up"],
					"lines": len(g["item_codes"]),
				}
			)
		# the minimum is a whole-cart rule, so spec stems count towards it
		problems += packing.find_problems(by_box, total_stems, packing.get_minimum_order_stems())

	spec_map = _cart_specs(cart)
	by_spec = {}
	for row in spec_rows:
		by_spec.setdefault(row.specification, []).append(row)
	for name, rows in sorted(by_spec.items()):
		spec = spec_map.get(name)
		if not spec:
			problems.append(_("{0}: {1}").format(name, specs.not_available()))
			continue
		stems = sum(flt(row.qty) for row in rows)
		problems += specs.check_lines(
			spec, [{"item_code": row.item_code, "qty": row.qty} for row in rows]
		)
		boxes = sum(specs.boxes_in(spec, row.qty) for row in rows)
		groups.append(
			{
				"box_type": spec.box_type,
				"box_name": spec.box_type or _("spec box"),
				"specification": name,
				"spec_name": spec.spec_name,
				"pack_rate": spec.pack_rate,
				"stems": stems,
				"boxes": boxes,
				# unchecked fill (mixed boxes) is the packhouse's to count
				"is_full": spec.fill != specs.WHOLE_BOXES or bool(boxes),
				"checked": spec.fill == specs.WHOLE_BOXES,
				"nearest_down": None,
				"nearest_up": None,
				"lines": len(rows),
			}
		)
	return {
		"groups": groups,
		"problems": problems,
		"packable": not problems,
		"total_stems": total_stems,
		"total_boxes": sum(g["boxes"] for g in groups if g["pack_rate"]),
	}


def _box_view(cart):
	"""Box summary for the cart page, or None when there is nothing to show."""
	return packing_summary(cart)


def serialize_cart(cart):
	from upande_webstore.services import packing

	if not cart:
		return {
			"name": None,
			"items": [],
			"total": 0,
			"currency": None,
			"count": 0,
			"boxes": None,
		}
	from upande_webstore.services.pricing import get_price_list

	product_map = {}
	item_codes = [row.item_code for row in cart.items]
	if item_codes:
		for p in frappe.get_all(
			"Webstore Product",
			filters={"item": ["in", item_codes]},
			fields=["item", "web_title", "route"],
		):
			product_map[p.item] = p
	return {
		"name": cart.name,
		"items": [
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"web_title": product_map.get(row.item_code, {}).get("web_title") or row.item_name,
				"route": product_map.get(row.item_code, {}).get("route"),
				"qty": row.qty,
				"rate": row.rate,
				"amount": row.amount,
				"specification": row.get("specification") or None,
				"box_type": row.get("box_type"),
				"box_name": (
					row.box_type
					if row.get("specification")
					else packing.box_label(row.box_type) if row.get("box_type") else None
				),
				# a spec line's box is the spec's; the buyer cannot change it
				"box_fixed": bool(row.get("specification")),
				"number_of_boxes": row.get("number_of_boxes") or 0,
			}
			for row in cart.items
		],
		"total": cart.total,
		"currency": frappe.db.get_value("Price List", get_price_list(), "currency"),
		"count": int(sum(row.qty for row in cart.items)),
		"boxes": _box_view(cart),
	}


@frappe.whitelist()
@guard("cart")
def get_cart():
	_require_login()
	cart = _get_open_cart()
	if cart:
		_reprice(cart)
		_recompute_boxes(cart)
		cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
@guard("cart")
def get_cart_count():
	_require_login()
	cart = _get_open_cart()
	return int(sum(row.qty for row in cart.items)) if cart else 0


@frappe.whitelist()
@guard("cart")
def add_item(item_code, qty=1):
	_require_login()
	qty = frappe.utils.flt(qty) or 1
	if qty <= 0:
		frappe.throw(_("Quantity must be positive."), frappe.ValidationError)
	product = frappe.db.get_value("Webstore Product", {"item": item_code, "published": 1})
	if not product:
		frappe.throw(_("This product is not available."), frappe.ValidationError)
	# Same message as an unpublished product on purpose: which shops carry
	# which lines is not something an unauthenticated probe should be able to
	# map by watching the error change.
	from upande_webstore.services.catalog import is_in_current_store

	if not is_in_current_store(product):
		frappe.throw(_("This product is not available."), frappe.ValidationError)
	cart = _get_open_cart(create=True)
	existing = _find_row(cart, item_code)
	new_qty = (existing.qty if existing else 0) + qty
	_validate_stock(item_code, new_qty)
	if existing:
		existing.qty = new_qty
	else:
		cart.append("items", {"item_code": item_code, "qty": qty})
	_reprice(cart)
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
@guard("cart")
def update_qty(item_code, qty, specification=None):
	_require_login()
	qty = frappe.utils.flt(qty)
	if qty <= 0:
		return remove_item(item_code, specification)
	cart = _get_open_cart()
	if not cart:
		frappe.throw(_("Cart is empty."), frappe.ValidationError)
	row = _find_row(cart, item_code, specification)
	if not row:
		frappe.throw(_("Item not in cart."), frappe.ValidationError)
	_validate_stock(item_code, qty)
	row.qty = qty
	_reprice(cart)
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
@guard("cart")
def remove_item(item_code, specification=None):
	_require_login()
	cart = _get_open_cart()
	if not cart:
		return serialize_cart(None)
	gone = _find_row(cart, item_code, specification)
	cart.items = [r for r in cart.items if r is not gone]
	_reprice(cart)
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
@guard("cart")
def get_box_types():
	from upande_webstore.services.packing import get_box_types as _box_types

	return _box_types()


@frappe.whitelist()
@guard("cart")
def set_box_type(item_code, box_type, specification=None):
	"""Override one line's box. Blank falls back to the product's own box."""
	from upande_webstore.services import packing

	_require_login()
	cart = _get_open_cart()
	if not cart:
		frappe.throw(_("Cart is empty."), frappe.ValidationError)
	row = _find_row(cart, item_code, specification)
	if not row:
		frappe.throw(_("Item not in cart."), frappe.ValidationError)
	if row.get("specification"):
		frappe.throw(
			_("This line ships in its specification's box, which cannot be changed."),
			frappe.ValidationError,
		)
	if box_type and not packing.is_usable_box(box_type):
		frappe.throw(_("That box type is not available."), frappe.ValidationError)
	row.box_type = box_type or None
	_reprice(cart)
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)
