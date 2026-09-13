import re

import frappe
from frappe import _
from frappe.model.document import Document

# A slug sharing a name with a route the app (or the site) already owns would
# make that storefront unreachable — /portal/store would collide with the
# shared customer portal — or silently shadow it. Checked as a fixed list
# rather than derived from website_route_rules: those rules are Task 2's, and
# this set is the one the spec calls out by name.
RESERVED_SLUGS = frozenset(
	{"portal", "api", "app", "assets", "files", "login", "signup", "desk", "private", "me"}
)

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Webstore(Document):
	def validate(self):
		self.validate_slug()

	def validate_slug(self):
		slug = (self.slug or "").strip()
		if not SLUG_PATTERN.match(slug):
			frappe.throw(
				_(
					"Slug must be lowercase letters, digits and hyphens only, and cannot "
					"start with a hyphen (got {0})."
				).format(self.slug),
				frappe.ValidationError,
			)
		if slug in RESERVED_SLUGS:
			frappe.throw(
				_("{0} is a reserved path and cannot be used as a store slug.").format(slug),
				frappe.ValidationError,
			)
		# autoname (field:slug) has already set self.name to slug by the time
		# validate runs, so comparing names cannot tell "this record" from "a
		# different one with the same slug" — only is_new() can, here.
		if self.is_new() and frappe.db.exists("Webstore", slug):
			frappe.throw(
				_("A store with slug {0} already exists.").format(slug),
				frappe.ValidationError,
			)
