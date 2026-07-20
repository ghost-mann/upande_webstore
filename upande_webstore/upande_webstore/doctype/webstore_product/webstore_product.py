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
		context.no_cache = 1
		context.item_doc = frappe.get_doc("Item", self.item)
		return context
