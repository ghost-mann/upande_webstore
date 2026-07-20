import frappe
from frappe import _

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_qty


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


def serialize_cart(cart):
	if not cart:
		return {"name": None, "items": [], "total": 0, "currency": None, "count": 0}
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
			}
			for row in cart.items
		],
		"total": cart.total,
		"currency": frappe.db.get_value("Price List", get_price_list(), "currency"),
		"count": int(sum(row.qty for row in cart.items)),
	}


@frappe.whitelist()
def get_cart():
	_require_login()
	cart = _get_open_cart()
	if cart:
		_reprice(cart)
		cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
def get_cart_count():
	_require_login()
	cart = _get_open_cart()
	return int(sum(row.qty for row in cart.items)) if cart else 0


@frappe.whitelist()
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
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
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
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
def remove_item(item_code):
	_require_login()
	cart = _get_open_cart()
	if not cart:
		return serialize_cart(None)
	cart.items = [r for r in cart.items if r.item_code != item_code]
	_reprice(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)
