import frappe

from upande_webstore.services.catalog import get_categories, get_products

PAGE_LENGTH = 12


def get_context(context):
	context.no_cache = 1
	search = frappe.form_dict.get("q") or None
	category = frappe.form_dict.get("category") or None
	page = max(frappe.utils.cint(frappe.form_dict.get("page")) or 1, 1)
	result = get_products(
		search=search, category=category, start=(page - 1) * PAGE_LENGTH, page_length=PAGE_LENGTH
	)
	context.products = result["products"]
	context.total = result["total"]
	context.page = page
	context.total_pages = max((result["total"] + PAGE_LENGTH - 1) // PAGE_LENGTH, 1)
	context.search = search or ""
	context.category = category or ""
	context.categories = get_categories()
	context.featured = (
		get_products(featured_only=True, page_length=4)["products"]
		if not search and not category and page == 1
		else []
	)
	return context
