"""The shop address: customers on the gateway's address, staff on the ERP.

A site can give its store a customer-facing address of its own (Webstore
Settings > Shop Address), served by the customer gateway - a Cloudflare
Worker that passes only the store, portal and login through to this ERP. The
gateway proves a request came through it by sending the shared secret in
`X-Webstore-Gateway`; anything without it reached the ERP directly.

Site-wide on purpose: every storefront shares one shop address, with its
slug under it (/<slug>/store), so these read the Single, never the
per-store merge get_settings() returns.

See docs/superpowers/specs/2026-10-18-shop-address-design.md.
"""

import hmac
from urllib.parse import urlsplit

import frappe
from frappe import _

GATEWAY_HEADER = "X-Webstore-Gateway"


def _settings():
	return frappe.get_cached_doc("Webstore Settings")


def normalise_shop_address(value):
	"""`https://host` from what an admin typed, or None when blank.

	Raises frappe.ValidationError for anything that isn't a bare https
	origin: a path would make every shop link ambiguous, and plain http would
	put customer sessions on the wire unencrypted."""
	value = (value or "").strip()
	if not value:
		return None
	parts = urlsplit(value)
	if parts.scheme != "https" or not parts.hostname:
		frappe.throw(_("The shop address must start with https:// and name a host."), frappe.ValidationError)
	if parts.path not in ("", "/") or parts.query or parts.fragment:
		frappe.throw(_("The shop address can't include a path - only https:// and the host."), frappe.ValidationError)
	host = parts.hostname.lower()
	return f"https://{host}:{parts.port}" if parts.port else f"https://{host}"


def shop_address():
	value = (_settings().get("shop_address") or "").strip()
	return value.rstrip("/") or None


def shop_enabled():
	return bool(shop_address() and _settings().get("send_customers_to_shop"))


def gateway_secret():
	settings = _settings()
	try:
		return settings.get_password("gateway_secret", raise_exception=False) or None
	except Exception:
		return None


def is_shop_request():
	"""This request came through the gateway: it carries the shared secret.

	Independent of the redirect switch, so the shop can be tried end to end
	before customers are sent to it."""
	if not shop_address():
		return False
	request = getattr(frappe.local, "request", None)
	if not request:
		return False
	sent = request.headers.get(GATEWAY_HEADER) or ""
	secret = gateway_secret()
	if not sent or not secret:
		return False
	return hmac.compare_digest(sent.encode(), secret.encode())


def shop_url(path=""):
	path = path or "/"
	if not path.startswith("/"):
		path = "/" + path
	return (shop_address() or "") + path


def is_staff(user):
	"""Staff use the ERP. Any desk account counts, including one that is also
	linked to a customer."""
	if user in ("Administrator",):
		return True
	return frappe.db.get_value("User", user, "user_type") == "System User"


def is_customer_account(user):
	if not user or user in ("Guest", "Administrator"):
		return False
	return not is_staff(user)
