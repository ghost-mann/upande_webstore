import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from upande_webstore.services.claims import (
	assert_belongs_to,
	assert_contact_belongs,
	assert_credit_note,
)
from upande_webstore.services.claim_lines import (
	assert_claimable_quantities,
	claimed_total,
	line_amount,
)


class WebstoreClaim(Document):
	def validate(self):
		if not self.posting_date:
			self.posting_date = now_datetime()
		self.set_action_markers()
		self.validate_references()
		self.validate_lines()

	def set_action_markers(self):
		"""Read from the action master, not believed from the client: they
		decide how the total is computed and which fields apply."""
		markers = (
			frappe.db.get_value(
				"Webstore Claim Action",
				self.action,
				["is_price_adjustment", "requires_credit_note"],
				as_dict=True,
			)
			if self.action
			else None
		) or {}
		self.is_price_adjustment = markers.get("is_price_adjustment") or 0
		self.requires_credit_note = markers.get("requires_credit_note") or 0

	def validate_lines(self):
		"""The totals are ours, not the client's — the stance services/packing.py
		takes on box counts, for the same reason."""
		price_adjustment = bool(self.is_price_adjustment)
		lines = self.lines or []
		if not price_adjustment:
			# New Unit Value only means something under a price adjustment; a
			# value left behind by a changed action would show as if it counted
			for row in lines:
				row.new_rate = 0
		assert_claimable_quantities(lines, price_adjustment)
		for row in lines:
			row.claim_amount = line_amount(row, price_adjustment)
		self.proposed_total = claimed_total(lines, price_adjustment)

	def validate_references(self):
		"""Every referenced document must belong to this claim's customer.

		Enforced here rather than in the portal API so it also covers desk edits,
		imports and any future caller.
		"""
		assert_belongs_to(self.customer, self.against_doctype, self.against_document)
		for row in self.related_documents or []:
			assert_belongs_to(self.customer, row.reference_doctype, row.reference_name)
		assert_contact_belongs(self.customer, self.contact_person)
		assert_credit_note(self.customer, self.credit_note)
