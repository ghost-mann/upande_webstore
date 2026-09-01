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
		self.validate_default_box_type()
		self.apply_feature_dependencies()

	def validate_occasion(self):
		if not self.occasion:
			return
		from upande_webstore.theme import occasion

		if self.occasion not in occasion.list_names():
			frappe.throw(_("No shipped occasion named {0}.").format(self.occasion))

	def validate_default_box_type(self):
		"""The farm default is the box most cart lines actually get, so a typo
		here turns box enforcement off across the whole storefront while the form
		still says it is on: every line falls back to no box, get_pack_rate
		returns 0 and compute_boxes reports is_full. The field is an Autocomplete
		rather than a Link — the doctype box types live in differs per farm — so
		nothing but this check stands between a mistyped name and that silence.
		Blank is valid: it means "no farm default".

		Only checked when the value actually changed. Webstore Settings is one
		big form — Theme, Branding, nineteen feature toggles — and a default that
		was valid when it was set can go stale on its own: the box Item gets
		disabled, or the `Box Type` table gets emptied, with nobody touching this
		field. Without the change guard, an operator changing an unrelated colour
		hits a box-type error about a field they never touched, and `apply_theme`
		(the desk "Apply Preset" button, which saves the whole form including
		this field untouched) fails the same way. An operator who breaks it by
		setting it themselves still gets told at that moment, which is the point
		of the check; a stale value inherited from before no longer holds the
		whole form hostage."""
		if not self.default_box_type:
			return
		if not self.has_value_changed("default_box_type"):
			return
		from upande_webstore.services.packing import box_source_hint, is_usable_box

		if not is_usable_box(self.default_box_type):
			frappe.throw(
				_("{0} is not a usable box type on this site. {1}").format(
					self.default_box_type, box_source_hint()
				),
				frappe.ValidationError,
			)

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
