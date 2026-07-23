import frappe

from upande_webstore.api.support import get_claims
from upande_webstore.services.portal import get_customer_docs, portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/claims", "claims")
	context.claims = get_claims()
	orders = get_customer_docs("Sales Order", ["name"], "customer", filters={"docstatus": 1}, limit=20, order_by="transaction_date desc")
	invoices = get_customer_docs("Sales Invoice", ["name"], "customer", filters={"docstatus": 1}, limit=20, order_by="posting_date desc")
	context.reference_docs = [o.name for o in orders] + [i.name for i in invoices]
	return context
