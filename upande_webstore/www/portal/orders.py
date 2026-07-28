import frappe

from upande_webstore.services.portal import get_customer_docs, portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/orders", "orders")
	# Drafts are included because a customer who orders directly from the
	# webstore gets a draft Sales Order — without this their own order would be
	# invisible to them until the sales team submitted it. Cancelled (2) stays out.
	context.orders = get_customer_docs(
		"Sales Order",
		["name", "transaction_date", "status", "docstatus", "per_delivered", "per_billed", "grand_total", "currency"],
		"customer",
		filters={"docstatus": ["<", 2]},
		limit=50,
		order_by="transaction_date desc",
	)
	return context
