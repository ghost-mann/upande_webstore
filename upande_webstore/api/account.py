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
