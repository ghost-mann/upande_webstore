"""Brand copy resolution.

Every fallback string lives in DEFAULTS — one readable place, replacing the
`or '...'` literals that were scattered across five templates.
"""

from urllib.parse import quote

import frappe

SHIPPED_LOGO = "/assets/upande_webstore/images/upande-logo.png"

# the three steps the storefront used to hardcode
SHIPPED_PROCESS_STEPS = (
	{
		"title": "Build your basket",
		"description": "Browse live availability and wholesale pack sizes. Your prices appear automatically once your account is linked.",
	},
	{
		"title": "Ask for a quotation",
		"description": "Send your basket with a PO reference. Our team confirms pricing, availability and freight within 24 hours.",
	},
	{
		"title": "Accept & receive",
		"description": "Accept online from your portal. We pack to order and ship cold chain, with documents in your portal.",
	},
)
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
	# how ordering works
	"process_eyebrow": "How ordering works",
	"process_heading": "From your basket to a",
	"process_heading_em": "confirmed quotation in one working day",
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


def get_branding(settings=None, occasion=None):
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

	# empty table = the shipped three steps, so an unconfigured site keeps the
	# band it has always had; clearing it deliberately is done with the flag
	steps = [
		{"title": row.title, "description": row.description}
		for row in (settings.get("process_steps") or [])
		if (row.title or "").strip()
	]
	resolved.process_steps = steps or [dict(step) for step in SHIPPED_PROCESS_STEPS]

	# the occasion speaks last: an overlay whose whole purpose is seasonal copy
	# has to beat the evergreen hero a farm keeps the rest of the year
	if occasion:
		from upande_webstore.theme.occasion import HERO_FIELDS

		hero = occasion.get("hero") or {}
		for key, field in HERO_FIELDS.items():
			if hero.get(key):
				resolved[field] = hero[key]

	return resolved
