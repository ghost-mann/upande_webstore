"""Customer portal behaviour.

Whether a portal page exists at all is a feature flag in Webstore Settings; this
module only answers "how should it behave". One read path so a default is never
defined twice.
"""

import frappe

# fieldname -> fallback when unset. These are the values the pages used to
# hardcode, so an unconfigured site behaves exactly as it did before.
DEFAULTS = {
	"landing_page": "Dashboard",
	"welcome_note": "",
	"support_note": "",
	"spend_months": 12,
	"recent_orders_count": 6,
	"top_items_count": 5,
	"statement_default_days": 90,
	"quotation_accept_requires_po": 0,
	"allow_invoice_pdf": 1,
	"claim_window_days": 14,
	"require_claim_document": 0,
	"allow_claim_attachments": 1,
	"max_attachment_mb": 10,
	"allow_profile_edit": 1,
	"allow_address_edit": 1,
}

SHIPPED_CLAIM_TYPES = (
	"Damaged goods",
	"Short delivery",
	"Quality below grade",
	"Billing error",
	"Other",
)

LANDING_ROUTES = {
	"Dashboard": "/portal",
	"Orders": "/portal/orders",
	"Quotations": "/portal/quotations",
	"Invoices": "/portal/invoices",
	"Statement": "/portal/statement",
}

# landing page -> the feature that must be on for it to be reachable
LANDING_FEATURES = {
	"Dashboard": "dashboard",
	"Orders": "orders",
	"Quotations": "quotations",
	"Invoices": "invoices",
	"Statement": "statement",
}


def get_portal_settings():
	return frappe.get_cached_doc("Webstore Portal Settings")


def get(fieldname):
	"""One setting, falling back to the value the portal used to hardcode."""
	if fieldname not in DEFAULTS:
		raise ValueError(f"unknown portal setting: {fieldname!r}")
	default = DEFAULTS[fieldname]
	value = get_portal_settings().get(fieldname)
	if value in (None, ""):
		return default
	if isinstance(default, int):
		try:
			return int(value)
		except (TypeError, ValueError):
			return default
	return value


def get_int(fieldname, minimum=1):
	"""A count that must stay usable: 0 or nonsense falls back to the default."""
	value = get(fieldname)
	return value if value and value >= minimum else DEFAULTS[fieldname]


def is_on(fieldname):
	return bool(get(fieldname))


def get_claim_types():
	"""Configured claim types, or the shipped list when none are set."""
	rows = [
		(row.claim_type or "").strip()
		for row in (get_portal_settings().get("claim_types") or [])
		if (row.claim_type or "").strip()
	]
	return tuple(rows) if rows else SHIPPED_CLAIM_TYPES


def get_landing_route():
	"""Where /portal should send the customer.

	Falls back to the dashboard when the configured page is switched off, so a
	stale setting can never land someone on a 404.
	"""
	from upande_webstore.theme.features import enabled

	choice = get("landing_page") or "Dashboard"
	flags = enabled()
	feature = LANDING_FEATURES.get(choice)
	if choice == "Dashboard" or not feature or not flags.get(feature):
		return None if choice == "Dashboard" else LANDING_ROUTES["Dashboard"]
	return LANDING_ROUTES[choice]
