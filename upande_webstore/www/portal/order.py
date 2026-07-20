import frappe

from upande_webstore.services.portal import assert_customer_doc, portal_guard


def get_context(context):
	portal_guard("/portal/orders")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/orders"
		raise frappe.Redirect
	context.no_cache = 1
	context.doc = assert_customer_doc("Sales Order", name, "customer")
	return context
