"""Store resolution.

`current_store()` resolves from an explicit override (`frappe.local.webstore_slug`)
plus the shapes a real site can be in today: exactly one storefront (the common
case, and every migrated site), or the migrated default itself. Every other
consumer — `services.settings` included — reads `current_store()` rather than
working any of this out again. None of that logic changes here.

Cached on `frappe.local` exactly as `services/packing.py::get_box_source` is:
a property of the request, resolved once, with `clear_store_cache()` for
tests that need to re-resolve within one process.

What Task 2 adds alongside it: `resolve_webstore_prefix()`, the before_request
hook that sets `frappe.local.webstore_slug` from the inbound path (or, for an
API call the storefront's own JS makes, from the page that called it), and
`current_store_or_404()`, which enforces the one rule `current_store()`
deliberately does not - a slug that was explicitly given in a URL and does not
resolve, or resolves to a store nobody but a System Manager may preview, is a
404, never a silent fall-through to the default store.
"""

import re
from urllib.parse import urlparse

import frappe

_UNSET = object()

#: The slug a migrated single-store site keeps, so `/store` requires no
#: redirect — see patches.create_default_webstore.
DEFAULT_SLUG = "store"

#: A storefront path always starts <slug>/(store|cart|wishlist) - matches the
#: listing/cart/wishlist pages themselves and any deeper path under `store`
#: (a product's own detail route). The bare, unprefixed /store, /cart and
#: /wishlist have only one segment and never match, so the default store's
#: existing URLs are untouched by this pattern.
_PREFIXED_PAGE = re.compile(r"^([a-z0-9][a-z0-9-]*)/(?:store|cart|wishlist)(?:/.*)?$")


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


def _slug_from_path(path):
	match = _PREFIXED_PAGE.match((path or "").strip("/"))
	return match.group(1) if match else None


def resolve_webstore_prefix():
	"""before_request hook: read the store slug off the inbound path before
	any routing or page rendering happens, so it is already on
	`frappe.local` by the time anything calls `current_store()`.

	A storefront page carries its slug in its own path (`/flowers/cart`).
	The storefront's own JS, though, calls its API from that page
	(`/api/method/...`), which carries no slug of its own - the one place
	that path still is is the Referer, so an API request falls back to it.
	Anything else (the desk, `/portal`, a request with neither) leaves
	`webstore_slug` unset, and `current_store()` falls back to its own
	single-store/default-slug logic exactly as before this hook existed.
	"""
	path = (frappe.request.path or "").strip("/") if frappe.request else ""
	slug = _slug_from_path(path)
	if not slug and path.startswith("api/"):
		referer = frappe.request.headers.get("Referer") or ""
		slug = _slug_from_path(urlparse(referer).path)
	if slug:
		frappe.local.webstore_slug = slug


def current_store_or_404():
	"""`current_store()`, but for a request whose path carried an explicit
	slug: unknown or unpublished must 404 rather than quietly fall back to
	the default store - published is also waived for a System Manager, who
	may preview a store before it goes live.

	A request with no slug (today's bare /store, /cart, /wishlist) never
	reaches the check below; `current_store()`'s own ambiguous-fallback
	logic (Task 1, unchanged) decides those exactly as it always has.
	"""
	slug = getattr(frappe.local, "webstore_slug", None)
	store = current_store()
	if not slug:
		return store
	if not store or (not store.published and "System Manager" not in frappe.get_roles()):
		raise frappe.PageDoesNotExistError
	return store


def storefront_path(page):
	"""The current store's URL for one of its own pages (`cart`, `wishlist`,
	`store`).

	The default store keeps the bare `/cart`; any other store's page lives
	under its slug. Used for the guest login redirect, which would otherwise
	send a shopper on /flowers/cart back to the default store's cart after
	they log in.
	"""
	slug = getattr(frappe.local, "webstore_slug", None)
	if not slug or slug == DEFAULT_SLUG:
		return f"/{page}"
	return f"/{slug}/{page}"
