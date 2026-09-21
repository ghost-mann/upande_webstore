import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from upande_webstore.services.claims import assert_belongs_to, assert_credit_note


class WebstoreClaim(Document):
	def validate(self):
		if not self.posting_date:
			self.posting_date = now_datetime()
		if not self.raised_by:
			self.raised_by = frappe.session.user
		self.validate_references()

	def validate_references(self):
		"""Every referenced document must belong to this claim's customer.

		Enforced here rather than in the portal API so it also covers desk edits,
		imports and any future caller.
		"""
		assert_belongs_to(self.customer, self.against_doctype, self.against_document)
		for row in self.related_documents or []:
			assert_belongs_to(self.customer, row.reference_doctype, row.reference_name)
		assert_credit_note(self.customer, self.credit_note)
