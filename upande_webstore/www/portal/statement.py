import frappe
from frappe.utils import add_days, getdate, nowdate

from upande_webstore.services.portal import portal_page_context
from upande_webstore.services.statement import get_statement


def get_context(context):
	portal_page_context(context, "/portal/statement", "statement")
	from upande_webstore.services.portal_settings import get_int

	default_days = get_int("statement_default_days")
	context.from_date = getdate(
		frappe.form_dict.get("from") or add_days(nowdate(), -default_days)
	)
	context.to_date = getdate(frappe.form_dict.get("to") or nowdate())
	context.statement = get_statement(context.from_date, context.to_date)
	context.currency = frappe.get_cached_value(
		"Company", frappe.defaults.get_global_default("company"), "default_currency"
	)
	return context
