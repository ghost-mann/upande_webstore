import frappe
from frappe import _
from frappe.model.document import Document

from upande_webstore.theme import fonts


class WebstoreSettings(Document):
	def validate(self):
		# not a submittable doctype; anything other than 0 makes the desk offer
		# Cancel/Amend on what should be a plain settings form
		if self.docstatus:
			self.docstatus = 0
		self.validate_font_url()
		self.validate_occasion()
		self.apply_feature_dependencies()

	def validate_occasion(self):
		if not self.occasion:
			return
		from upande_webstore.theme import occasion

		if self.occasion not in occasion.list_names():
			frappe.throw(_("No shipped occasion named {0}.").format(self.occasion))

	def apply_feature_dependencies(self):
		# the drawer has nothing to show without a cart
		if not self.enable_cart and self.enable_cart_drawer:
			self.enable_cart_drawer = 0

	def validate_font_url(self):
		url = (self.google_fonts_url or "").strip()
		if url and not fonts.is_allowed_url(url):
			frappe.throw(
				_("Google Fonts URL must be an https link to {0}.").format(fonts.ALLOWED_FONT_HOST)
			)
		for role in ("sans", "display", "mono"):
			if self.get(f"font_{role}") == "Custom" and not self.get(f"font_{role}_name"):
				frappe.throw(_("Set a family name for the custom {0} font.").format(role))
