"""Assemble the --ws-* override set from the settings seeds.

Returns bare token names (no '--ws-' prefix); the template adds it. An empty
dict means nothing is configured, so no <style> block is emitted at all.
"""

from upande_webstore.theme import color, fonts

DEFAULT_CANVAS = (244, 243, 239)

# Every settings field this module reads. Owned here because this is what
# consumes them; theme/transfer.py imports this list rather than duplicating it.
THEME_FIELDS = (
	"accent",
	"accent_dark",
	"accent_soft",
	"accent_drives_primary",
	"ink",
	"ink_muted",
	"canvas",
	"wash",
	"border",
	"border_strong",
	"success",
	"warning",
	"danger",
	"info",
	"font_sans",
	"font_sans_name",
	"font_display",
	"font_display_name",
	"font_mono",
	"font_mono_name",
	"google_fonts_url",
	"radius",
	"radius_card",
	"radius_panel",
	"custom_css",
)

# the colour subset of THEME_FIELDS — the only seeds an occasion can move
COLOR_FIELDS = (
	"accent",
	"accent_dark",
	"accent_soft",
	"ink",
	"ink_muted",
	"canvas",
	"wash",
	"border",
	"border_strong",
	"success",
	"warning",
	"danger",
	"info",
)

# seed fieldname -> ((scss token, derivation key), ...)
# The token names differ from the field names where the SCSS already had its own
# vocabulary: 'danger' fills the 'destructive' tokens, and warning is two-tone
# (dark text + brighter fill) rather than base + deep.
STATUS_TOKENS = {
	"success": (("success", "base"), ("success-deep", "deep"), ("success-soft", "soft")),
	"warning": (("warning", "base"), ("warning-mid", "light"), ("warning-soft", "soft")),
	"danger": (("destructive", "base"), ("destructive-soft", "soft")),
	"info": (("info", "base"), ("info-deep", "deep"), ("info-soft", "soft")),
}

SHAPE_FIELDS = (
	("radius", "radius"),
	("radius_card", "radius-card"),
	("radius_panel", "radius-panel"),
)

FONT_TOKENS = (("sans", "font-sans"), ("display", "display"), ("mono", "font-mono"))


def _seed(values, field):
	return color.parse(values.get(field))


def _seed_values(settings, active_occasion):
	"""Colour seeds after the occasion overlay.

	Groups are replaced whole: an occasion that sets `accent` owns accent_dark
	and accent_soft too, blank meaning re-derive. Merging here rather than over
	the finished tokens is what makes the derived ramp — hover, deep, ring and
	the contrast-picked on-accent — follow the occasion instead of the farm.
	"""
	values = {field: settings.get(field) for field in COLOR_FIELDS}
	if not active_occasion:
		return values

	from upande_webstore.theme.occasion import SEED_GROUPS

	seeds = active_occasion.get("seeds") or {}
	for group in SEED_GROUPS.values():
		if any(seeds.get(field) for field in group):
			for field in group:
				values[field] = seeds.get(field) or ""
	return values


def get_tokens(settings, occasion=None):
	out = {}
	values = _seed_values(settings, occasion)

	ink = _seed(values, "ink")
	canvas = _seed(values, "canvas")
	muted = _seed(values, "ink_muted")

	ink_scale = color.ink_scale(ink, muted, canvas or DEFAULT_CANVAS)
	out.update(ink_scale)
	out.update(
		color.surface_scale(
			ink,
			canvas,
			_seed(values, "wash"),
			_seed(values, "border"),
			_seed(values, "border_strong"),
		)
	)

	accent = _seed(values, "accent")
	out.update(
		color.accent_scale(accent, _seed(values, "accent_dark"), _seed(values, "accent_soft"))
	)

	# Text laid over the CTA gradient, which runs accent-deep -> accent. Judged
	# against both ends so neither fails, and deliberately pure black or pure
	# white rather than the ink/canvas tones — on a saturated fill those read as
	# washed-out grey, and the pure values also measure better.
	if accent:
		deep = color.parse(out["accent-deep"])
		out["on-accent"] = color.to_hex(
			color.best_contrast((deep, accent), (color.BLACK, color.WHITE))
		)

	for field, mapping in STATUS_TOKENS.items():
		family = color.status_scale(_seed(values, field))
		if not family:
			continue
		for token, key in mapping:
			out[token] = family[key]

	# the ink gradient follows the ink seed so it is not stuck on shipped black
	if ink_scale:
		out["grad-ink"] = (
			f"linear-gradient(135deg, {ink_scale['ink']} 0%, {ink_scale['ink-3']} 100%)"
		)

	# accent drives primary actions: remap the action-surface aliases
	if settings.get("accent_drives_primary") and accent:
		out["primary"] = "var(--ws-accent)"
		out["primary-hover"] = "var(--ws-accent-hover)"
		out["primary-soft"] = "var(--ws-accent-soft)"
		out["grad-ink"] = "linear-gradient(135deg, var(--ws-accent-deep) 0%, var(--ws-accent) 100%)"

	for field, token in SHAPE_FIELDS:
		value = settings.get(field)
		if value:
			out[token] = str(value).strip()

	resolved = fonts.resolve(settings)
	for role, token in FONT_TOKENS:
		if resolved[role]:
			out[token] = resolved[role]

	return out


def get_custom_css(settings):
	return (settings.get("custom_css") or "").strip()
