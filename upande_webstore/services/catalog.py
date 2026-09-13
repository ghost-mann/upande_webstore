import frappe

from upande_webstore.services.pricing import get_item_price, get_variant_price_range
from upande_webstore.services.stock import get_stock_info


def _store_product_names(store):
	"""Every `Webstore Product` name visible in `store` (a slug).

	Membership is the `stores` child table when it has any rows at all - a
	product listed under several storefronts. An empty table falls back to
	the product's own `primary_store` (blank meaning the default store), so
	an unscoped product still shows in exactly the one catalogue it always
	has - its own, never nothing and never every store at once.
	"""
	from upande_webstore.services.store import DEFAULT_SLUG

	explicit = frappe.get_all("Webstore Product Store", filters={"webstore": store}, pluck="parent")
	assigned = frappe.get_all("Webstore Product Store", pluck="parent", distinct=True)

	filters = {"name": ["not in", assigned]} if assigned else {}
	filters["primary_store"] = ["in", ("", store)] if store == DEFAULT_SLUG else store
	implicit = frappe.get_all("Webstore Product", filters=filters, pluck="name")

	return list(set(explicit) | set(implicit))


def _apply_store_filter(filters):
	"""Narrow `filters` (a dict of Webstore Product filters, mutated in
	place) to the resolved store's catalogue - or leave it untouched when no
	store resolves at all, which is what keeps a site with no `Webstore` row
	yet (before Task 1's patch has ever run) showing every product exactly
	as it did before this feature existed."""
	from upande_webstore.services.store import current_store

	store = current_store()
	if store:
		filters["name"] = ["in", _store_product_names(store.name)]
	return filters


def is_in_current_store(product):
	"""Is this `Webstore Product` (by name) part of the resolved store's
	catalogue?

	The listing pages filter the catalogue, but a cart or wishlist call names
	a product directly, so without this a crafted request could put a dairy
	product into the flower store's cart — the listing would hide it and the
	cart would still carry it into a Sales Order stamped with the wrong shop.
	Answered per product rather than by reusing _store_product_names, which
	pulls the whole catalogue back to compare one name against it.
	"""
	from upande_webstore.services.store import DEFAULT_SLUG, current_store

	store = current_store()
	if not store:
		# No store resolved at all (a site whose patch has never run): the
		# catalogue is unfiltered, so nothing is out of store either.
		return True
	rows = frappe.get_all("Webstore Product Store", filters={"parent": product}, pluck="webstore")
	if rows:
		return store.name in rows
	primary = frappe.db.get_value("Webstore Product", product, "primary_store") or DEFAULT_SLUG
	return primary == store.name


def get_products(search=None, category=None, featured_only=False, start=0, page_length=12):
	filters = _apply_store_filter({"published": 1})
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

	categories = frappe.get_all(
		"Webstore Product", filters=_apply_store_filter({"published": 1}), pluck="category"
	)
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
