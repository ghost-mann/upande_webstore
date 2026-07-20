import frappe

from upande_webstore.api.support import get_issues
from upande_webstore.services.portal import portal_guard


def get_context(context):
	portal_guard("/portal/support")
	context.no_cache = 1
	context.issues = get_issues()
	return context
