import frappe

from upande_webstore.api.support import get_issues
from upande_webstore.services.portal import portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/support", "support")
	context.issues = get_issues()
	return context
