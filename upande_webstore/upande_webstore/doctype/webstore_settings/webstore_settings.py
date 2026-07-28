import frappe
from frappe import _
from frappe.model.document import Document

from upande_webstore.theme import fonts


class WebstoreSettings(Document):
	def validate(self):
		self.validate_font_url()

	def validate_font_url(self):
		url = (self.google_fonts_url or "").strip()
		if url and not fonts.is_allowed_url(url):
			frappe.throw(
				_("Google Fonts URL must be an https link to {0}.").format(fonts.ALLOWED_FONT_HOST)
			)
		for role in ("sans", "display", "mono"):
			if self.get(f"font_{role}") == "Custom" and not self.get(f"font_{role}_name"):
				frappe.throw(_("Set a family name for the custom {0} font.").format(role))
