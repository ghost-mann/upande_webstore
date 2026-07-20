import frappe
from frappe.utils import add_days, getdate, nowdate

from upande_webstore.services.portal import portal_guard
from upande_webstore.services.statement import get_statement


def get_context(context):
	portal_guard("/portal/statement")
	context.no_cache = 1
	context.from_date = getdate(frappe.form_dict.get("from") or add_days(nowdate(), -90))
	context.to_date = getdate(frappe.form_dict.get("to") or nowdate())
	context.statement = get_statement(context.from_date, context.to_date)
	context.currency = frappe.get_cached_value(
		"Company", frappe.defaults.get_global_default("company"), "default_currency"
	)
	return context
