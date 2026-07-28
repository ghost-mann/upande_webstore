"""Portal access provisioning.

Builds the User -> Contact -> Customer chain that get_customer() resolves. Shared
by self-service signup and by the sales team's Webstore Portal Access tool, so
there is one implementation of "what portal access means".

Accounts are Website Users with the Customer role: portal and storefront only,
never desk access.
"""

import frappe
from frappe import _
from frappe.utils import validate_email_address

PORTAL_ROLE = "Customer"


def ensure_user(email, full_name, phone=None, send_welcome=True):
	"""Website User for this email, created if absent. Never grants desk access."""
	email = (email or "").strip().lower()
	validate_email_address(email, throw=True)
	if not (full_name or "").strip():
		frappe.throw(_("Full name is required."), frappe.ValidationError)

	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": full_name.strip(),
				"mobile_no": phone,
				"user_type": "Website User",
				"send_welcome_email": 1 if send_welcome else 0,
			}
		)
		user.flags.ignore_permissions = True
		user.insert()

	if PORTAL_ROLE not in [r.role for r in user.roles]:
		user.add_roles(PORTAL_ROLE)
	return user


def link_contact(email, full_name, customer, phone=None):
	"""Contact for this user, linked to the customer. Idempotent."""
	contact_name = frappe.db.get_value("Contact", {"user": email})
	if contact_name:
		contact = frappe.get_doc("Contact", contact_name)
	else:
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": (full_name or email).strip(),
				"user": email,
				"email_ids": [{"email_id": email, "is_primary": 1}],
			}
		)
		contact.flags.ignore_permissions = True
		contact.insert()

	linked = any(
		link.link_doctype == "Customer" and link.link_name == customer for link in contact.links or []
	)
	if not linked:
		contact.append("links", {"link_doctype": "Customer", "link_name": customer})
	if phone and not contact.phone_nos:
		contact.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1})
	contact.flags.ignore_permissions = True
	contact.save()
	return contact


def grant_portal_access(customer, full_name, email, phone=None, send_welcome=True):
	"""Give one person portal + storefront access to an existing customer.

	Returns (user, contact). Safe to re-run: an existing user is re-linked and
	re-enabled rather than duplicated.
	"""
	if not customer or not frappe.db.exists("Customer", customer):
		frappe.throw(_("Select an existing customer."), frappe.ValidationError)

	user = ensure_user(email, full_name, phone=phone, send_welcome=send_welcome)
	if not user.enabled:
		user.enabled = 1
		user.flags.ignore_permissions = True
		user.save()
	contact = link_contact(user.name, full_name, customer, phone=phone)
	return user, contact


def revoke_portal_access(email):
	"""Disable the login. The Contact and its Customer link are kept, so history
	stays intact and access can be restored without retyping anything."""
	if not frappe.db.exists("User", email):
		return None
	user = frappe.get_doc("User", email)
	user.enabled = 0
	user.flags.ignore_permissions = True
	user.save()
	return user
