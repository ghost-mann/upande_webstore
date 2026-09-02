"""Seasonal overlays applied on top of a site's own theme.

An occasion is a shipped file, never a per-site record: one app serves many
farms, so Valentine's is authored once and reused. Activating one writes
nothing to Webstore Settings — the overlay resolves at render time, so
switching it off is clearing a field and a campaign can never damage the base
theme it sits on.
"""

import json
import os
import re

import frappe

from upande_webstore.services.access import require_permission

SCHEMA_VERSION = 1

OCCASION_DIR = os.path.join(os.path.dirname(__file__), "occasions")
NAME_RE = re.compile(r"^[a-z0-9_]+$")

# Seeds an occasion may set, grouped so a group is taken or left whole. Mona
# seeds accent_soft explicitly, and without atomic groups that blue tint would
# survive under an occasion's red accent.
SEED_GROUPS = {
	"accent": ("accent", "accent_dark", "accent_soft"),
	"surface": ("canvas", "wash"),
}

SEED_FIELDS = frozenset(field for group in SEED_GROUPS.values() for field in group)

# occasion hero key -> Webstore Settings branding field
HERO_FIELDS = {
	"eyebrow": "hero_eyebrow",
	"heading": "hero_heading",
	"heading_em": "hero_heading_em",
	"body": "hero_body",
	"cta_primary": "hero_cta_primary",
}

BANNER_FIELDS = ("text", "cta_label", "cta_url")

# farm override field -> the banner key it replaces
BANNER_OVERRIDES = {
	"occasion_banner_text": "text",
	"occasion_banner_cta_label": "cta_label",
	"occasion_banner_cta_url": "cta_url",
}


def list_names():
	if not os.path.isdir(OCCASION_DIR):
		return []
	return sorted(
		filename[: -len(".json")]
		for filename in os.listdir(OCCASION_DIR)
		if filename.endswith(".json")
	)


def load(name):
	"""The validated occasion, or None if it cannot be used.

	Returns None rather than raising at every failure: a storefront must not
	500 because a farm points at an occasion this app version stopped shipping.
	The caller decides whether a given None is worth logging.
	"""
	# the regex rejects '/', '.' and '%' outright, so no path can escape the dir
	if not isinstance(name, str) or not NAME_RE.match(name):
		return None
	path = os.path.join(OCCASION_DIR, f"{name}.json")
	if not os.path.isfile(path):
		return None
	try:
		with open(path, encoding="utf-8") as handle:
			raw = json.load(handle)
	except (OSError, ValueError):
		return None
	if not isinstance(raw, dict) or raw.get("schema") != SCHEMA_VERSION:
		return None

	seeds = raw.get("seeds") or {}
	banner = raw.get("banner") or {}
	hero = raw.get("hero") or {}
	return {
		"name": name,
		"label": raw.get("label") or name,
		# the whitelist is what stops a shipped file reaching custom_css, the
		# status colours or the type scale on every farm running this app
		"seeds": {k: v for k, v in seeds.items() if k in SEED_FIELDS and v},
		"banner": {k: v for k, v in banner.items() if k in BANNER_FIELDS and v},
		"hero": {k: v for k, v in hero.items() if k in HERO_FIELDS and v},
	}


def _expired(settings):
	runs_until = settings.get("occasion_runs_until")
	if not runs_until:
		return False
	# inclusive: an occasion set to run until today is still live today
	return frappe.utils.getdate(runs_until) < frappe.utils.getdate(frappe.utils.nowdate())


def active(settings=None):
	"""The occasion in force, or None. Never raises."""
	if settings is None:
		from upande_webstore.services.settings import get_settings

		settings = get_settings()

	name = (settings.get("occasion") or "").strip()
	if not name or _expired(settings):
		return None

	resolved = load(name)
	if resolved is None:
		# named but unusable, which is worth a log — unlike a blank field
		frappe.log_error(f"Webstore occasion {name!r} could not be loaded", "Webstore Occasion")
		return None

	banner = dict(resolved["banner"])
	for field, key in BANNER_OVERRIDES.items():
		value = (settings.get(field) or "").strip()
		if value:
			banner[key] = value
	# a CTA needs both halves — a bare URL renders a link with no words
	if not (banner.get("cta_url") and banner.get("cta_label")):
		banner.pop("cta_url", None)
		banner.pop("cta_label", None)
	# wording is the banner; a CTA alone has nothing to sit beside
	resolved["banner"] = banner if banner.get("text") else {}
	return frappe._dict(resolved)


@frappe.whitelist()
def list_occasions():
	"""[{value, label}] for the desk Autocomplete."""
	require_permission("Webstore Settings")
	return [
		{"value": name, "label": (load(name) or {}).get("label") or name} for name in list_names()
	]
