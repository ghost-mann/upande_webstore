import frappe

from upande_webstore.services.pricing import get_item_price
from upande_webstore.services.stock import get_stock_info


def get_products(search=None, category=None, featured_only=False, start=0, page_length=12):
	filters = {"published": 1}
	if category:
		filters["category"] = category
	if featured_only:
		filters["featured"] = 1
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = [
			["web_title", "like", like],
			["short_description", "like", like],
			["item", "like", like],
		]
	fields = ["name", "web_title", "route", "image", "short_description", "item", "category", "featured"]
	products = frappe.get_all(
		"Webstore Product",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="featured desc, web_title asc",
		start=start,
		page_length=page_length,
	)
	if search:
		total = len(
			frappe.get_all("Webstore Product", filters=filters, or_filters=or_filters, pluck="name")
		)
	else:
		total = frappe.db.count("Webstore Product", filters)
	for product in products:
		has_variants = frappe.get_cached_value("Item", product["item"], "has_variants")
		product["has_variants"] = has_variants
		product["price"] = None if has_variants else get_item_price(product["item"])
		product["stock"] = None if has_variants else get_stock_info(product["item"])
	return {"products": products, "total": total}


def get_categories():
	from collections import Counter

	categories = frappe.get_all("Webstore Product", filters={"published": 1}, pluck="category")
	counts = Counter(c for c in categories if c)
	return [{"name": name, "count": count} for name, count in sorted(counts.items())]
