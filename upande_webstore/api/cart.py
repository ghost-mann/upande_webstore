import frappe
from frappe import _

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_qty
from upande_webstore.theme.features import guard


def _require_login():
	if frappe.session.user in (None, "", "Guest"):
		frappe.throw(_("Please log in to use the cart."), frappe.PermissionError)


def _get_open_cart(create=False):
	name = frappe.db.get_value(
		"Webstore Cart", {"user": frappe.session.user, "status": "Open"}
	)
	if name:
		return frappe.get_doc("Webstore Cart", name)
	if not create:
		return None
	cart = frappe.get_doc({"doctype": "Webstore Cart", "user": frappe.session.user, "status": "Open"})
	cart.insert(ignore_permissions=True)
	return cart


def _validate_stock(item_code, qty):
	item = frappe.get_cached_doc("Item", item_code)
	if not item.is_stock_item:
		return
	available = get_stock_qty(item_code)
	if qty > available:
		frappe.throw(
			_("{0} is not available in the requested quantity.").format(item.item_name),
			frappe.ValidationError,
		)


def _reprice(cart):
	"""Re-resolve every rate server-side; never trust stored/client prices."""
	for row in cart.items:
		price = get_item_price(row.item_code, qty=row.qty)
		row.rate = price["rate"]
		row.amount = row.rate * row.qty
		row.item_name = frappe.get_cached_value("Item", row.item_code, "item_name")


def _recompute_boxes(cart):
	"""Keep each line's box choice honest and derive its box count.

	The product supplies the default — it knows a 120cm stem needs a tall box —
	but the buyer may override it per line, so a usable existing choice is left
	alone. Only the box *count* is never a client input, same as _reprice and
	rates.
	"""
	from upande_webstore.services import packing

	if not packing.packing_enabled():
		return
	for row in cart.items:
		if not row.box_type or not packing.is_usable_box(row.box_type):
			row.box_type = packing.get_product_box_type(row.item_code)
		info = packing.compute_boxes(row.qty, packing.get_pack_rate(row.box_type))
		# a line that shares a box with others has no whole-box count of its own
		row.number_of_boxes = info["boxes"] if info["pack_rate"] and info["is_full"] else 0


def _box_view(cart):
	"""Box summary for the cart page, or None when packing is off."""
	from upande_webstore.services import packing

	if not cart or not packing.packing_enabled():
		return None
	total_stems = sum(frappe.utils.flt(row.qty) for row in cart.items)
	groups = packing.group_by_box_type(
		[{"item_code": row.item_code, "qty": row.qty, "box_type": row.box_type} for row in cart.items]
	)
	problems = packing.find_problems(
		groups, total_stems, packing.get_minimum_order_stems()
	)
	return {
		"groups": [
			{
				"box_type": g["box_type"],
				"box_name": packing.box_label(g["box_type"]),
				"pack_rate": g["pack_rate"],
				"stems": g["stems"],
				"boxes": g["boxes"],
				"is_full": g["is_full"],
				"nearest_down": g["nearest_down"],
				"nearest_up": g["nearest_up"],
				"lines": len(g["item_codes"]),
			}
			for g in sorted(groups.values(), key=lambda g: (g["box_type"] or ""))
		],
		"problems": problems,
		"packable": not problems,
		"total_stems": total_stems,
	}


def serialize_cart(cart):
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
				"box_type": row.get("box_type"),
				"box_name": (
					frappe.db.get_value("Item", row.box_type, "item_name") or row.box_type
					if row.get("box_type") else None
				),
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
	if not frappe.db.get_value("Webstore Product", {"item": item_code, "published": 1}):
		frappe.throw(_("This product is not available."), frappe.ValidationError)
	cart = _get_open_cart(create=True)
	existing = next((row for row in cart.items if row.item_code == item_code), None)
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
def update_qty(item_code, qty):
	_require_login()
	qty = frappe.utils.flt(qty)
	if qty <= 0:
		return remove_item(item_code)
	cart = _get_open_cart()
	if not cart:
		frappe.throw(_("Cart is empty."), frappe.ValidationError)
	row = next((r for r in cart.items if r.item_code == item_code), None)
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
def remove_item(item_code):
	_require_login()
	cart = _get_open_cart()
	if not cart:
		return serialize_cart(None)
	cart.items = [r for r in cart.items if r.item_code != item_code]
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
def set_box_type(item_code, box_type):
	"""Override one line's box. Blank falls back to the product's own box."""
	from upande_webstore.services import packing

	_require_login()
	cart = _get_open_cart()
	if not cart:
		frappe.throw(_("Cart is empty."), frappe.ValidationError)
	row = next((r for r in cart.items if r.item_code == item_code), None)
	if not row:
		frappe.throw(_("Item not in cart."), frappe.ValidationError)
	if box_type and not packing.is_usable_box(box_type):
		frappe.throw(_("That box type is not available."), frappe.ValidationError)
	row.box_type = box_type or None
	_reprice(cart)
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)
