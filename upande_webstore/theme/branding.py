"""Brand copy resolution.

Every fallback string lives in DEFAULTS — one readable place, replacing the
`or '...'` literals that were scattered across five templates.
"""

from urllib.parse import quote

import frappe

SHIPPED_LOGO = "/assets/upande_webstore/images/upande-logo.png"
SHIPPED_HERO = "/assets/upande_webstore/images/site/hero.jpg"

DEFAULTS = {
	# identity
	"site_name": "Upande Store",
	"wordmark": "upande",
	"wordmark_bold": "store",
	"wordmark_subtitle": "Store & Customer Portal",
	# hero
	"hero_eyebrow": "Upande · Nairobi · Est. for growers",
	"hero_heading": "The harvest,",
	"hero_heading_em": "straight from the farm gate",
	"hero_body": (
		"Export-grade roses from Kenyan growers — standard and spray varieties, "
		"graded by stem length, quotation-first ordering with cold chain to your door."
	),
	"hero_cta_primary": "Browse the catalog",
	"hero_cta_secondary_guest": "Open a trade account",
	"hero_cta_secondary_member": "Go to your portal",
	# footer
	"footer_tagline": (
		"Export-grade roses from Kenyan growers — ordered online, confirmed by "
		"people who know the farms."
	),
	"footer_contact_email": "sales@upande.com",
	"footer_hours": "Mon–Sat, 07:00–17:00 EAT",
	"footer_location": "Nairobi, Kenya",
	"footer_website": "https://upande.com",
	"footer_copyright": "Upande Ltd.",
	"footer_note": "Quotation-first ordering · No payment taken online",
	# portal
	"portal_eyebrow": "Upande Store · Customer Portal",
}

IMAGE_DEFAULTS = {"brand_logo": SHIPPED_LOGO, "hero_image": SHIPPED_HERO, "favicon": None}


def _card_image(row):
	"""The row's own image, else the Item Group's.

	A card's Category *is* an Item Group, so a picture set there is the natural
	place to look — mirrors how a product falls back to the Item's photo.
	"""
	if row.get("image"):
		return row.get("image")
	category = row.get("category")
	if category and frappe.db.exists("Item Group", category):
		return frappe.get_cached_value("Item Group", category, "image") or None
	return None


def _card_href(row):
	if row.get("url"):
		return row.get("url")
	category = row.get("category")
	return f"/store?category={quote(category)}" if category else "/store"


def get_branding(settings=None):
	if settings is None:
		from upande_webstore.services.settings import get_settings

		settings = get_settings()

	resolved = frappe._dict()
	for key, default in DEFAULTS.items():
		value = settings.get(key)
		resolved[key] = value.strip() if isinstance(value, str) and value.strip() else default
	for key, default in IMAGE_DEFAULTS.items():
		resolved[key] = settings.get(key) or default

	resolved.hero_stats = [
		{"value": row.value, "label": row.label} for row in (settings.get("hero_stats") or [])
	]
	resolved.category_cards = [
		{
			"label": row.label,
			"subtitle": row.subtitle or "",
			"image": _card_image(row),
			"href": _card_href(row),
		}
		for row in (settings.get("category_cards") or [])
	]

	# group footer rows by heading, preserving first-appearance column order
	columns = []
	index = {}
	for row in settings.get("footer_links") or []:
		if row.column not in index:
			index[row.column] = len(columns)
			columns.append({"heading": row.column, "links": []})
		columns[index[row.column]]["links"].append({"label": row.label, "url": row.url})
	resolved.footer_columns = columns

	return resolved
