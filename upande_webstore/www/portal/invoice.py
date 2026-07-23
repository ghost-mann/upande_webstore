import frappe

from upande_webstore.services.portal import assert_customer_doc, portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/invoices", "invoices")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/invoices"
		raise frappe.Redirect
	context.doc = assert_customer_doc("Sales Invoice", name, "customer")
	return context
