import frappe
from frappe import _

from upande_webstore.services.pricing import get_customer


def get_website_user_home_page(user):
	"""Where a portal customer lands after login.

	Wired via the `get_website_user_home_page` hook. frappe only reaches this
	hook once two earlier checks come up empty - Role.home_page for any of the
	user's roles, then Portal Settings.default_portal_home
	(frappe/website/utils.py get_home_page) - so a site that has configured
	either of those silently wins over the landing_page setting this reuses;
	both are unset on every site this app has installed on so far, but that
	precedence is frappe's, not this hook's, to override.

	Returns None for anyone this app is not responsible for - no active
	portal access, or a user who (despite holding portal access) currently
	has desk access - so frappe's normal resolution carries on for them; a
	System Manager must never be redirected into the portal.
	"""
	from upande_webstore.services.portal_settings import LANDING_ROUTES, get_landing_route
	from upande_webstore.services.provisioning import has_active_portal_access

	if not has_active_portal_access(user):
		return None
	if frappe.db.get_value("User", user, "user_type") != "Website User":
		return None
	return get_landing_route() or LANDING_ROUTES["Dashboard"]


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
	"""Shared context for every portal page: feature gate, guard, sidebar badges,
	at-a-glance stats and the customer identity card.

	`active` doubles as the page's feature key, so this single call gates all
	twelve portal pages. Gated before the login redirect, so a disabled page
	404s for guests rather than bouncing them to a login that leads nowhere.
	"""
	from upande_webstore.services.portal_data import get_sidebar_counts
	from upande_webstore.theme.features import require

	require("portal", active)

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
