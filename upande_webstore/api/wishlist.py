import frappe
from frappe import _
from frappe.utils import nowdate

from upande_webstore.api.cart import _require_login
from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_info


def _get_wishlist(create=False):
	name = frappe.db.get_value("Webstore Wishlist", {"user": frappe.session.user})
	if name:
		return frappe.get_doc("Webstore Wishlist", name)
	if not create:
		return None
	doc = frappe.get_doc({"doctype": "Webstore Wishlist", "user": frappe.session.user})
	doc.insert(ignore_permissions=True)
	return doc


@frappe.whitelist()
def toggle(product):
	_require_login()
	if not frappe.db.exists("Webstore Product", product):
		frappe.throw(_("Product not found."), frappe.ValidationError)
	doc = _get_wishlist(create=True)
	existing = next((row for row in doc.items if row.product == product), None)
	if existing:
		doc.items = [row for row in doc.items if row.product != product]
		wishlisted = False
	else:
		doc.append("items", {"product": product, "added_on": nowdate()})
		wishlisted = True
	doc.save(ignore_permissions=True)
	return {"wishlisted": wishlisted, "count": len(doc.items)}


@frappe.whitelist()
def get_wishlisted_products():
	_require_login()
	doc = _get_wishlist()
	return [row.product for row in doc.items] if doc else []


@frappe.whitelist()
def get_wishlist():
	_require_login()
	doc = _get_wishlist()
	if not doc:
		return {"items": [], "count": 0}
	items = []
	for row in doc.items:
		product = frappe.db.get_value(
			"Webstore Product",
			row.product,
			["name", "web_title", "route", "image", "item", "published"],
			as_dict=True,
		)
		if not product or not product.published:
			continue
		item_doc = frappe.get_cached_doc("Item", product.item)
		items.append({
			"product": product.name,
			"web_title": product.web_title,
			"route": product.route,
			"image": product.image,
			"item_code": product.item,
			"has_variants": item_doc.has_variants,
			"price": None if item_doc.has_variants else get_item_price(product.item),
			"stock": None if item_doc.has_variants else get_stock_info(product.item),
		})
	return {"items": items, "count": len(items)}
