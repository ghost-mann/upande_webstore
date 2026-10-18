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


# Server methods a shop visitor may call through the gateway. Everything else
# under /api/method is refused there. The gateway takes this list from the
# config endpoint, so a new customer-facing method only has to be added here.
CUSTOMER_METHODS = (
	# Frappe's login and account pages
	"login",
	"logout",
	"web_logout",
	"frappe.core.doctype.user.user.reset_password",
	"frappe.core.doctype.user.user.update_password",
	"frappe.core.doctype.user.user.test_password_strength",
	"frappe.www.login.send_login_link",
	"upload_file",  # claim photos
	# Storefront
	"upande_webstore.api.account.add_address",
	"upande_webstore.api.account.sign_up",
	"upande_webstore.api.account.update_profile",
	"upande_webstore.api.cart.add_item",
	"upande_webstore.api.cart.get_box_types",
	"upande_webstore.api.cart.get_cart",
	"upande_webstore.api.cart.get_cart_count",
	"upande_webstore.api.cart.remove_item",
	"upande_webstore.api.cart.set_box_type",
	"upande_webstore.api.cart.update_qty",
	"upande_webstore.api.checkout.place_order",
	"upande_webstore.api.pricing.set_price_list",
	"upande_webstore.api.search.search_products",
	"upande_webstore.api.specs.add_spec",
	"upande_webstore.api.specs.get_my_specs",
	"upande_webstore.api.variants.get_attributes",
	"upande_webstore.api.variants.resolve_variant",
	"upande_webstore.api.wishlist.get_wishlist",
	"upande_webstore.api.wishlist.get_wishlisted_products",
	"upande_webstore.api.wishlist.toggle",
	# Portal
	"upande_webstore.api.claims.create_claim",
	"upande_webstore.api.claims.get_claim",
	"upande_webstore.api.claims.get_claims",
	"upande_webstore.api.claims.get_document_lines",
	"upande_webstore.api.portal.accept_quotation",
	"upande_webstore.api.portal.decline_quotation",
	"upande_webstore.api.portal.download_invoice_pdf",
	"upande_webstore.api.support.create_issue",
)

# Webstore methods the desk uses; never offered on the shop address.
DESK_ONLY_METHODS = (
	"upande_webstore.api.boxes.describe_source",
	"upande_webstore.api.boxes.list_box_types",
	"upande_webstore.api.boxes.list_site_box_records",
	"upande_webstore.api.boxes.load_site_boxes",
	"upande_webstore.api.specs.describe_source",
	"upande_webstore.api.claims.claimable_document_query",
	"upande_webstore.api.claims.claimable_invoice_query",
	"upande_webstore.api.claims.fetch_invoice_lines",
)

# Called by the gateway itself, straight on the ERP address, with the secret.
GATEWAY_METHODS = ("upande_webstore.api.gateway.config",)

DEFAULT_LOGIN_ATTEMPTS = 10


def _lines(value):
	return [line.strip() for line in (value or "").splitlines() if line.strip()]


def gateway_config():
	settings = _settings()
	extra_methods = _lines(settings.get("shop_extra_methods"))
	return {
		"shop_address": shop_address(),
		"send_customers_to_shop": shop_enabled(),
		"login_attempts_per_minute": frappe.utils.cint(settings.get("shop_login_attempts_per_minute"))
		or DEFAULT_LOGIN_ATTEMPTS,
		"allow_indexing": bool(settings.get("shop_allow_indexing")),
		"extra_pages": _lines(settings.get("shop_extra_pages")),
		"methods": list(CUSTOMER_METHODS) + [m for m in extra_methods if m not in CUSTOMER_METHODS],
	}
