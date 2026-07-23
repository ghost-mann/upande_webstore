import frappe

from upande_webstore.services.portal import get_customer_docs, portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/invoices", "invoices")
	context.invoices = get_customer_docs(
		"Sales Invoice",
		["name", "posting_date", "due_date", "status", "grand_total", "outstanding_amount", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=50,
		order_by="posting_date desc",
	)
	return context
