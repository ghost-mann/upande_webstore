import frappe

from upande_webstore.services.portal import get_customer_docs, portal_guard


def get_context(context):
	portal_guard("/portal/quotations")
	context.no_cache = 1
	context.quotations = get_customer_docs(
		"Quotation",
		["name", "transaction_date", "valid_till", "status", "webstore_portal_status", "grand_total", "currency"],
		"party_name",
		filters={"docstatus": 1},
		limit=50,
		order_by="transaction_date desc",
	)
	return context
