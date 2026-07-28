import frappe


def get_settings():
	return frappe.get_cached_doc("Webstore Settings")


def get_warehouses():
	return [row.warehouse for row in get_settings().warehouses]


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
	# retained one release for anything still reading the old key
	context.webstore_appearance = get_appearance()
