import frappe

from upande_webstore.services.store_fields import (
	PER_STORE_SCALARS,
	PER_STORE_TABLES,
	PER_STORE_TRISTATE,
	TRISTATE_OPTIONS,
)


def get_settings():
	"""The site Single, overlaid with the resolved store's non-empty values.

	Signature and return shape are unchanged on purpose: 23 call sites read
	this via attribute and `.get()` access and iterate its child tables, and
	must keep working whether or not `Webstore` rows exist at all. A site with
	no store resolved (there is no Webstore row yet, or none matches) gets
	back the Single exactly as before this feature existed — the identical
	cached object, not a copy — which is what keeps a single-store site's
	behaviour provably unchanged.
	"""
	singles = frappe.get_cached_doc("Webstore Settings")

	from upande_webstore.services.store import current_store

	store = current_store()
	if not store:
		return singles

	# Merging builds a whole Document out of ~140 fields and seven child
	# tables, and a single page render asks for the settings dozens of times.
	# Keyed on both documents' timestamps rather than just the store name, so
	# a save to either one invalidates it without anything having to remember
	# to clear a cache.
	key = (store.name, str(store.modified), str(singles.modified))
	cached = getattr(frappe.local, "webstore_merged_settings", None)
	if cached and cached[0] == key:
		return cached[1]
	merged = _merge(singles, store)
	frappe.local.webstore_merged_settings = (key, merged)
	return merged


def _is_set(value):
	"""Non-empty for both text fields (blank string) and Int fields (0 is
	their unset state) — every per-store field's own description documents
	0/blank as "inherit"."""
	return value not in (None, "", 0, "0")


def _merge(singles, store):
	"""A store's non-empty scalars and non-empty tables over the Single.

	Built as a fresh, unsaved Document from the Single's own dict rather than
	mutating the cached Single in place - that object is shared by every
	request until the next cache clear, and corrupting it would leak one
	store's overrides into every other request on the site.
	"""
	merged = frappe.get_doc(singles.as_dict())
	for field in PER_STORE_SCALARS:
		value = store.get(field)
		if _is_set(value):
			merged.set(field, value)
	for field in PER_STORE_TRISTATE:
		choice = TRISTATE_OPTIONS.get(store.get(field))
		if choice is not None:
			merged.set(field, choice)
	for field in PER_STORE_TABLES:
		rows = store.get(field) or []
		if rows:
			merged.set(field, [row.as_dict(no_default_fields=True) for row in rows])
	return merged


def get_warehouses():
	return [row.warehouse for row in get_settings().warehouses]


# Select options on Webstore Settings.checkout_mode. Blank (a site that has
# never touched the field) reads as CHECKOUT_MODE_BUYER_CHOOSES so an existing
# install's cart page is unchanged by this setting existing at all.
CHECKOUT_MODE_BUYER_CHOOSES = "Buyer chooses"
CHECKOUT_MODE_QUOTATION_ONLY = "Quotation only"
CHECKOUT_MODE_ORDER_ONLY = "Sales order only"


def get_checkout_mode(settings=None):
	"""The farm's resolved checkout_mode, blank folded to Buyer chooses."""
	settings = settings or get_settings()
	return (settings.get("checkout_mode") or "").strip() or CHECKOUT_MODE_BUYER_CHOOSES


def checkout_mode_permits(mode, settings=None):
	"""Whether a checkout `mode` ("quotation"/"order") may be used at all.

	The button is only presentation; this is the check `place_order` re-runs
	server-side so a client cannot post a mode the farm has switched off just
	because the button that would have hidden it never rendered.
	"""
	resolved = get_checkout_mode(settings)
	if resolved == CHECKOUT_MODE_QUOTATION_ONLY:
		return mode == "quotation"
	if resolved == CHECKOUT_MODE_ORDER_ONLY:
		return mode == "order"
	return True


APPEARANCE_IMAGE_FIELDS = (
	"brand_logo",
	"hero_image",
	"flowers_category_image",
	"coffee_category_image",
	"produce_category_image",
)


def _parse_hex(value):
	"""'#rrggbb' -> (r, g, b), else None. Shorthand/invalid values are rejected."""
	if not isinstance(value, str):
		return None
	value = value.strip()
	if len(value) != 7 or not value.startswith("#"):
		return None
	try:
		return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
	except ValueError:
		return None


def _mix(rgb, target, amount):
	return tuple(round(channel + (t - channel) * amount) for channel, t in zip(rgb, target))


def _to_hex(rgb):
	return "#%02x%02x%02x" % rgb


def derive_brand_colors(primary):
	"""The configured color is the storefront *accent* (default gold);
	ink neutrals are fixed. Light/deep endpoints feed the accent gradient."""
	rgb = _parse_hex(primary)
	if not rgb:
		return {}
	return {
		"primary": _to_hex(rgb),
		"primary_hover": _to_hex(_mix(rgb, (0, 0, 0), 0.12)),
		"primary_soft": _to_hex(_mix(rgb, (255, 255, 255), 0.92)),
		"primary_light": _to_hex(_mix(rgb, (255, 255, 255), 0.25)),
		"primary_deep": _to_hex(_mix(rgb, (0, 0, 0), 0.25)),
		"ring": "rgba({}, {}, {}, 0.35)".format(*rgb),
	}


def get_appearance():
	settings = get_settings()
	appearance = {field: settings.get(field) or None for field in APPEARANCE_IMAGE_FIELDS}
	appearance["colors"] = derive_brand_colors(settings.get("primary_color"))
	return appearance


def update_website_context(context):
	from upande_webstore.theme import get_theme

	theme = get_theme(get_settings())
	context.webstore_tokens = theme.tokens
	context.webstore_custom_css = theme.custom_css
	context.webstore_font_link = theme.font_link
	context.webstore_branding = theme.branding
	context.webstore_features = theme.features
	context.webstore_occasion = theme.occasion
	# retained one release for anything still reading the old key
	context.webstore_appearance = get_appearance()

	from upande_webstore.services.pricing import get_guest_currency_picker

	context.webstore_currency = get_guest_currency_picker()

	# Every storefront link used to be the literal "/store". On /flowers/store
	# that navigates the shopper into the default store's catalogue — a
	# different shop — so the templates read these instead of hardcoding a
	# path. The default store's values are the bare paths, so nothing about a
	# single-store site's markup changes.
	from upande_webstore.services.store import storefront_path

	context.webstore_urls = frappe._dict(
		store=storefront_path("store"),
		cart=storefront_path("cart"),
		wishlist=storefront_path("wishlist"),
	)
