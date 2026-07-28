import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address

from upande_webstore.services.settings import get_settings
from upande_webstore.theme.features import guard


def _address_types():
	"""Read the options straight off the Address doctype so the portal cannot
	drift from what the desk accepts."""
	field = frappe.get_meta("Address").get_field("address_type")
	return tuple(o for o in (field.options or "").split("\n") if o.strip())


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
@guard("signup")
def sign_up(email, full_name, phone, company_name=None):
	email = (email or "").strip().lower()
	full_name = (full_name or "").strip()
	company_name = (company_name or "").strip() or None
	validate_email_address(email, throw=True)
	if not full_name:
		frappe.throw(_("Full name is required."), frappe.ValidationError)
	if frappe.db.exists("User", email):
		frappe.throw(_("An account with this email already exists. Please log in."), frappe.ValidationError)

	customer_name = company_name or full_name
	if frappe.db.exists("Customer", customer_name):
		frappe.throw(
			_("A customer named {0} already exists. Contact us to get portal access.").format(customer_name),
			frappe.ValidationError,
		)

	settings = get_settings()
	user = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": full_name,
		"mobile_no": phone,
		"user_type": "Website User",
		"send_welcome_email": 1,
	})
	user.flags.ignore_permissions = True
	user.insert()
	user.add_roles("Customer")

	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": customer_name,
		"customer_type": "Company" if company_name else "Individual",
		"customer_group": settings.default_customer_group,
		"territory": settings.default_territory,
	})
	customer.flags.ignore_permissions = True
	customer.insert()

	contact_name = frappe.db.get_value("Contact", {"user": email})
	if contact_name:
		# frappe auto-creates a bare Contact for new users; attach the Customer link
		contact = frappe.get_doc("Contact", contact_name)
		contact.append("links", {"link_doctype": "Customer", "link_name": customer.name})
		if phone and not contact.phone_nos:
			contact.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1})
		contact.flags.ignore_permissions = True
		contact.save()
	else:
		contact = frappe.get_doc({
			"doctype": "Contact",
			"first_name": full_name,
			"user": email,
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"phone_nos": [{"phone": phone, "is_primary_mobile_no": 1}] if phone else [],
			"links": [{"link_doctype": "Customer", "link_name": customer.name}],
		})
		contact.flags.ignore_permissions = True
		contact.insert()

	return {"message": _("Account created. Check your email to set your password.")}


@frappe.whitelist(methods=["POST"])
@guard("portal", "account")
def update_profile(full_name, phone):
	from upande_webstore.services.portal_settings import is_on

	if not is_on("allow_profile_edit"):
		frappe.throw(_("Profile changes are not available."), frappe.PermissionError)
	from upande_webstore.api.cart import _require_login

	_require_login()
	full_name = (full_name or "").strip()
	if not full_name:
		frappe.throw(_("Name is required."), frappe.ValidationError)
	user = frappe.get_doc("User", frappe.session.user)
	user.first_name = full_name
	user.mobile_no = phone
	user.flags.ignore_permissions = True
	user.save()
	contact_name = frappe.db.get_value("Contact", {"user": frappe.session.user})
	if contact_name:
		frappe.db.set_value("Contact", contact_name, {"first_name": full_name})
	return {"message": _("Profile updated.")}


@frappe.whitelist(methods=["POST"])
@guard("portal", "account")
def add_address(
	address_title,
	address_line1,
	city,
	country,
	address_type="Shipping",
	address_line2=None,
	state=None,
	pincode=None,
	phone=None,
	email_id=None,
	is_primary_address=0,
	is_shipping_address=0,
):
	"""Create an Address for the session user's customer.

	Mirrors the Address doctype rather than a reduced subset, so a portal-created
	address is indistinguishable from one your team enters in the desk.
	"""
	from upande_webstore.services.portal_settings import is_on

	if not is_on("allow_address_edit"):
		frappe.throw(_("Adding addresses is not available."), frappe.PermissionError)
	from upande_webstore.api.cart import _require_login
	from upande_webstore.services.portal import get_current_customer

	_require_login()
	customer = get_current_customer()
	if not (address_title and address_line1 and city and country):
		frappe.throw(
			_("Label, street, city and country are required."), frappe.ValidationError
		)

	allowed_types = _address_types()
	address_type = (address_type or "Shipping").strip()
	if address_type not in allowed_types:
		frappe.throw(
			_("Address type must be one of: {0}").format(", ".join(allowed_types)),
			frappe.ValidationError,
		)

	address = frappe.get_doc({
		"doctype": "Address",
		"address_title": address_title,
		"address_type": address_type,
		"address_line1": address_line1,
		"address_line2": address_line2,
		"city": city,
		"state": state,
		"pincode": pincode,
		"country": country,
		"phone": phone,
		"email_id": email_id,
		"is_primary_address": 1 if int(is_primary_address or 0) else 0,
		"is_shipping_address": 1 if int(is_shipping_address or 0) else 0,
		"links": [{"link_doctype": "Customer", "link_name": customer}],
	})
	address.flags.ignore_permissions = True
	address.insert()
	return {"name": address.name}
