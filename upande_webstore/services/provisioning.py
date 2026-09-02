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


def _desk_access_roles(role_names):
	"""Which of these role names grant desk access, per the Role doctype's own
	desk_access flag.

	This is the same signal frappe itself derives user_type from
	(User.has_desk_access, frappe/core/doctype/user/user.py) - checked directly
	against the roles in question rather than trusting a user's stored
	user_type, which only gets recomputed on save and so can be stale. Checking
	roles directly also needs no special case for Administrator: its user_type
	is hardcoded to "System User" regardless of roles, but in practice it also
	carries roles with desk_access=1 (System Manager and friends), so it is
	caught the same way as everyone else.

	Shared by ensure_user() (an existing user must not already have desk
	access before portal access is granted) and
	guard_desk_access_for_portal_customers() (a portal customer must not be
	newly given a desk-access role) - one decision, two moments it is asked at.
	"""
	return sorted(role for role in role_names if frappe.get_cached_value("Role", role, "desk_access"))


def ensure_user(email, full_name, phone=None, send_welcome=True):
	"""Website User for this email, created if absent. Never grants desk access.

	Refuses outright when the email already belongs to a user who holds desk
	access: reusing that account for portal access would leave a customer
	login that still reaches the desk, and this function must never strip an
	existing account's roles to fix that - it might be a real staff member's
	account. The caller has to resolve the conflict by hand (a different
	email, or demoting the account in User first).
	"""
	email = (email or "").strip().lower()
	validate_email_address(email, throw=True)
	if not (full_name or "").strip():
		frappe.throw(_("Full name is required."), frappe.ValidationError)

	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		desk_roles = _desk_access_roles(r.role for r in user.roles)
		if desk_roles:
			frappe.throw(
				_(
					"{0} is a desk user (role(s): {1}) and cannot be granted portal access - "
					"they would still be able to reach the desk. Use a different email for "
					"this contact, or remove {0}'s desk access in User first."
				).format(email, ", ".join(desk_roles)),
				frappe.ValidationError,
				title=_("Email belongs to a desk user"),
			)
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
		try:
			user.insert()
		except frappe.OutgoingEmailError:
			# a missing or misconfigured mail account must not block provisioning;
			# the salesperson can hand over the password link instead
			frappe.clear_messages()
			user.flags.no_welcome_mail = True
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


def has_active_portal_access(user):
	"""True only when `user` holds an Active Webstore Portal Access record.

	This, not the Customer role, is the source of truth for "is this a portal
	customer" wherever this app needs to answer that question: a site can
	reuse the Customer role for something this app never touches, but this
	app is the only writer of Webstore Portal Access, so its status is the
	precise signal - grant() flips it to Active, revoke() flips it back.
	"""
	if not user or user in ("Administrator", "Guest"):
		return False
	return bool(frappe.db.exists("Webstore Portal Access", {"user": user, "status": "Active"}))


def guard_desk_access_for_portal_customers(doc, method=None):
	"""User.validate doc_event: refuse to grant a desk-access role to someone
	who currently holds active portal access.

	Frappe flips a user's user_type to System User the moment any assigned
	role has desk_access=1 (User.set_system_user, called from the core
	validate() that runs before doc_events - frappe/core/doctype/user/user.py
	lines ~404-415). That recalculation already happened by the time this
	hook fires, so there is nothing here to race or loop against: this only
	blocks the save outright, before it reaches the database, so the
	recalculated user_type is never persisted either.

	Fires only on a role newly added in *this* save, not on the mere
	coexistence of an existing System User and an active portal access
	record - an existing System Manager who is also a customer contact must
	keep saving undisturbed; only the transition (granting a desk role while
	portal access is active) is refused. ensure_user()'s own Customer grant
	sails through untouched because Customer carries no desk access.
	"""
	if not has_active_portal_access(doc.name):
		return

	before = doc.get_doc_before_save()
	previous_roles = {r.role for r in ((before.get("roles") if before else None) or [])}
	current_roles = {r.role for r in (doc.get("roles") or [])}
	newly_added = current_roles - previous_roles
	if not newly_added:
		return

	desk_roles = _desk_access_roles(newly_added)
	if not desk_roles:
		return

	frappe.throw(
		_(
			"{0} has active portal access and cannot also be given the role(s) {1}, "
			"which grant desk access. Revoke their portal access first if you "
			"genuinely want to give them desk access."
		).format(doc.name, ", ".join(desk_roles)),
		frappe.ValidationError,
		title=_("Portal customer cannot be given desk access"),
	)


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
