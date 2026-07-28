import frappe

from upande_webstore.services.portal import portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/claims", "claims")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/claims"
		raise frappe.Redirect

	from upande_webstore.api.claims import get_claim

	context.doc = get_claim(name)
	context.attachments = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Webstore Claim", "attached_to_name": name},
		fields=["file_name", "file_url"],
		ignore_permissions=True,
	)
	return context
