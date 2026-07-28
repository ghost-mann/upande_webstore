import frappe
from frappe.website.website_generator import WebsiteGenerator


class WebstoreProduct(WebsiteGenerator):
	website = frappe._dict(
		page_title_field="web_title",
		condition_field="published",
		template="templates/generators/webstore_product.html",
	)

	def make_route(self):
		return "store/" + self.scrub(self.web_title)

	def validate(self):
		super().validate()
		if not self.image:
			self.image = frappe.db.get_value("Item", self.item, "image")

	def get_context(self, context):
		from upande_webstore.api.variants import get_attributes
		from upande_webstore.services.pricing import get_item_price
		from upande_webstore.services.stock import get_stock_info

		context.no_cache = 1
		item_doc = frappe.get_cached_doc("Item", self.item)
		context.item_doc = item_doc
		# a photo set on the Item counts as the product photo
		context.image = self.image or item_doc.image
		context.is_template = bool(item_doc.has_variants)
		if context.is_template:
			context.attributes = get_attributes(self.item)
			context.price = None
			context.stock = None
		else:
			context.attributes = []
			context.price = get_item_price(self.item)
			context.stock = get_stock_info(self.item)
		return context
