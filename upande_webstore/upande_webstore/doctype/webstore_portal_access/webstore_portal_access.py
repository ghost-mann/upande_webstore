import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from upande_webstore.services.provisioning import grant_portal_access, revoke_portal_access


class WebstorePortalAccess(Document):
	def before_naming(self):
		# The record is named from `email`, and naming re-syncs the field from the
		# name afterwards — so normalising in validate() gets overwritten. Do it
		# here, before the name is taken, and both stay lowercase.
		self.email = (self.email or "").strip().lower()

	def validate(self):
		self.email = (self.email or "").strip().lower()
		if self.status == "Active" and not self.user:
			# status is read-only in the form, but guard against imports
			self.status = "Not Granted"

	@frappe.whitelist()
	def grant(self):
		"""Create or re-link the Website User and give them portal access."""
		frappe.only_for(("System Manager", "Sales Manager", "Sales User"))
		user, contact = grant_portal_access(
			self.customer, self.full_name, self.email, phone=self.phone
		)
		self.db_set(
			{
				"user": user.name,
				"contact": contact.name,
				"status": "Active",
				"granted_on": now_datetime(),
			},
			notify=True,
		)
		return {"user": user.name, "contact": contact.name}

	@frappe.whitelist()
	def password_setup_link(self):
		"""A one-time link the customer uses to set their own password.

		The welcome email carries the same link, but it only arrives if the site
		has a working outgoing Email Account. This lets a salesperson hand the
		link over another way — WhatsApp, SMS, read out on a call — so access
		does not depend on email being configured.

		Generating a new link invalidates any previous one.
		"""
		frappe.only_for(("System Manager", "Sales Manager", "Sales User"))
		if not self.user:
			frappe.throw(_("Grant access first."), frappe.ValidationError)
		user = frappe.get_doc("User", self.user)
		# Frappe exposes no public API that returns the link instead of mailing it
		return {"link": user._reset_password(send_email=False)}

	@frappe.whitelist()
	def revoke(self):
		"""Disable the login, keeping the Contact and its customer link."""
		frappe.only_for(("System Manager", "Sales Manager", "Sales User"))
		if not self.user:
			frappe.throw(_("This person has not been granted access yet."), frappe.ValidationError)
		revoke_portal_access(self.user)
		self.db_set({"status": "Revoked"}, notify=True)
		return {"user": self.user}
