import frappe

from upande_webstore.services.portal import get_customer_docs, portal_guard


def get_context(context):
	portal_guard("/portal/invoices")
	context.no_cache = 1
	context.invoices = get_customer_docs(
		"Sales Invoice",
		["name", "posting_date", "due_date", "status", "grand_total", "outstanding_amount", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=50,
		order_by="posting_date desc",
	)
	return context
