import frappe
from frappe import _

from upande_webstore.services.pricing import get_customer


def get_current_customer():
	customer = get_customer()
	if not customer:
		frappe.throw(_("Your account is not linked to a customer."), frappe.PermissionError)
	return customer


def assert_customer_doc(doctype, name, party_field):
	customer = get_current_customer()
	doc = frappe.get_doc(doctype, name)
	if doc.get(party_field) != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return doc


def get_customer_docs(doctype, fields, party_field, filters=None, limit=20, order_by="modified desc"):
	customer = get_current_customer()
	filters = dict(filters or {})
	filters[party_field] = customer
	return frappe.get_all(
		doctype, filters=filters, fields=fields, limit_page_length=limit, order_by=order_by
	)


def get_outstanding_balance():
	# erpnext's get_balance_on enforces desk permissions website users lack;
	# the query below is already scoped to the session user's own customer.
	customer = get_current_customer()
	rows = frappe.get_all(
		"GL Entry",
		filters={"party_type": "Customer", "party": customer, "is_cancelled": 0},
		fields=["debit", "credit"],
		limit_page_length=0,
	)
	return float(sum(row.debit - row.credit for row in rows))


def portal_guard(route):
	"""Redirect guests to login; returns the current customer."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={route}"
		raise frappe.Redirect
	return get_current_customer()


def portal_page_context(context, route, active):
	"""Shared context for every portal page: guard, sidebar badges,
	at-a-glance stats and the customer identity card."""
	from upande_webstore.services.portal_data import get_sidebar_counts

	customer = portal_guard(route)
	context.no_cache = 1
	context.full_width = 1
	context.customer = customer
	context.portal_active = active
	context.portal_counts = get_sidebar_counts()
	context.portal_balance = get_outstanding_balance()
	context.portal_currency = frappe.get_cached_value(
		"Company", frappe.defaults.get_global_default("company"), "default_currency"
	)
	context.customer_since = frappe.db.get_value("Customer", customer, "creation")
	return customer
