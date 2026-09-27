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
	context.description_html = description_html(context.doc.description)
	context.attachments = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Webstore Claim", "attached_to_name": name},
		fields=["file_name", "file_url"],
		ignore_permissions=True,
	)
	return context


def description_html(description):
	"""Description is a Text Editor, so it is HTML — sanitised again here
	because the template prints it unescaped. A claim written before the field
	became a Text Editor is plain text and keeps its line breaks."""
	from frappe.utils.html_utils import sanitize_html

	from upande_webstore.api.claims import plain_text_to_html

	if not description:
		return ""
	if "<" not in description and ">" not in description:
		return plain_text_to_html(description)
	return sanitize_html(description)
