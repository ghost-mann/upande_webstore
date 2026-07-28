import frappe
from frappe import _
from frappe.model.document import Document

BOUNDS = {
	"spend_months": (1, 36),
	"recent_orders_count": (1, 50),
	"top_items_count": (1, 25),
	"statement_default_days": (1, 730),
	"max_attachment_mb": (1, 100),
}


class WebstorePortalSettings(Document):
	def validate(self):
		self.validate_bounds()
		self.validate_claim_types()

	def validate_bounds(self):
		"""Keep the numbers inside ranges the pages can actually render, so a
		typo cannot produce an empty dashboard or a two-year query."""
		for fieldname, (low, high) in BOUNDS.items():
			value = self.get(fieldname)
			if value in (None, "", 0):
				continue
			if not (low <= int(value) <= high):
				frappe.throw(
					_("{0} must be between {1} and {2}.").format(
						_(self.meta.get_label(fieldname)), low, high
					)
				)

	def validate_claim_types(self):
		seen = set()
		for row in self.claim_types or []:
			label = (row.claim_type or "").strip()
			if not label:
				continue
			if label.casefold() in seen:
				frappe.throw(_("Claim type {0} is listed twice.").format(label))
			seen.add(label.casefold())
