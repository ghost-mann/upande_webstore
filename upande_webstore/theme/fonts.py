"""Font family resolution.

Shipped families are self-hosted woff2; anything else comes from a Google Fonts
stylesheet, whose host is validated so this field cannot inject an arbitrary
remote origin into every page's <head>.
"""

from urllib.parse import urlparse

ALLOWED_FONT_HOST = "fonts.googleapis.com"

SHIPPED_SANS = ["Poppins"]
SHIPPED_DISPLAY = ["Fraunces"]
SHIPPED_MONO = ["IBM Plex Mono"]

STACKS = {
	"Poppins": '"Poppins", -apple-system, "Segoe UI", sans-serif',
	"Fraunces": '"Fraunces", Georgia, serif',
	"IBM Plex Mono": '"IBM Plex Mono", ui-monospace, monospace',
}

FALLBACKS = {
	"sans": '-apple-system, "Segoe UI", sans-serif',
	"display": "Georgia, serif",
	"mono": "ui-monospace, monospace",
}


def is_allowed_url(url):
	"""True only for an https URL whose host is exactly fonts.googleapis.com."""
	if not isinstance(url, str) or not url.strip():
		return False
	try:
		parsed = urlparse(url.strip())
	except ValueError:
		return False
	return parsed.scheme == "https" and parsed.netloc == ALLOWED_FONT_HOST


def _stack(role, choice, custom_name):
	if not choice:
		return None
	if choice != "Custom":
		return STACKS.get(choice)
	if not custom_name:
		return None
	return f'"{custom_name}", {FALLBACKS[role]}'


def resolve(settings):
	"""-> {sans, display, mono, link}; each value None when unconfigured."""
	url = settings.get("google_fonts_url")
	return {
		"sans": _stack("sans", settings.get("font_sans"), settings.get("font_sans_name")),
		"display": _stack(
			"display", settings.get("font_display"), settings.get("font_display_name")
		),
		"mono": _stack("mono", settings.get("font_mono"), settings.get("font_mono_name")),
		"link": url.strip() if is_allowed_url(url) else None,
	}
