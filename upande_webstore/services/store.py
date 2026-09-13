"""Store resolution.

Task 2 resolves the store from the request path; until then this answers the
same question from an explicit override plus the shapes a real site can be
in today: exactly one storefront (the common case, and every migrated site),
or the migrated default itself. Every other consumer — `services.settings`
included — reads `current_store()` rather than working any of this out again.

Cached on `frappe.local` exactly as `services/packing.py::get_box_source` is:
a property of the request, resolved once, with `clear_store_cache()` for
tests that need to re-resolve within one process.
"""

import frappe

_UNSET = object()

#: The slug a migrated single-store site keeps, so `/store` requires no
#: redirect — see patches.create_default_webstore.
DEFAULT_SLUG = "store"


def current_store():
	if getattr(frappe.local, "webstore_current_store", _UNSET) is _UNSET:
		frappe.local.webstore_current_store = _resolve_store()
	return frappe.local.webstore_current_store


def clear_store_cache():
	"""Tests resolve a different store within one request; production never does."""
	frappe.local.webstore_current_store = _UNSET


def _resolve_store():
	slug = getattr(frappe.local, "webstore_slug", None)
	if slug:
		return _get_by_slug(slug)

	published = frappe.get_all("Webstore", filters={"published": 1}, pluck="name")
	if len(published) == 1:
		return _get_by_slug(published[0])

	return _get_by_slug(DEFAULT_SLUG)


def _get_by_slug(slug):
	if frappe.db.exists("Webstore", slug):
		return frappe.get_cached_doc("Webstore", slug)
	return None
