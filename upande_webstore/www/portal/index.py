import frappe

from upande_webstore.services.portal import (
	get_customer_docs,
	get_outstanding_balance,
	portal_guard,
)


def get_context(context):
	customer = portal_guard("/portal")
	context.no_cache = 1
	context.customer = customer
	context.balance = get_outstanding_balance()
	context.currency = frappe.get_cached_value(
		"Company", frappe.defaults.get_global_default("company"), "default_currency"
	)
	context.open_quotations = len(
		get_customer_docs(
			"Quotation", ["name"], "party_name",
			filters={"docstatus": 1, "status": ["not in", ["Lost", "Ordered", "Expired"]]},
			limit=100,
		)
	)
	context.recent_orders = get_customer_docs(
		"Sales Order",
		["name", "transaction_date", "status", "grand_total", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=5,
		order_by="transaction_date desc",
	)
	return context
