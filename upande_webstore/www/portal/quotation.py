import frappe

from upande_webstore.services.portal import assert_customer_doc, portal_guard


def get_context(context):
	portal_guard("/portal/quotations")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/quotations"
		raise frappe.Redirect
	context.no_cache = 1
	context.doc = assert_customer_doc("Quotation", name, "party_name")
	context.actionable = context.doc.docstatus == 1 and not context.doc.webstore_portal_status
	return context
