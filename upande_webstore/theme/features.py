"""One registry driving all three enforcement layers, so a flag cannot be
enforced in one place and forgotten in another."""

import functools
from collections import namedtuple

import frappe
from frappe import _

Feature = namedtuple("Feature", ["key", "fieldname", "label", "group"])


def _f(key, label, group):
	return Feature(key, f"enable_{key}", label, group)


FEATURES = (
	# storefront — 9
	_f("cart", "Cart & Checkout", "storefront"),
	_f("wishlist", "Wishlist", "storefront"),
	_f("signup", "Signup", "storefront"),
	_f("search_palette", "Search Palette", "storefront"),
	_f("cart_drawer", "Cart Drawer", "storefront"),
	_f("hero", "Hero", "storefront"),
	_f("hero_stats", "Hero Stats", "storefront"),
	_f("category_cards", "Category Cards", "storefront"),
	_f("footer", "Footer", "storefront"),
	# portal — 10
	_f("portal", "Portal", "portal"),
	_f("dashboard", "Dashboard", "portal"),
	_f("quotations", "Quotations", "portal"),
	_f("orders", "Orders", "portal"),
	_f("invoices", "Invoices", "portal"),
	_f("statement", "Statement", "portal"),
	_f("support", "Support", "portal"),
	_f("claims", "Claims", "portal"),
	_f("account", "Account", "portal"),
	_f("sidebar_stats", "Sidebar Stats", "portal"),
)

BY_KEY = {feature.key: feature for feature in FEATURES}


def _is_on(value):
	"""An unset field counts as ON, so a site that predates these fields behaves
	exactly as it did before. Only an explicit 0 disables."""
	if value in (None, ""):
		return True
	try:
		return bool(int(value))
	except (TypeError, ValueError):
		return bool(value)


def enabled():
	"""{key: bool} for every feature."""
	from upande_webstore.services.settings import get_settings

	settings = get_settings()
	return frappe._dict(
		{feature.key: _is_on(settings.get(feature.fieldname)) for feature in FEATURES}
	)


def _blocked(keys):
	flags = enabled()
	for key in keys:
		if key not in BY_KEY:
			raise ValueError(f"unknown webstore feature: {key!r}")
		if not flags[key]:
			return key
	return None


def require(*keys):
	"""Route-level gate. Raises DoesNotExistError, which Frappe renders as 404."""
	blocked = _blocked(keys)
	if blocked:
		raise frappe.DoesNotExistError(f"webstore feature disabled: {blocked}")


def guard(*keys):
	"""API-level gate for whitelisted methods."""

	def decorator(fn):
		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			if _blocked(keys):
				frappe.throw(_("This feature is not enabled."), frappe.PermissionError)
			return fn(*args, **kwargs)

		return wrapper

	return decorator
