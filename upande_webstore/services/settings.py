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
	rgb = _parse_hex(primary)
	if not rgb:
		return {}
	return {
		"primary": _to_hex(rgb),
		"primary_hover": _to_hex(_mix(rgb, (0, 0, 0), 0.12)),
		"primary_soft": _to_hex(_mix(rgb, (255, 255, 255), 0.92)),
		"ring": "rgba({}, {}, {}, 0.35)".format(*rgb),
	}


def get_appearance():
	settings = get_settings()
	appearance = {field: settings.get(field) or None for field in APPEARANCE_IMAGE_FIELDS}
	appearance["colors"] = derive_brand_colors(settings.get("primary_color"))
	return appearance


def update_website_context(context):
	context.webstore_appearance = get_appearance()
