import frappe

from upande_webstore.services.portal import get_customer_docs, portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/orders", "orders")
	context.orders = get_customer_docs(
		"Sales Order",
		["name", "transaction_date", "status", "per_delivered", "per_billed", "grand_total", "currency"],
		"customer",
		filters={"docstatus": 1},
		limit=50,
		order_by="transaction_date desc",
	)
	return context
