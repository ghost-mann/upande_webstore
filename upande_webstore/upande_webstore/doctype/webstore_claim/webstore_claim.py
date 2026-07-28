import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from upande_webstore.services.claims import assert_belongs_to, assert_credit_note
from upande_webstore.services.portal_settings import get_claim_types


class WebstoreClaim(Document):
	def validate(self):
		if not self.posting_date:
			self.posting_date = now_datetime()
		if not self.raised_by:
			self.raised_by = frappe.session.user
		self.validate_claim_type()
		self.validate_references()

	def validate_claim_type(self):
		"""claim_type is a Data field so Portal Settings can define the list; that
		means the allowed values have to be checked here rather than by a Select."""
		allowed = get_claim_types()
		if (self.claim_type or "").strip() not in allowed:
			frappe.throw(
				frappe._("Claim type must be one of: {0}").format(", ".join(allowed)),
				frappe.ValidationError,
			)

	def validate_references(self):
		"""Every referenced document must belong to this claim's customer.

		Enforced here rather than in the portal API so it also covers desk edits,
		imports and any future caller.
		"""
		assert_belongs_to(self.customer, self.against_doctype, self.against_document)
		for row in self.related_documents or []:
			assert_belongs_to(self.customer, row.reference_doctype, row.reference_name)
		assert_credit_note(self.customer, self.credit_note)
