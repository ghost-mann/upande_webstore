import frappe

from upande_webstore.services.portal import assert_customer_doc, portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/quotations", "quotations")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/quotations"
		raise frappe.Redirect
	context.doc = assert_customer_doc("Quotation", name, "party_name")
	context.actionable = context.doc.docstatus == 1 and not context.doc.webstore_portal_status
	return context
