import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import validate_email_address

from upande_webstore.services.settings import get_settings


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
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
def update_profile(full_name, phone):
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
def add_address(address_title, address_line1, city, country, phone=None):
	from upande_webstore.api.cart import _require_login
	from upande_webstore.services.portal import get_current_customer

	_require_login()
	customer = get_current_customer()
	if not (address_title and address_line1 and city and country):
		frappe.throw(_("All address fields except phone are required."), frappe.ValidationError)
	address = frappe.get_doc({
		"doctype": "Address",
		"address_title": address_title,
		"address_type": "Shipping",
		"address_line1": address_line1,
		"city": city,
		"country": country,
		"phone": phone,
		"links": [{"link_doctype": "Customer", "link_name": customer}],
	})
	address.flags.ignore_permissions = True
	address.insert()
	return {"name": address.name}
