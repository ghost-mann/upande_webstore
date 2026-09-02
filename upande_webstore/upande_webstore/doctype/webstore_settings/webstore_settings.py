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
		self.validate_guest_price_lists()
		self.apply_feature_dependencies()

	def on_update(self):
		self.reconcile_role_permissions()

	def reconcile_role_permissions(self):
		"""Apply the Roles section to real Custom DocPerms.

		Deliberately on_update, not validate: this writes Custom DocPerm
		records for *other* doctypes, a side effect with consequences well
		beyond this form, so it must run against the configuration that is
		actually about to be saved — after validate has had its say on what
		that configuration is — and exactly once per save, not once per
		validate call. A failure here must not pass silently: it is logged
		and re-raised, which rolls the whole save back rather than leaving
		Webstore Settings claiming a grant that was never actually applied.
		"""
		from upande_webstore.services import roles

		try:
			applied = roles.reconcile(self)
		except Exception:
			frappe.log_error(
				title=_("Webstore Settings role permission reconcile failed"),
				message=frappe.get_traceback(),
			)
			raise
		if applied != (self.applied_role_permissions or ""):
			self.db_set("applied_role_permissions", applied, update_modified=False)

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

	def validate_guest_price_lists(self):
		"""Every row offered to guests must actually be usable, and the table
		as a whole must resolve unambiguously.

		A visitor picks a *currency*, not a price list, so two rows sharing a
		currency could never be told apart by the picker — and a row pointing
		at a buying-only or disabled price list would let a guest choose a
		list that was never meant to be public. Both are refused at save time
		rather than discovered later as a silently-skipped row (see
		pricing.get_offered_price_lists, which re-checks the same two things
		live, since a row valid at save can still go stale afterwards).
		"""
		seen_currencies = {}
		default_seen = False
		for row in self.guest_price_lists or []:
			info = frappe.db.get_value(
				"Price List", row.price_list, ["enabled", "selling", "currency"], as_dict=True
			)
			if not info or not info.enabled or not info.selling:
				frappe.throw(
					_("{0} must be an enabled, selling price list to be offered to guests.").format(
						row.price_list
					)
				)
			if info.currency in seen_currencies:
				frappe.throw(
					_(
						"{0} and {1} are both priced in {2}. Only one guest price list per "
						"currency may be offered, since the visitor picks a currency."
					).format(seen_currencies[info.currency], row.price_list, info.currency)
				)
			seen_currencies[info.currency] = row.price_list
			if row.is_default:
				if default_seen:
					frappe.throw(_("Only one guest price list may be marked Default."))
				default_seen = True

	def apply_feature_dependencies(self):
		# the drawer has nothing to show without a cart
		if not self.enable_cart and self.enable_cart_drawer:
			self.enable_cart_drawer = 0

		# "Sales order only" says the sales order IS the checkout, so the flag
		# that gates it cannot stay off: the cart page would render no checkout
		# button at all and place_order would refuse both modes, leaving a buyer
		# with a full basket and no way out and nothing on screen explaining why
		if self.checkout_mode == "Sales order only" and not self.enable_direct_order:
			self.enable_direct_order = 1

	def validate_font_url(self):
		url = (self.google_fonts_url or "").strip()
		if url and not fonts.is_allowed_url(url):
			frappe.throw(
				_("Google Fonts URL must be an https link to {0}.").format(fonts.ALLOWED_FONT_HOST)
			)
		for role in ("sans", "display", "mono"):
			if self.get(f"font_{role}") == "Custom" and not self.get(f"font_{role}_name"):
				frappe.throw(_("Set a family name for the custom {0} font.").format(role))
