"""Pure color math for the webstore theme.

Imports nothing from Frappe so the derivation is testable as plain functions.
`mix()` returns unrounded floats and only `to_hex()` rounds, so chained mixes
do not accumulate rounding error.
"""

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Fractions along ink -> canvas at which each ink token sits. Derived from the
# shipped hand-tuned scale; see the spec for the measured divergence.
INK_STEPS = (0.000, 0.068, 0.137, 0.205, 0.342)  # ink, ink-1 .. ink-4
INK_MUTE = 0.547
INK_FAINT = 0.744

# Alphas the shipped SCSS used as literal rgba(10, 10, 10, N).
WASH_ALPHA = 0.04
HAIRLINE_ALPHA = 0.06
HAIRLINE_STRONG_ALPHA = 0.12
RING_ALPHA = 0.35


def parse(value):
	"""'#rrggbb' -> (r, g, b); anything else -> None. Shorthand is rejected."""
	if not isinstance(value, str):
		return None
	value = value.strip()
	if len(value) != 7 or not value.startswith("#"):
		return None
	try:
		return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
	except ValueError:
		return None


def to_hex(rgb):
	"""Round and clamp to a '#rrggbb' string."""
	return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def mix(rgb, target, amount):
	"""Linear blend toward target. amount 0 -> rgb, 1 -> target. Unrounded."""
	return tuple(c + (t - c) * amount for c, t in zip(rgb, target))


def rgba(rgb, alpha):
	r, g, b = (round(c) for c in rgb)
	return f"rgba({r}, {g}, {b}, {alpha})"


def ink_scale(ink, muted, canvas):
	"""The seven ink tokens.

	Two-segment interpolation: `muted` anchors position INK_MUTE so the
	temperature of the most-visible gray is set directly rather than falling out
	of the arithmetic. Without a muted seed the segments collapse algebraically
	to the single ink -> canvas ramp.
	"""
	if not ink:
		return {}
	if muted is None:
		muted = mix(ink, canvas, INK_MUTE)
	scale = {}
	for name, step in zip(("ink", "ink-1", "ink-2", "ink-3", "ink-4"), INK_STEPS):
		scale[name] = to_hex(mix(ink, muted, step / INK_MUTE))
	scale["ink-mute"] = to_hex(muted)
	scale["ink-faint"] = to_hex(mix(muted, canvas, (INK_FAINT - INK_MUTE) / (1 - INK_MUTE)))
	return scale


def surface_scale(ink, canvas, wash, border, border_strong):
	"""Surfaces, hairlines and the three shadow strings.

	Shadows use the ink seed at the alphas the SCSS hardcoded, so a navy-ink
	project gets navy-tinted shadows instead of black ones.
	"""
	if not canvas and not ink:
		return {}
	ink = ink or (10, 10, 10)
	scale = {}
	if canvas:
		scale["bg"] = to_hex(canvas)
		# --ws-surface is a LIFT above the canvas, never below it.
		scale["surface"] = to_hex(mix(canvas, WHITE, 0.5))
		scale["card"] = "#ffffff"
	scale["wash"] = to_hex(wash) if wash else rgba(ink, WASH_ALPHA)
	scale["hairline"] = to_hex(border) if border else rgba(ink, HAIRLINE_ALPHA)
	scale["hairline-strong"] = (
		to_hex(border_strong) if border_strong else rgba(ink, HAIRLINE_STRONG_ALPHA)
	)
	scale["shadow-card"] = f"0 1px 0 {rgba(ink, 0.04)}, 0 8px 32px -16px {rgba(ink, 0.1)}"
	scale["shadow-hover"] = f"0 1px 0 {rgba(ink, 0.06)}, 0 24px 48px -24px {rgba(ink, 0.18)}"
	scale["shadow-lg"] = f"0 24px 60px -18px {rgba(ink, 0.28)}"
	return scale


def accent_scale(accent, dark, soft):
	"""The six accent tokens. `dark` and `soft` override their derivations."""
	if not accent:
		return {}
	deep = dark or mix(accent, BLACK, 0.25)
	return {
		"accent": to_hex(accent),
		# when an explicit dark is given, hover sits between accent and it
		"accent-hover": to_hex(mix(accent, dark, 0.6) if dark else mix(accent, BLACK, 0.12)),
		"accent-soft": to_hex(soft) if soft else to_hex(mix(accent, WHITE, 0.92)),
		"accent-light": to_hex(mix(accent, WHITE, 0.25)),
		"accent-deep": to_hex(deep),
		"ring": rgba(accent, RING_ALPHA),
	}


def status_scale(seed):
	"""One semantic status family.

	`light` exists because the shipped warning pair is two-tone: --ws-warning is
	the dark text shade and --ws-warning-mid the brighter fill.
	"""
	if not seed:
		return {}
	return {
		"base": to_hex(seed),
		"deep": to_hex(mix(seed, BLACK, 0.12)),
		"light": to_hex(mix(seed, WHITE, 0.25)),
		"soft": rgba(seed, 0.12),
	}
