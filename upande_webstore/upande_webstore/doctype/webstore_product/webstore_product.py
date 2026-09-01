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
		self.validate_box_type()

	def validate_box_type(self):
		"""A box that is not a box would silently fall back to the farm default,
		which looks like the setting being ignored. Say so, and name where box
		types come from on this site — it differs per farm."""
		from frappe import _

		if not self.box_type:
			return
		from upande_webstore.services.packing import box_source_hint, is_usable_box

		if not is_usable_box(self.box_type):
			frappe.throw(
				_("{0} is not a usable box type on this site. {1}").format(
					self.box_type, box_source_hint()
				),
				frappe.ValidationError,
			)

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
			from upande_webstore.services.pricing import get_variant_price_range

			context.attributes = get_attributes(self.item)
			context.price = None
			context.stock = None
			# so the page is not priceless before a length is chosen
			context.price_range = get_variant_price_range(self.item)
		else:
			context.attributes = []
			context.price_range = None
			context.price = get_item_price(self.item)
			context.stock = get_stock_info(self.item)
		return context
