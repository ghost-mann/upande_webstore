import frappe

from upande_webstore.services.catalog import get_categories, get_products
from upande_webstore.services.store import current_store_or_404

PAGE_LENGTH = 12


def get_context(context):
	context.no_cache = 1
	# An explicit /<slug>/store must 404 for an unknown or unpublished slug
	# rather than silently showing the default store's catalogue.
	current_store_or_404()
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
	_spec_context(context)
	return context


def _spec_context(context):
	"""The My specifications switch, for a signed-in customer who has specs.

	Nothing is read unless the module is on, the cart is, and the visitor is a
	customer — guests and customers without specs get the store unchanged.
	"""
	from upande_webstore.services import specs
	from upande_webstore.services.pricing import get_customer
	from upande_webstore.theme.features import enabled

	context.spec_count = 0
	context.view = "products"
	context.specs = []
	flags = enabled()
	if not (flags.customer_specs and flags.cart) or frappe.session.user == "Guest":
		return
	if not specs.availability()[0]:
		return
	customer = get_customer()
	if not customer:
		return
	context.spec_count = specs.count_for(customer)
	if context.spec_count and frappe.form_dict.get("view") == "specs":
		context.view = "specs"
		context.specs = specs.my_specs(customer)
