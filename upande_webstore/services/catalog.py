import frappe

from upande_webstore.services.pricing import get_item_price, get_variant_price_range
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
		# Item is not readable by Guest on newer frappe; the storefront must not
		# require exposing it, so read the two fields directly rather than via
		# a permission-checked cached document (one query instead of two).
		item_fields = frappe.db.get_value(
			"Item", product["item"], ["has_variants", "image"], as_dict=True
		) or {}
		has_variants = item_fields.get("has_variants")
		product["has_variants"] = has_variants
		# most people attach the photo to the Item in ERPNext, so use that when
		# the listing has none of its own
		if not product.get("image"):
			product["image"] = item_fields.get("image")
		product["price"] = None if has_variants else get_item_price(product["item"])
		# a template has no price of its own; show the range across its variants
		product["price_range"] = (
			get_variant_price_range(product["item"]) if has_variants else None
		)
		product["stock"] = None if has_variants else get_stock_info(product["item"])
	return {"products": products, "total": total}


def get_categories():
	"""The storefront's category filter list.

	A farm's curated `categories` table on Webstore Settings wins once it has
	rows: table order (operators drag rows to reorder), published rows only,
	`label` for display when set else the Item Group's own name. Empty table
	falls back to deriving the list from published products, alphabetically,
	exactly as before this table existed — so the feature is inert until an
	operator configures it.

	Every entry carries both `value` (the Item Group name stored on
	Webstore Product.category — what /store?category= must keep matching, so
	a display rename never breaks a bookmark or the filter itself) and
	`label` (what the storefront prints).
	"""
	from collections import Counter

	from upande_webstore.services.settings import get_settings

	categories = frappe.get_all("Webstore Product", filters={"published": 1}, pluck="category")
	counts = Counter(c for c in categories if c)

	configured = get_settings().get("categories") or []
	if configured:
		entries = []
		for row in configured:
			if not row.published:
				continue
			count = counts.get(row.item_group, 0)
			if not count:
				# a configured category with no published products behind it
				# would just be a link to an empty page
				continue
			entries.append(
				{"value": row.item_group, "label": row.label or row.item_group, "count": count}
			)
		return entries

	return [{"value": name, "label": name, "count": count} for name, count in sorted(counts.items())]
