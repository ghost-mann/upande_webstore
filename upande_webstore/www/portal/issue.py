import frappe

from upande_webstore.api.support import get_issue_or_throw, get_replies
from upande_webstore.services.portal import portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/support", "support")
	name = frappe.form_dict.get("name")
	if not name:
		frappe.local.flags.redirect_location = "/portal/support"
		raise frappe.Redirect
	context.doc = get_issue_or_throw(name)
	context.replies = get_replies(name)
	return context
