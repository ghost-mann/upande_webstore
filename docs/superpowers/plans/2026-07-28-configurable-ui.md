# Configurable UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every per-client visual and structural choice out of code and into `Webstore Settings`, so one branch serves N client projects.

**Architecture:** A new `upande_webstore/theme/` package derives the full `--ws-*` CSS token set from ~13 optional color seeds plus font and radius fields, resolves all brand copy against a single `DEFAULTS` dict, and drives 19 feature flags from one registry enforced at three layers (template / route / API). Tokens reach the browser as an inline `<style>` block in `<head>`, widening the mechanism already in `webstore_base.html`. Theme state round-trips as JSON, with shipped presets for Mona Flowers and Upande.

**Tech Stack:** Frappe/ERPNext v16, Python 3, Jinja2, SCSS (esbuild via `bench build`), `frappe.tests.IntegrationTestCase`.

**Spec:** `docs/superpowers/specs/2026-07-28-configurable-ui-design.md`

## Global Constraints

- **A site with every new field blank must render byte-identically to today.** Every field is optional and falls back to the shipped SCSS value. Asserted by test: a blank settings doc yields `get_tokens() == {}` so **no override block is emitted at all**.
- `theme/color.py` imports **nothing from Frappe** — it is pure functions, testable standalone.
- `mix()` returns **unrounded floats**; only `to_hex()` rounds. Chained mixes must not accumulate rounding error.
- Backward compatibility: `derive_brand_colors("#166534")` must keep returning `primary_hover=#13592e`, `primary_soft=#ecf3ef`, `primary_light=#508c67`, `primary_deep=#104c27`, `ring=rgba(22, 101, 52, 0.35)`. Existing `tests/test_settings.py` must pass **unmodified**.
- `context.webstore_appearance` is retained as an alias for one release; nothing may break mid-migration.
- Malformed/shorthand hex is **treated as unset**, never raises.
- Ink scale constants, used verbatim: `INK_STEPS = (0.000, 0.068, 0.137, 0.205, 0.342)`, `INK_MUTE = 0.547`, `INK_FAINT = 0.744`.
- Derived-vs-shipped ink divergence is bounded at **≤ 8 per channel** (measured worst case is 7, in blue).
- Feature flags all default **on**.
- Google Fonts URL host must be exactly `fonts.googleapis.com`; anything else is rejected on validate.
- Tab indentation in all Python and SCSS files (matches existing codebase).
- Run tests with: `bench --site webstore.localhost run-tests --app upande_webstore --module <module>`

## File Structure

| File | Responsibility |
|---|---|
| `theme/color.py` | **Create.** Pure hex math + scale derivation. No Frappe. |
| `theme/tokens.py` | **Create.** Seeds + fonts + shape → `{--ws-*: value}` dict. |
| `theme/fonts.py` | **Create.** Shipped family list, Google Fonts URL validation + link. |
| `theme/branding.py` | **Create.** `DEFAULTS` dict + `get_branding()`. |
| `theme/features.py` | **Create.** `FEATURES` registry, `enabled()`, `require()`, `guard()`. |
| `theme/transfer.py` | **Create.** `export_theme()`, `import_theme()`, `apply_preset()`. |
| `theme/__init__.py` | **Create.** `get_theme()` — the single context payload. |
| `theme/presets/*.json` | **Create.** `mona_flowers.json`, `upande.json`. |
| `services/settings.py` | **Modify.** Keeps `get_settings`/`get_warehouses`; delegates the rest. |
| `doctype/webstore_settings/webstore_settings.json` | **Modify.** Tabs + ~70 fields. |
| `doctype/webstore_settings/webstore_settings.py` | **Modify.** `validate()` for dependent flags + font URL. |
| `doctype/webstore_settings/webstore_settings.js` | **Create.** Transfer tab buttons. |
| `doctype/webstore_hero_stat/` | **Create.** Child table. |
| `doctype/webstore_category_card/` | **Create.** Child table. |
| `doctype/webstore_footer_link/` | **Create.** Child table. |
| `templates/webstore_base.html` | **Modify.** Token block, branding, feature conditionals. |
| `templates/webstore_portal_base.html` | **Modify.** Sidebar feature conditionals. |
| `www/store.html` | **Modify.** Hero/cards from branding + feature conditionals. |
| `public/scss/webstore.bundle.scss` | **Modify.** Action-surface sweep + `rgba(10,10,10,…)` → `var()`. |
| `services/portal.py` | **Modify.** One-line feature gate in `portal_page_context`. |
| `api/*.py` | **Modify.** `@guard(...)` decorators. |
| `patches/move_category_images_to_table.py` | **Create.** Migration. |
| `tests/test_theme.py` `test_features.py` `test_branding.py` `test_transfer.py` | **Create.** |

**Phasing.** Tasks 1–3 = theme engine, 4–7 = feature flags, 8–12 = branding, 13–14 = transfer/presets, 15 = integration. Each phase leaves the app working and shippable; work can stop cleanly after any phase.

---

## Phase 1 — Theme engine

### Task 1: Pure color math

**Files:**
- Create: `upande_webstore/theme/__init__.py` (empty for now)
- Create: `upande_webstore/theme/color.py`
- Create: `upande_webstore/tests/test_theme.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse(value) -> tuple|None`, `to_hex(rgb) -> str`, `mix(rgb, target, amount) -> tuple[float,...]`, `rgba(rgb, alpha) -> str`, `ink_scale(ink, muted, canvas) -> dict[str,str]`, `surface_scale(ink, canvas, wash, border, border_strong) -> dict[str,str]`, `accent_scale(accent, dark, soft) -> dict[str,str]`, `status_scale(seed) -> dict[str,str]`. Module constants `INK_STEPS`, `INK_MUTE`, `INK_FAINT`, `BLACK`, `WHITE`. All `*_scale` functions take and return **rgb tuples in, hex strings out**, and return `{}` if their primary seed is `None`.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_theme.py`:

```python
import unittest

from upande_webstore.theme import color


class TestColorPrimitives(unittest.TestCase):
	def test_parse_valid(self):
		self.assertEqual(color.parse("#166534"), (22, 101, 52))
		self.assertEqual(color.parse("  #FFFFFF  "), (255, 255, 255))

	def test_parse_rejects_invalid(self):
		for bad in (None, "", "#1f0", "green", "#16653g", 123, "#1665344"):
			self.assertIsNone(color.parse(bad), f"expected None for {bad!r}")

	def test_mix_returns_unrounded_floats(self):
		# chained mixes must not accumulate rounding error
		result = color.mix((0, 0, 0), (255, 255, 255), 0.5)
		self.assertEqual(result, (127.5, 127.5, 127.5))

	def test_to_hex_rounds_and_clamps(self):
		self.assertEqual(color.to_hex((127.5, 0, 255)), "#800000ff"[:7])
		self.assertEqual(color.to_hex((-10, 300, 128)), "#00ff80")

	def test_rgba(self):
		self.assertEqual(color.rgba((22, 101, 52), 0.35), "rgba(22, 101, 52, 0.35)")


class TestInkScale(unittest.TestCase):
	SHIPPED = {
		"ink": "#0a0a0a", "ink-1": "#1a1a18", "ink-2": "#2a2a26", "ink-3": "#3a3a34",
		"ink-4": "#5a5a52", "ink-mute": "#8a8780", "ink-faint": "#b8b6ae",
	}

	def test_collapses_to_single_ramp_without_muted(self):
		"""With muted unset the two segments must reduce EXACTLY to ink->canvas."""
		ink, canvas = (10, 10, 10), (244, 243, 239)
		scale = color.ink_scale(ink, None, canvas)
		expected = {}
		names = ("ink", "ink-1", "ink-2", "ink-3", "ink-4")
		for name, step in zip(names, color.INK_STEPS):
			expected[name] = color.to_hex(color.mix(ink, canvas, step))
		expected["ink-mute"] = color.to_hex(color.mix(ink, canvas, color.INK_MUTE))
		expected["ink-faint"] = color.to_hex(color.mix(ink, canvas, color.INK_FAINT))
		self.assertEqual(scale, expected)

	def test_within_regression_bound_of_shipped(self):
		"""Shipped scale was warm-shifted by eye; bound the divergence at 8."""
		scale = color.ink_scale((10, 10, 10), None, (244, 243, 239))
		for name, shipped_hex in self.SHIPPED.items():
			shipped = color.parse(shipped_hex)
			derived = color.parse(scale[name])
			worst = max(abs(a - b) for a, b in zip(shipped, derived))
			self.assertLessEqual(worst, 8, f"{name}: {shipped_hex} vs {scale[name]}")

	def test_muted_seed_survives_derivation(self):
		"""Mona's blue-shifted muted must be preserved exactly, not flattened."""
		scale = color.ink_scale((26, 26, 26), (135, 140, 156), (247, 248, 250))
		self.assertEqual(scale["ink-mute"], "#878c9c")
		self.assertEqual(scale["ink"], "#1a1a1a")
		# ink-4 sits between ink and muted, so it must be bluer than neutral gray
		r, g, b = color.parse(scale["ink-4"])
		self.assertGreater(b, r, "ink-4 should stay blue-shifted")

	def test_returns_empty_without_ink(self):
		self.assertEqual(color.ink_scale(None, None, (244, 243, 239)), {})


class TestAccentScale(unittest.TestCase):
	def test_backward_compatible_with_derive_brand_colors(self):
		"""These five values are pinned by the existing test_settings suite."""
		scale = color.accent_scale((22, 101, 52), None, None)
		self.assertEqual(scale["accent"], "#166534")
		self.assertEqual(scale["accent-hover"], "#13592e")
		self.assertEqual(scale["accent-soft"], "#ecf3ef")
		self.assertEqual(scale["accent-light"], "#508c67")
		self.assertEqual(scale["accent-deep"], "#104c27")
		self.assertEqual(scale["ring"], "rgba(22, 101, 52, 0.35)")

	def test_explicit_dark_and_soft_override_derivation(self):
		scale = color.accent_scale((30, 77, 140), (20, 53, 98), (232, 240, 251))
		self.assertEqual(scale["accent-deep"], "#143562")
		self.assertEqual(scale["accent-soft"], "#e8f0fb")

	def test_returns_empty_without_accent(self):
		self.assertEqual(color.accent_scale(None, None, None), {})


class TestSurfaceScale(unittest.TestCase):
	def test_opaque_hairlines_when_border_seeds_given(self):
		scale = color.surface_scale(
			(26, 26, 26), (247, 248, 250), (238, 240, 244), (226, 230, 237), (197, 203, 214)
		)
		self.assertEqual(scale["hairline"], "#e2e6ed")
		self.assertEqual(scale["hairline-strong"], "#c5cbd6")
		self.assertEqual(scale["wash"], "#eef0f4")
		self.assertEqual(scale["bg"], "#f7f8fa")

	def test_alpha_hairlines_when_border_seeds_absent(self):
		scale = color.surface_scale((10, 10, 10), (244, 243, 239), None, None, None)
		self.assertEqual(scale["hairline"], "rgba(10, 10, 10, 0.06)")
		self.assertEqual(scale["hairline-strong"], "rgba(10, 10, 10, 0.12)")
		self.assertEqual(scale["wash"], "rgba(10, 10, 10, 0.04)")

	def test_surface_is_a_lift_toward_white(self):
		"""--ws-surface must sit BETWEEN canvas and white, never below canvas."""
		scale = color.surface_scale((26, 26, 26), (247, 248, 250), None, None, None)
		self.assertEqual(scale["surface"], "#fbfcfd")
		self.assertEqual(scale["card"], "#ffffff")

	def test_shadows_use_ink_seed_not_hardcoded_black(self):
		scale = color.surface_scale((30, 77, 140), (247, 248, 250), None, None, None)
		self.assertIn("rgba(30, 77, 140", scale["shadow-card"])


class TestStatusScale(unittest.TestCase):
	def test_derives_deep_and_soft(self):
		scale = color.status_scale((45, 106, 79))
		self.assertEqual(scale["base"], "#2d6a4f")
		self.assertEqual(scale["deep"], "#285d46")
		self.assertEqual(scale["soft"], "rgba(45, 106, 79, 0.12)")

	def test_returns_empty_without_seed(self):
		self.assertEqual(color.status_scale(None), {})
```

Note the deliberate oddity in `test_to_hex_rounds_and_clamps`: `"#800000ff"[:7]` is just `"#800000"` written so the intent (127.5 → 0x80) is visible. Replace with the literal `"#800000"` if you find it clearer.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench/apps/upande_webstore
python3 -m pytest upande_webstore/tests/test_theme.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'upande_webstore.theme'`

(These are pure `unittest.TestCase`, not `IntegrationTestCase`, so plain pytest works without a bench site.)

- [ ] **Step 3: Write minimal implementation**

Create empty `upande_webstore/theme/__init__.py`, then `upande_webstore/theme/color.py`:

```python
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
	scale["shadow-card"] = (
		f"0 1px 0 {rgba(ink, 0.04)}, 0 8px 32px -16px {rgba(ink, 0.1)}"
	)
	scale["shadow-hover"] = (
		f"0 1px 0 {rgba(ink, 0.06)}, 0 24px 48px -24px {rgba(ink, 0.18)}"
	)
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
	"""One semantic status family: base, deep, soft."""
	if not seed:
		return {}
	return {
		"base": to_hex(seed),
		"deep": to_hex(mix(seed, BLACK, 0.12)),
		"soft": rgba(seed, 0.12),
	}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest upande_webstore/tests/test_theme.py -v
```

Expected: PASS, all cases.

If `test_backward_compatible_with_derive_brand_colors` fails, the rounding contract is broken — check that `mix` is not rounding.

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/theme/__init__.py upande_webstore/theme/color.py upande_webstore/tests/test_theme.py
git commit -m "feat(theme): pure color math with seed-anchored ink scale"
```

---

### Task 2: Token assembly and fonts

**Files:**
- Create: `upande_webstore/theme/fonts.py`
- Create: `upande_webstore/theme/tokens.py`
- Modify: `upande_webstore/tests/test_theme.py` (append classes)

**Interfaces:**
- Consumes: everything from `theme/color.py` (Task 1).
- Produces:
  - `fonts.SHIPPED_SANS`, `SHIPPED_DISPLAY`, `SHIPPED_MONO` — lists of family names.
  - `fonts.STACKS` — `dict[str, str]` mapping a family name to its full CSS stack.
  - `fonts.is_allowed_url(url) -> bool` — True only for `fonts.googleapis.com`.
  - `fonts.resolve(settings) -> dict` with keys `sans`, `display`, `mono` (CSS stacks or `None`) and `link` (the Google Fonts URL or `None`).
  - `tokens.get_tokens(settings) -> dict[str, str]` — keys are **bare token names without the `--ws-` prefix** (e.g. `"ink-1"`, `"accent-soft"`, `"grad-ink"`, `"radius-card"`, `"font-sans"`). Returns `{}` when nothing is configured.
  - `tokens.get_custom_css(settings) -> str` — the raw Advanced CSS, or `""`.
  - `settings` is any object supporting `.get(fieldname)` — a Frappe doc or a plain dict, so tests need no database.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_theme.py`:

```python
from upande_webstore.theme import fonts, tokens

MONA = {
	"accent": "#1e4d8c", "accent_dark": "#143562", "accent_soft": "#e8f0fb",
	"ink": "#1a1a1a", "ink_muted": "#878c9c", "canvas": "#f7f8fa",
	"wash": "#eef0f4", "border": "#e2e6ed", "border_strong": "#c5cbd6",
	"success": "#2d6a4f", "warning": "#9a6700", "danger": "#b42318", "info": "#175cd3",
	"accent_drives_primary": 1,
}


class TestFonts(unittest.TestCase):
	def test_shipped_families_have_stacks(self):
		for family in fonts.SHIPPED_SANS + fonts.SHIPPED_DISPLAY + fonts.SHIPPED_MONO:
			self.assertIn(family, fonts.STACKS)

	def test_allows_only_google_fonts_host(self):
		self.assertTrue(fonts.is_allowed_url("https://fonts.googleapis.com/css2?family=Inter"))
		for bad in (
			"https://evil.example.com/css2?family=Inter",
			"https://fonts.googleapis.com.evil.example/css",
			"http://fonts.googleapis.com/css2?family=Inter",  # must be https
			"javascript:alert(1)",
			"", None,
		):
			self.assertFalse(fonts.is_allowed_url(bad), f"expected reject for {bad!r}")

	def test_resolve_blank_returns_nones(self):
		resolved = fonts.resolve({})
		self.assertIsNone(resolved["sans"])
		self.assertIsNone(resolved["link"])

	def test_resolve_custom_family_uses_name_field(self):
		resolved = fonts.resolve({
			"font_sans": "Custom",
			"font_sans_name": "Inter",
			"google_fonts_url": "https://fonts.googleapis.com/css2?family=Inter",
		})
		self.assertTrue(resolved["sans"].startswith('"Inter"'))
		self.assertEqual(resolved["link"], "https://fonts.googleapis.com/css2?family=Inter")


class TestGetTokens(unittest.TestCase):
	def test_blank_settings_emit_nothing(self):
		"""THE safety guarantee: a blank site gets no override block at all."""
		self.assertEqual(tokens.get_tokens({}), {})

	def test_mona_seeds_produce_expected_tokens(self):
		result = tokens.get_tokens(MONA)
		self.assertEqual(result["accent"], "#1e4d8c")
		self.assertEqual(result["accent-deep"], "#143562")
		self.assertEqual(result["accent-soft"], "#e8f0fb")
		self.assertEqual(result["ink"], "#1a1a1a")
		self.assertEqual(result["ink-mute"], "#878c9c")
		self.assertEqual(result["bg"], "#f7f8fa")
		self.assertEqual(result["wash"], "#eef0f4")
		self.assertEqual(result["hairline"], "#e2e6ed")
		self.assertEqual(result["hairline-strong"], "#c5cbd6")
		self.assertEqual(result["success"], "#2d6a4f")
		self.assertEqual(result["info"], "#175cd3")

	def test_accent_drives_primary_remaps_action_tokens(self):
		result = tokens.get_tokens(MONA)
		self.assertEqual(result["primary"], "var(--ws-accent)")
		self.assertEqual(result["primary-hover"], "var(--ws-accent-hover)")
		self.assertEqual(result["primary-soft"], "var(--ws-accent-soft)")
		self.assertIn("var(--ws-accent-deep)", result["grad-ink"])

	def test_primary_untouched_when_flag_off(self):
		off = dict(MONA, accent_drives_primary=0)
		result = tokens.get_tokens(off)
		self.assertNotIn("primary", result)
		self.assertNotIn("grad-ink", result)

	def test_malformed_hex_treated_as_unset(self):
		result = tokens.get_tokens({"accent": "not-a-color", "ink": "#1a1a1a", "canvas": "#f7f8fa"})
		self.assertNotIn("accent", result)
		self.assertEqual(result["ink"], "#1a1a1a")

	def test_shape_and_font_tokens(self):
		result = tokens.get_tokens({
			"radius": "4px", "radius_card": "6px", "radius_panel": "8px",
			"font_sans": "Poppins",
		})
		self.assertEqual(result["radius"], "4px")
		self.assertEqual(result["radius-card"], "6px")
		self.assertEqual(result["radius-panel"], "8px")
		self.assertIn("Poppins", result["font-sans"])

	def test_custom_css_passthrough(self):
		self.assertEqual(tokens.get_custom_css({"custom_css": "--ws-x: 1;"}), "--ws-x: 1;")
		self.assertEqual(tokens.get_custom_css({}), "")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest upande_webstore/tests/test_theme.py -v
```

Expected: FAIL — `ImportError: cannot import name 'fonts'`

- [ ] **Step 3: Write minimal implementation**

Create `upande_webstore/theme/fonts.py`:

```python
"""Font family resolution. Shipped families are self-hosted woff2; anything else
comes from a Google Fonts stylesheet, whose host is validated so this field
cannot inject an arbitrary remote origin into every page's <head>."""

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
		"display": _stack("display", settings.get("font_display"), settings.get("font_display_name")),
		"mono": _stack("mono", settings.get("font_mono"), settings.get("font_mono_name")),
		"link": url.strip() if is_allowed_url(url) else None,
	}
```

Create `upande_webstore/theme/tokens.py`:

```python
"""Assemble the --ws-* override set from the settings seeds.

Returns bare token names (no '--ws-' prefix); the template adds it. An empty
dict means nothing is configured, so no <style> block is emitted at all.
"""

from upande_webstore.theme import color, fonts

STATUS_SEEDS = ("success", "warning", "danger", "info")

# status family -> the SCSS token stems it fills
STATUS_TOKENS = {
	"success": ("success", "success-deep", "success-soft"),
	"warning": ("warning", "warning-mid", "warning-soft"),
	"danger": ("destructive", None, "destructive-soft"),
	"info": ("info", "info-deep", "info-soft"),
}

SHAPE_FIELDS = {"radius": "radius", "radius_card": "radius-card", "radius_panel": "radius-panel"}


def _seed(settings, field):
	return color.parse(settings.get(field))


def get_tokens(settings):
	out = {}

	ink = _seed(settings, "ink")
	canvas = _seed(settings, "canvas")
	out.update(color.ink_scale(ink, _seed(settings, "ink_muted"), canvas or (244, 243, 239)))
	out.update(
		color.surface_scale(
			ink,
			canvas,
			_seed(settings, "wash"),
			_seed(settings, "border"),
			_seed(settings, "border_strong"),
		)
	)

	accent = _seed(settings, "accent")
	out.update(
		color.accent_scale(accent, _seed(settings, "accent_dark"), _seed(settings, "accent_soft"))
	)

	for seed_field in STATUS_SEEDS:
		family = color.status_scale(_seed(settings, seed_field))
		if not family:
			continue
		base, mid, soft = STATUS_TOKENS[seed_field]
		out[base] = family["base"]
		if mid:
			out[mid] = family["deep"] if seed_field != "warning" else family["base"]
		out[soft] = family["soft"]

	# ink gradient follows the ink seed so it is not stuck on shipped black
	if ink:
		scale = color.ink_scale(ink, _seed(settings, "ink_muted"), canvas or (244, 243, 239))
		out["grad-ink"] = f"linear-gradient(135deg, {scale['ink']} 0%, {scale['ink-3']} 100%)"

	# accent drives primary actions: remap the action-surface aliases
	if settings.get("accent_drives_primary") and accent:
		out["primary"] = "var(--ws-accent)"
		out["primary-hover"] = "var(--ws-accent-hover)"
		out["primary-soft"] = "var(--ws-accent-soft)"
		out["grad-ink"] = "linear-gradient(135deg, var(--ws-accent-deep) 0%, var(--ws-accent) 100%)"

	for field, token in SHAPE_FIELDS.items():
		value = settings.get(field)
		if value:
			out[token] = str(value).strip()

	resolved = fonts.resolve(settings)
	for role, token in (("sans", "font-sans"), ("display", "display"), ("mono", "font-mono")):
		if resolved[role]:
			out[token] = resolved[role]

	return out


def get_custom_css(settings):
	return (settings.get("custom_css") or "").strip()
```

Note: `surface_scale` is called with the raw `canvas` (possibly `None`) so alpha hairlines still derive from the ink seed, while `ink_scale` needs a concrete canvas and so defaults it. `warning-mid` maps to the *base* seed rather than the deep one, because in the shipped SCSS `--ws-warning` is the dark text tone and `--ws-warning-mid` is the brighter fill.

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest upande_webstore/tests/test_theme.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/theme/fonts.py upande_webstore/theme/tokens.py upande_webstore/tests/test_theme.py
git commit -m "feat(theme): token assembly, shape fields and validated font resolution"
```

---

### Task 3: Theme tab, SCSS sweep, and head emission

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.py`
- Modify: `upande_webstore/public/scss/webstore.bundle.scss`
- Modify: `upande_webstore/templates/webstore_base.html`
- Modify: `upande_webstore/services/settings.py`

**Interfaces:**
- Consumes: `tokens.get_tokens`, `tokens.get_custom_css`, `fonts.resolve` (Task 2).
- Produces: context keys `webstore_tokens` (dict), `webstore_custom_css` (str), `webstore_font_link` (str|None). `services.settings.get_appearance()` keeps its current signature and return shape.

- [ ] **Step 1: Add the SCSS `--ws-hairline-strong` token and sweep the literals**

Two mechanical edits to `upande_webstore/public/scss/webstore.bundle.scss`.

**1a.** In the `:root` block after line 82 (`--ws-hairline`), add:

```scss
	--ws-hairline-strong: rgba(10, 10, 10, 0.12);
```

**1b.** Replace all **32** occurrences of the literal `rgba(10, 10, 10, N)` outside the `:root` block with the matching token. Map by alpha:

| Literal alpha | Replace with |
|---|---|
| `0.04` | `var(--ws-wash)` |
| `0.06` | `var(--ws-hairline)` |
| `0.07`, `0.08` | `var(--ws-hairline-strong)` |
| `0.12` | `var(--ws-hairline-strong)` |
| anything else (shadows, `0.15`, `0.18`, `0.26`, `0.28`) | leave as-is — these are inside `box-shadow` declarations that the shadow tokens already cover, or one-off depth values not worth a token |

Find them with:

```bash
grep -n "rgba(10, 10, 10" upande_webstore/public/scss/webstore.bundle.scss
```

Only replace where the literal is a **background or border color**. Leave `box-shadow` literals alone in this task.

- [ ] **Step 2: Sweep the action surfaces**

`--ws-primary` already exists in `:root` as `var(--ws-ink)`, so this sweep is a no-op visually until the flag is turned on. Change **only** these 14 lines, and only the `background` / `border-color` / `outline` properties — never `color:`, which is text.

```bash
grep -n "background: var(--ws-ink)\|border-color: var(--ws-ink)\|outline: 2px solid var(--ws-ink)" upande_webstore/public/scss/webstore.bundle.scss
```

Lines to change: **157, 158, 227, 350, 396, 435, 458, 607, 723, 1198, 1248, 1331, 1355, 1456**.

In each, `var(--ws-ink)` → `var(--ws-primary)` for the `background`, `border-color` and `outline` properties only. Line 350 has both a `background` and a `border-color` — change both, leave its `color:` alone.

**Do not touch** the `var(--ws-grad-ink)` consumers (lines 247, 262, 329, 656, 815) — `--ws-grad-ink` is itself remapped by `get_tokens`.

- [ ] **Step 3: Verify the SCSS sweep changed nothing visually**

```bash
cd /home/austin/frappe-v16-bench && bench build --app upande_webstore
```

Expected: builds clean. The compiled CSS differs only by variable indirection; since `--ws-primary: var(--ws-ink)` and `--ws-hairline-strong` matches the literal it replaced, rendering is identical.

- [ ] **Step 4: Add the Theme tab fields to the DocType**

In `webstore_settings.json`, replace the existing `appearance_tab` entry and the `brand_colors_section` / `primary_color` fields. Keep `brand_logo`, `hero_image` and the three `*_category_image` fields exactly where they are for now — Task 12 migrates them.

Add to `field_order` after the existing appearance image fields, and to `fields`:

```json
{"fieldname": "theme_tab", "fieldtype": "Tab Break", "label": "Theme"},
{"fieldname": "brand_colors_section", "fieldtype": "Section Break", "label": "Brand Colors"},
{"fieldname": "accent", "fieldtype": "Color", "label": "Accent", "description": "Blank = shipped gold."},
{"fieldname": "accent_dark", "fieldtype": "Color", "label": "Accent Dark", "description": "Blank = derived from Accent."},
{"fieldname": "accent_soft", "fieldtype": "Color", "label": "Accent Soft (tint)", "description": "Blank = derived from Accent."},
{"fieldname": "accent_drives_primary", "fieldtype": "Check", "label": "Accent Drives Primary Actions", "description": "On: buttons, active nav and avatars use the accent instead of ink."},
{"fieldname": "neutral_cb", "fieldtype": "Column Break"},
{"fieldname": "ink", "fieldtype": "Color", "label": "Ink / Neutral", "description": "Headings and body text. The whole neutral scale derives from this."},
{"fieldname": "ink_muted", "fieldtype": "Color", "label": "Muted Text", "description": "Anchors the gray temperature. Blank = derived."},
{"fieldname": "canvas", "fieldtype": "Color", "label": "Page Canvas"},
{"fieldname": "wash", "fieldtype": "Color", "label": "Muted Fill", "description": "Sunken fills. Must be darker than the canvas."},
{"fieldname": "border", "fieldtype": "Color", "label": "Border"},
{"fieldname": "border_strong", "fieldtype": "Color", "label": "Border (strong)"},
{"fieldname": "status_colors_section", "fieldtype": "Section Break", "label": "Status Colors"},
{"fieldname": "success", "fieldtype": "Color", "label": "Success"},
{"fieldname": "warning", "fieldtype": "Color", "label": "Warning"},
{"fieldname": "status_cb", "fieldtype": "Column Break"},
{"fieldname": "danger", "fieldtype": "Color", "label": "Danger"},
{"fieldname": "info", "fieldtype": "Color", "label": "Info"},
{"fieldname": "typography_section", "fieldtype": "Section Break", "label": "Typography"},
{"fieldname": "font_sans", "fieldtype": "Select", "label": "Body Font", "options": "\nPoppins\nCustom"},
{"fieldname": "font_sans_name", "fieldtype": "Data", "label": "Body Font Family", "depends_on": "eval:doc.font_sans=='Custom'"},
{"fieldname": "font_display", "fieldtype": "Select", "label": "Display Font", "options": "\nFraunces\nCustom"},
{"fieldname": "font_display_name", "fieldtype": "Data", "label": "Display Font Family", "depends_on": "eval:doc.font_display=='Custom'"},
{"fieldname": "font_cb", "fieldtype": "Column Break"},
{"fieldname": "font_mono", "fieldtype": "Select", "label": "Mono Font", "options": "\nIBM Plex Mono\nCustom"},
{"fieldname": "font_mono_name", "fieldtype": "Data", "label": "Mono Font Family", "depends_on": "eval:doc.font_mono=='Custom'"},
{"fieldname": "google_fonts_url", "fieldtype": "Data", "label": "Google Fonts URL", "description": "https://fonts.googleapis.com/... Required for Custom families."},
{"fieldname": "shape_section", "fieldtype": "Section Break", "label": "Shape"},
{"fieldname": "radius", "fieldtype": "Data", "label": "Base Radius", "description": "Any CSS length. Blank = 0.75rem."},
{"fieldname": "radius_card", "fieldtype": "Data", "label": "Card Radius", "description": "Blank = 20px."},
{"fieldname": "radius_panel", "fieldtype": "Data", "label": "Panel Radius", "description": "Blank = 24px."},
{"fieldname": "advanced_section", "fieldtype": "Section Break", "label": "Advanced", "collapsible": 1},
{"fieldname": "custom_css", "fieldtype": "Code", "label": "Custom CSS", "options": "CSS", "description": "Emitted after the generated tokens, so it wins. Use for any token the seeds do not reach."}
```

Keep `primary_color` in the JSON as a hidden field (`"hidden": 1`) so `derive_brand_colors` and the existing tests keep working during the transition.

- [ ] **Step 5: Add validation**

Replace `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.py` contents (read it first; it is currently a bare controller) so `validate` includes:

```python
import frappe
from frappe import _
from frappe.model.document import Document

from upande_webstore.theme import fonts


class WebstoreSettings(Document):
	def validate(self):
		self.validate_font_url()

	def validate_font_url(self):
		url = (self.google_fonts_url or "").strip()
		if url and not fonts.is_allowed_url(url):
			frappe.throw(
				_("Google Fonts URL must be an https link to {0}.").format(fonts.ALLOWED_FONT_HOST)
			)
		for role in ("sans", "display", "mono"):
			if self.get(f"font_{role}") == "Custom" and not self.get(f"font_{role}_name"):
				frappe.throw(_("Set a family name for the custom {0} font.").format(role))
```

Preserve any existing methods in that file — append `validate` rather than replacing wholesale if one already exists.

- [ ] **Step 6: Emit the tokens in `<head>`**

In `upande_webstore/templates/webstore_base.html`, replace the entire `{% block style %}` (lines 3–17) with:

```jinja
{% block style %}
{{ super() }}
{%- if webstore_font_link %}
<link rel="stylesheet" href="{{ webstore_font_link }}">
{%- endif %}
{%- if webstore_tokens or webstore_custom_css %}
<style>
	:root {
	{%- for name, value in webstore_tokens.items() %}
		--ws-{{ name }}: {{ value }};
	{%- endfor %}
	{%- if webstore_custom_css %}
		{{ webstore_custom_css }}
	{%- endif %}
	}
</style>
{%- endif %}
{% endblock %}
```

Custom CSS goes **inside** `:root` and **after** the generated tokens, so bare `--ws-x: y;` declarations work and win.

- [ ] **Step 7: Wire the context**

In `upande_webstore/services/settings.py`, replace `update_website_context` with:

```python
def update_website_context(context):
	from upande_webstore.theme import fonts, tokens

	settings = get_settings()
	context.webstore_tokens = tokens.get_tokens(settings)
	context.webstore_custom_css = tokens.get_custom_css(settings)
	context.webstore_font_link = fonts.resolve(settings)["link"]
	# retained one release for templates still reading the old key
	context.webstore_appearance = get_appearance()
```

Leave `get_appearance`, `derive_brand_colors` and `APPEARANCE_IMAGE_FIELDS` untouched.

- [ ] **Step 8: Run the full existing suite plus the new tests**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore
```

Expected: PASS. `tests/test_settings.py` must pass **unmodified** — that is the backward-compatibility gate.

- [ ] **Step 9: Verify a blank site emits no style block**

```bash
bench --site webstore.localhost console
```

```python
import frappe
from upande_webstore.theme import tokens
from upande_webstore.services.settings import get_settings
print(repr(tokens.get_tokens(get_settings())))
```

Expected: `{}` on a site with no seeds set.

- [ ] **Step 10: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_settings/ \
        upande_webstore/public/scss/webstore.bundle.scss \
        upande_webstore/templates/webstore_base.html \
        upande_webstore/services/settings.py
git commit -m "feat(theme): Theme tab, token emission, and var()-driven SCSS"
```

---

## Phase 2 — Feature flags

### Task 4: Feature registry and guards

**Files:**
- Create: `upande_webstore/theme/features.py`
- Create: `upande_webstore/tests/test_features.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `FEATURES` — tuple of `Feature` namedtuples with fields `key`, `fieldname`, `label`, `group` (`"storefront"` or `"portal"`).
  - `enabled() -> frappe._dict` — `{key: bool}` for all 19, reading the cached settings doc; a field that is `None`/unset counts as **on**.
  - `require(*keys)` — raises `frappe.DoesNotExistError` if any key is off.
  - `guard(*keys)` — decorator for whitelisted methods, raising `frappe.PermissionError`.
  - `FIELDNAME(key)` helper is **not** exposed; use `Feature.fieldname`.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_features.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


def set_flag(fieldname, value):
	settings = frappe.get_doc("Webstore Settings")
	settings.set(fieldname, value)
	settings.save(ignore_permissions=True)
	frappe.clear_cache()


class TestFeatureRegistry(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_all_nineteen_registered(self):
		from upande_webstore.theme.features import FEATURES

		self.assertEqual(len(FEATURES), 19)
		keys = [f.key for f in FEATURES]
		self.assertEqual(len(keys), len(set(keys)), "duplicate feature keys")
		for expected in ("cart", "wishlist", "signup", "portal", "quotations", "claims"):
			self.assertIn(expected, keys)

	def test_groups_split_nine_and_ten(self):
		from upande_webstore.theme.features import FEATURES

		self.assertEqual(len([f for f in FEATURES if f.group == "storefront"]), 9)
		self.assertEqual(len([f for f in FEATURES if f.group == "portal"]), 10)

	def test_default_is_enabled(self):
		from upande_webstore.theme.features import enabled

		flags = enabled()
		for feature_key, value in flags.items():
			self.assertTrue(value, f"{feature_key} should default on")

	def test_disabling_reflects_in_enabled(self):
		from upande_webstore.theme.features import enabled

		set_flag("enable_wishlist", 0)
		self.assertFalse(enabled()["wishlist"])
		self.assertTrue(enabled()["cart"])


class TestRequire(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_passes_when_on(self):
		from upande_webstore.theme.features import require

		require("wishlist")  # must not raise

	def test_raises_when_off(self):
		from upande_webstore.theme.features import require

		set_flag("enable_wishlist", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			require("wishlist")

	def test_master_gate_composes(self):
		from upande_webstore.theme.features import require

		set_flag("enable_portal", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			require("portal", "quotations")

	def test_unknown_key_raises_valueerror_not_404(self):
		"""A typo in a feature key is a bug, not a 404."""
		from upande_webstore.theme.features import require

		with self.assertRaises(ValueError):
			require("wishlst")


class TestGuard(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_allows_when_on(self):
		from upande_webstore.theme.features import guard

		@guard("wishlist")
		def handler():
			return "ok"

		self.assertEqual(handler(), "ok")

	def test_throws_permission_error_when_off(self):
		from upande_webstore.theme.features import guard

		@guard("wishlist")
		def handler():
			return "ok"

		set_flag("enable_wishlist", 0)
		with self.assertRaises(frappe.PermissionError):
			handler()

	def test_preserves_function_metadata(self):
		from upande_webstore.theme.features import guard

		@guard("cart")
		def named_handler(a, b=2):
			"""docstring"""
			return a + b

		self.assertEqual(named_handler.__name__, "named_handler")
		self.assertEqual(named_handler.__doc__, "docstring")
		self.assertEqual(named_handler(1), 3)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_features
```

Expected: FAIL — `ModuleNotFoundError: No module named 'upande_webstore.theme.features'`

- [ ] **Step 3: Write minimal implementation**

Create `upande_webstore/theme/features.py`:

```python
"""One registry driving all three enforcement layers, so a flag cannot be
enforced in one place and forgotten in another."""

import functools
from collections import namedtuple

import frappe
from frappe import _

Feature = namedtuple("Feature", ["key", "fieldname", "label", "group"])


def _f(key, label, group):
	return Feature(key, f"enable_{key}", label, group)


FEATURES = (
	# storefront — 9
	_f("cart", "Cart & Checkout", "storefront"),
	_f("wishlist", "Wishlist", "storefront"),
	_f("signup", "Signup", "storefront"),
	_f("search_palette", "Search Palette", "storefront"),
	_f("cart_drawer", "Cart Drawer", "storefront"),
	_f("hero", "Hero", "storefront"),
	_f("hero_stats", "Hero Stats", "storefront"),
	_f("category_cards", "Category Cards", "storefront"),
	_f("footer", "Footer", "storefront"),
	# portal — 10
	_f("portal", "Portal", "portal"),
	_f("dashboard", "Dashboard", "portal"),
	_f("quotations", "Quotations", "portal"),
	_f("orders", "Orders", "portal"),
	_f("invoices", "Invoices", "portal"),
	_f("statement", "Statement", "portal"),
	_f("support", "Support", "portal"),
	_f("claims", "Claims", "portal"),
	_f("account", "Account", "portal"),
	_f("sidebar_stats", "Sidebar Stats", "portal"),
)

BY_KEY = {feature.key: feature for feature in FEATURES}


def enabled():
	"""{key: bool} for all features. An unset field counts as ON, so an existing
	site behaves exactly as it did before these fields existed."""
	from upande_webstore.services.settings import get_settings

	settings = get_settings()
	flags = frappe._dict()
	for feature in FEATURES:
		value = settings.get(feature.fieldname)
		flags[feature.key] = True if value is None else bool(value)
	return flags


def _check(keys):
	flags = enabled()
	for key in keys:
		if key not in BY_KEY:
			raise ValueError(f"unknown webstore feature: {key!r}")
		if not flags[key]:
			return key
	return None


def require(*keys):
	"""Route-level gate. Raises DoesNotExistError, which Frappe renders as 404."""
	blocked = _check(keys)
	if blocked:
		raise frappe.DoesNotExistError(f"webstore feature disabled: {blocked}")


def guard(*keys):
	"""API-level gate for whitelisted methods."""

	def decorator(fn):
		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			blocked = _check(keys)
			if blocked:
				frappe.throw(_("This feature is not enabled."), frappe.PermissionError)
			return fn(*args, **kwargs)

		return wrapper

	return decorator
```

- [ ] **Step 4: Run test to verify it fails differently**

The tests still fail because the `enable_*` fields do not exist yet, so `settings.get()` returns `None` for all — which the code treats as ON, so `test_disabling_reflects_in_enabled` fails on `set_flag`. That is expected; Step 5 adds the fields.

- [ ] **Step 5: Add the Features tab to the DocType**

In `webstore_settings.json`, append to `field_order` and `fields`. All checkboxes default `"1"`.

```json
{"fieldname": "features_tab", "fieldtype": "Tab Break", "label": "Features"},
{"fieldname": "storefront_features_section", "fieldtype": "Section Break", "label": "Storefront"},
{"fieldname": "enable_cart", "fieldtype": "Check", "label": "Cart & Checkout", "default": "1", "description": "Off = browse-only catalog."},
{"fieldname": "enable_wishlist", "fieldtype": "Check", "label": "Wishlist", "default": "1"},
{"fieldname": "enable_signup", "fieldtype": "Check", "label": "Signup", "default": "1"},
{"fieldname": "enable_search_palette", "fieldtype": "Check", "label": "Search Palette (⌘K)", "default": "1"},
{"fieldname": "enable_cart_drawer", "fieldtype": "Check", "label": "Cart Drawer", "default": "1"},
{"fieldname": "storefront_features_cb", "fieldtype": "Column Break"},
{"fieldname": "enable_hero", "fieldtype": "Check", "label": "Hero", "default": "1"},
{"fieldname": "enable_hero_stats", "fieldtype": "Check", "label": "Hero Stats", "default": "1"},
{"fieldname": "enable_category_cards", "fieldtype": "Check", "label": "Category Cards", "default": "1"},
{"fieldname": "enable_footer", "fieldtype": "Check", "label": "Footer", "default": "1"},
{"fieldname": "portal_features_section", "fieldtype": "Section Break", "label": "Portal"},
{"fieldname": "enable_portal", "fieldtype": "Check", "label": "Portal", "default": "1", "description": "Master switch for every /portal page."},
{"fieldname": "enable_dashboard", "fieldtype": "Check", "label": "Dashboard", "default": "1"},
{"fieldname": "enable_quotations", "fieldtype": "Check", "label": "Quotations", "default": "1"},
{"fieldname": "enable_orders", "fieldtype": "Check", "label": "Orders", "default": "1"},
{"fieldname": "enable_invoices", "fieldtype": "Check", "label": "Invoices", "default": "1"},
{"fieldname": "portal_features_cb", "fieldtype": "Column Break"},
{"fieldname": "enable_statement", "fieldtype": "Check", "label": "Statement", "default": "1"},
{"fieldname": "enable_support", "fieldtype": "Check", "label": "Support", "default": "1"},
{"fieldname": "enable_claims", "fieldtype": "Check", "label": "Claims", "default": "1"},
{"fieldname": "enable_account", "fieldtype": "Check", "label": "Account", "default": "1"},
{"fieldname": "enable_sidebar_stats", "fieldtype": "Check", "label": "Sidebar Stats", "default": "1"}
```

- [ ] **Step 6: Add the dependent-flag rule**

In `webstore_settings.py`, extend `validate`:

```python
	def validate(self):
		self.validate_font_url()
		self.apply_feature_dependencies()

	def apply_feature_dependencies(self):
		# the drawer has nothing to show without a cart
		if not self.enable_cart and self.enable_cart_drawer:
			self.enable_cart_drawer = 0
```

- [ ] **Step 7: Add a dependency test**

Append to `tests/test_features.py`:

```python
class TestDependentFlags(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_cart_off_forces_drawer_off(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_cart = 0
		settings.enable_cart_drawer = 1
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(frappe.get_doc("Webstore Settings").enable_cart_drawer, 0)
```

- [ ] **Step 8: Migrate and run**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_features
```

Expected: PASS.

Also update `upande_webstore/tests/utils.py` — `setup_webstore_settings` must reset the flags so tests do not leak state. Add after the existing image-field loop:

```python
	from upande_webstore.theme.features import FEATURES

	for feature in FEATURES:
		settings.set(feature.fieldname, 1)
```

- [ ] **Step 9: Commit**

```bash
git add upande_webstore/theme/features.py upande_webstore/tests/test_features.py \
        upande_webstore/tests/utils.py \
        upande_webstore/upande_webstore/doctype/webstore_settings/
git commit -m "feat(features): 19-flag registry with route and API guards"
```

---

### Task 5: Enforce flags on routes and APIs

**Files:**
- Modify: `upande_webstore/services/portal.py:52-68`
- Modify: `upande_webstore/www/wishlist.py`, `www/cart.py`, `www/signup.py`
- Modify: `upande_webstore/api/wishlist.py`, `api/cart.py`, `api/checkout.py`, `api/search.py`, `api/support.py`, `api/portal.py`, `api/account.py`

**Interfaces:**
- Consumes: `features.require`, `features.guard` (Task 4).
- Produces: no new symbols. All 12 portal pages gated by one insertion in `portal_page_context`.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_features.py`:

```python
class TestRouteEnforcement(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()
		self.user = frappe.session.user

	def tearDown(self):
		frappe.set_user(self.user)

	def test_portal_page_context_gates_on_master(self):
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("flagtest@example.com")
		frappe.set_user(email)
		from upande_webstore.services.portal import portal_page_context

		set_flag("enable_portal", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			portal_page_context(frappe._dict(), "/portal/orders", "orders")

	def test_portal_page_context_gates_on_page_key(self):
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("flagtest2@example.com")
		frappe.set_user(email)
		from upande_webstore.services.portal import portal_page_context

		set_flag("enable_orders", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			portal_page_context(frappe._dict(), "/portal/orders", "orders")

	def test_wishlist_page_gates(self):
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("flagtest3@example.com")
		frappe.set_user(email)
		import upande_webstore.www.wishlist as wishlist_page

		set_flag("enable_wishlist", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			wishlist_page.get_context(frappe._dict())


class TestApiEnforcement(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_search_api_gated_by_palette_flag(self):
		from upande_webstore.api.search import search_products

		set_flag("enable_search_palette", 0)
		with self.assertRaises(frappe.PermissionError):
			search_products("rose")

	def test_claim_api_gated(self):
		from upande_webstore.api.support import create_claim

		set_flag("enable_claims", 0)
		with self.assertRaises(frappe.PermissionError):
			create_claim("Quality", "SO-0001", "damaged")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_features
```

Expected: FAIL — no `DoesNotExistError` / `PermissionError` raised.

- [ ] **Step 3: Gate all 12 portal pages with one line**

Every portal page already passes an `active` argument that **exactly matches its feature key** (`dashboard`, `quotations`, `orders`, `invoices`, `statement`, `support`, `claims`, `account`). So in `upande_webstore/services/portal.py`, add to `portal_page_context` as the **first** statement, before `portal_guard`:

```python
def portal_page_context(context, route, active):
	"""Shared context for every portal page: feature gate, guard, sidebar
	badges, at-a-glance stats and the customer identity card."""
	from upande_webstore.services.portal_data import get_sidebar_counts
	from upande_webstore.theme.features import require

	require("portal", active)

	customer = portal_guard(route)
	...
```

Gate before the login redirect so a disabled feature 404s for guests too, rather than bouncing them to a login that leads nowhere.

- [ ] **Step 4: Gate the storefront pages**

`www/wishlist.py` — add as the first line of `get_context`:

```python
	from upande_webstore.theme.features import require

	require("wishlist")
```

`www/cart.py` — same with `require("cart")`.

`www/signup.py` — same with `require("signup")`.

- [ ] **Step 5: Decorate the API methods**

Add `from upande_webstore.theme.features import guard` to each file and place `@guard(...)` **below** `@frappe.whitelist()` and any `@rate_limit`, so it is the innermost decorator and runs after Frappe's own checks.

| File | Method | Guard |
|---|---|---|
| `api/search.py` | `search_products` | `@guard("search_palette")` |
| `api/cart.py` | `get_cart`, `get_cart_count`, `add_item`, `update_qty`, `remove_item` | `@guard("cart")` |
| `api/checkout.py` | `place_order` | `@guard("cart")` |
| `api/wishlist.py` | `toggle`, `get_wishlisted_products`, `get_wishlist` | `@guard("wishlist")` |
| `api/support.py` | `create_issue` | `@guard("portal", "support")` |
| `api/support.py` | `create_claim` | `@guard("portal", "claims")` |
| `api/portal.py` | `accept_quotation`, `decline_quotation` | `@guard("portal", "quotations")` |
| `api/portal.py` | `download_invoice_pdf` | `@guard("portal", "invoices")` |
| `api/account.py` | `sign_up` | `@guard("signup")` |
| `api/account.py` | `update_profile`, `add_address` | `@guard("portal", "account")` |

Leave `api/variants.py` ungated — variant resolution is core catalog behaviour with no flag.

Example shape:

```python
@frappe.whitelist()
@guard("search_palette")
def search_products(q=None):
	...
```

- [ ] **Step 6: Run the tests**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_features
bench --site webstore.localhost run-tests --app upande_webstore
```

Expected: PASS across the whole suite. Existing cart/wishlist/support tests must still pass because `setup_webstore_settings` now sets every flag on.

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/services/portal.py upande_webstore/www/ upande_webstore/api/ \
        upande_webstore/tests/test_features.py
git commit -m "feat(features): enforce flags at route and API layers"
```

---

### Task 6: Feature conditionals in templates

**Files:**
- Modify: `upande_webstore/templates/webstore_base.html`
- Modify: `upande_webstore/templates/webstore_portal_base.html`
- Modify: `upande_webstore/www/store.html`
- Modify: `upande_webstore/services/settings.py`

**Interfaces:**
- Consumes: `features.enabled` (Task 4).
- Produces: context key `webstore_features` (a `frappe._dict`, so `webstore_features.wishlist` works in Jinja).

- [ ] **Step 1: Inject the flags into context**

In `services/settings.py`, add to `update_website_context`:

```python
	from upande_webstore.theme.features import enabled

	context.webstore_features = enabled()
```

- [ ] **Step 2: Gate the navbar**

In `templates/webstore_base.html`, wrap these existing elements. Keep the markup and inline SVGs exactly as written — only add conditionals.

- The `<button ... data-ws-palette>` search trigger → `{% if webstore_features.search_palette %}` … `{% endif %}`
- The wishlist `<a>` → `{% if webstore_features.wishlist %}`
- The basket `<a class="ws-cart-link">` → `{% if webstore_features.cart %}`
- The `/portal` and `/store` member button pair plus the `.ws-avatar` link → `{% if webstore_features.portal %}`
- The guest `<a href="/signup">` → `{% if webstore_features.signup %}`

- [ ] **Step 3: Gate the drawers and footer**

Still in `webstore_base.html`, in `{% block footer %}`:

- `<dialog id="ws-cart-drawer">` → `{% if webstore_features.cart and webstore_features.cart_drawer %}`
- `<dialog id="ws-palette">` → `{% if webstore_features.search_palette %}`
- `<footer class="ws-footer">` → `{% if webstore_features.footer %}`

Inside the footer's Shop and Account columns, gate the individual links: the Customer portal / Quotations / Claims entries by `webstore_features.portal` and their own key.

- [ ] **Step 4: Gate the portal sidebar**

In `templates/webstore_portal_base.html`, wrap each `<a class="ws-side-link ...">` in `{% if webstore_features.<key> %}` using its existing `portal_active` value as the key — `dashboard`, `quotations`, `orders`, `invoices`, `statement`, `support`, `claims`, `account`.

Wrap the whole second `<div class="ws-side-section">` (the "At a glance" block) in `{% if webstore_features.sidebar_stats %}`.

- [ ] **Step 5: Gate the storefront hero and cards**

In `www/store.html`:

- Wrap `<div class="ws-hero2">` … `</div>` in `{% if webstore_features.hero %}`
- Wrap `<div class="ws-hero2-stats ...">` in `{% if webstore_features.hero_stats %}`
- Wrap `<div class="ws-cats">` in `{% if webstore_features.category_cards %}`
- Wrap the whole `{% block hero %}` body in `{% if webstore_features.hero or webstore_features.category_cards %}` so the `.ws-storefront-band` container does not render as an empty band when both are off.

- [ ] **Step 6: Fix the signup CTA fallback**

Still in `www/store.html`, the hero's secondary action currently links guests to `/signup`, which 404s when Signup is off. Replace the guest branch:

```jinja
{% if frappe.session.user == "Guest" %}
	{% if webstore_features.signup %}
	<a href="/signup" class="btn btn-hero-ghost">{{ _("Open a trade account") }}</a>
	{% else %}
	<a href="/login" class="btn btn-hero-ghost">{{ _("Member login") }}</a>
	{% endif %}
{% elif webstore_features.portal %}
	<a href="/portal" class="btn btn-hero-ghost">{{ _("Go to your portal") }}</a>
{% endif %}
```

- [ ] **Step 7: Gate add-to-cart controls**

Find every add-to-cart control and wrap it in `{% if webstore_features.cart %}`:

```bash
grep -rn "add_item\|add-to-cart\|data-ws-add" upande_webstore/www upande_webstore/templates
```

With Cart off the catalog must still browse cleanly — product pages render, prices show, no basket anywhere.

- [ ] **Step 8: Write the template test**

Append to `upande_webstore/tests/test_features.py`:

```python
class TestTemplateGating(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def _render_store(self):
		from frappe.website.serve import get_response_content

		return get_response_content("/store")

	def test_wishlist_link_hidden_when_off(self):
		set_flag("enable_wishlist", 0)
		self.assertNotIn('href="/wishlist"', self._render_store())

	def test_wishlist_link_shown_when_on(self):
		frappe.set_user("Administrator")
		self.assertIn("/store", self._render_store())

	def test_category_cards_hidden_when_off(self):
		set_flag("enable_category_cards", 0)
		self.assertNotIn("ws-catcard", self._render_store())

	def test_hero_hidden_when_off(self):
		set_flag("enable_hero", 0)
		self.assertNotIn("ws-hero2-inner", self._render_store())

	def test_footer_hidden_when_off(self):
		set_flag("enable_footer", 0)
		self.assertNotIn("ws-footer-grid", self._render_store())
```

- [ ] **Step 9: Run tests and eyeball the page**

```bash
bench --site webstore.localhost run-tests --app upande_webstore
bench build --app upande_webstore
```

Expected: PASS. Then flip a few flags off in the desk and load `/store` and `/portal` to confirm nothing leaves a hole in the layout.

- [ ] **Step 10: Commit**

```bash
git add upande_webstore/templates/ upande_webstore/www/ upande_webstore/services/settings.py \
        upande_webstore/tests/test_features.py
git commit -m "feat(features): template conditionals and signup CTA fallback"
```

---

## Phase 3 — Branding

### Task 7: Child doctypes

**Files:**
- Create: `upande_webstore/upande_webstore/doctype/webstore_hero_stat/{__init__.py,webstore_hero_stat.json,webstore_hero_stat.py}`
- Create: `upande_webstore/upande_webstore/doctype/webstore_category_card/{__init__.py,webstore_category_card.json,webstore_category_card.py}`
- Create: `upande_webstore/upande_webstore/doctype/webstore_footer_link/{__init__.py,webstore_footer_link.json,webstore_footer_link.py}`

**Interfaces:**
- Consumes: nothing.
- Produces: three child DocTypes usable as `Table` fields. Field names are fixed here and consumed by Tasks 8, 10 and 13: `Webstore Hero Stat`(`value`, `label`), `Webstore Category Card`(`label`, `subtitle`, `image`, `category`, `url`), `Webstore Footer Link`(`column`, `label`, `url`).

- [ ] **Step 1: Create the hero stat child table**

Follow the shape of the existing `webstore_warehouse` child doctype. `upande_webstore/upande_webstore/doctype/webstore_hero_stat/webstore_hero_stat.json`:

```json
{
 "doctype": "DocType",
 "name": "Webstore Hero Stat",
 "module": "Upande Webstore",
 "istable": 1,
 "engine": "InnoDB",
 "creation": "2026-07-28 00:00:01.000000",
 "modified": "2026-07-28 00:00:01.000000",
 "owner": "Administrator",
 "field_order": ["value", "label"],
 "fields": [
  {"fieldname": "value", "fieldtype": "Data", "label": "Value", "in_list_view": 1, "columns": 3, "reqd": 1},
  {"fieldname": "label", "fieldtype": "Data", "label": "Label", "in_list_view": 1, "columns": 7, "reqd": 1}
 ],
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

`webstore_hero_stat.py`:

```python
from frappe.model.document import Document


class WebstoreHeroStat(Document):
	pass
```

Plus an empty `__init__.py`.

- [ ] **Step 2: Create the category card child table**

`webstore_category_card.json`, same envelope, with:

```json
 "field_order": ["label", "subtitle", "image", "category", "url"],
 "fields": [
  {"fieldname": "label", "fieldtype": "Data", "label": "Label", "in_list_view": 1, "columns": 2, "reqd": 1},
  {"fieldname": "subtitle", "fieldtype": "Data", "label": "Subtitle", "in_list_view": 1, "columns": 3},
  {"fieldname": "image", "fieldtype": "Attach Image", "label": "Image", "in_list_view": 1, "columns": 2},
  {"fieldname": "category", "fieldtype": "Data", "label": "Category", "in_list_view": 1, "columns": 2, "description": "Links to /store?category=<value>."},
  {"fieldname": "url", "fieldtype": "Data", "label": "Custom URL", "description": "Overrides Category when set."}
 ],
```

Controller class `WebstoreCategoryCard`.

- [ ] **Step 3: Create the footer link child table**

`webstore_footer_link.json`, with:

```json
 "field_order": ["column", "label", "url"],
 "fields": [
  {"fieldname": "column", "fieldtype": "Data", "label": "Column", "in_list_view": 1, "columns": 3, "reqd": 1, "description": "Column heading. Rows sharing a heading group together, in table order."},
  {"fieldname": "label", "fieldtype": "Data", "label": "Label", "in_list_view": 1, "columns": 3, "reqd": 1},
  {"fieldname": "url", "fieldtype": "Data", "label": "URL", "in_list_view": 1, "columns": 4, "reqd": 1}
 ],
```

Controller class `WebstoreFooterLink`.

- [ ] **Step 4: Migrate to create the tables**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost migrate
```

Expected: three new DocTypes created, no errors.

- [ ] **Step 5: Verify they exist**

```bash
bench --site webstore.localhost console
```

```python
import frappe
for dt in ("Webstore Hero Stat", "Webstore Category Card", "Webstore Footer Link"):
	print(dt, frappe.db.exists("DocType", dt))
```

Expected: all three print a truthy value.

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/upande_webstore/doctype/webstore_hero_stat/ \
        upande_webstore/upande_webstore/doctype/webstore_category_card/ \
        upande_webstore/upande_webstore/doctype/webstore_footer_link/
git commit -m "feat(branding): hero stat, category card and footer link child tables"
```

---

### Task 8: Branding resolution

**Files:**
- Create: `upande_webstore/theme/branding.py`
- Create: `upande_webstore/tests/test_branding.py`

**Interfaces:**
- Consumes: the child DocType field names from Task 7.
- Produces:
  - `branding.DEFAULTS` — `dict[str, str]` of every fallback string.
  - `branding.get_branding(settings=None) -> frappe._dict` — every scalar key from `DEFAULTS` resolved to setting-or-default, plus `hero_stats` (list of `{value,label}`), `category_cards` (list of `{label,subtitle,image,href}`), `footer_columns` (list of `{heading, links:[{label,url}]}`), and the resolved `brand_logo` / `favicon` / `hero_image` paths.
  - `category_cards[].href` is precomputed: `url` if set, else `/store?category=<urlencoded category>`.

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_branding.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestBrandingDefaults(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_blank_resolves_to_shipped_defaults(self):
		from upande_webstore.theme.branding import DEFAULTS, get_branding

		resolved = get_branding()
		self.assertEqual(resolved["wordmark"], DEFAULTS["wordmark"])
		self.assertEqual(resolved["hero_heading"], DEFAULTS["hero_heading"])
		self.assertEqual(resolved["footer_copyright"], DEFAULTS["footer_copyright"])

	def test_every_default_key_is_resolved(self):
		"""No DEFAULTS key may be missing from the resolved payload."""
		from upande_webstore.theme.branding import DEFAULTS, get_branding

		resolved = get_branding()
		for key in DEFAULTS:
			self.assertIn(key, resolved)
			self.assertIsNotNone(resolved[key])

	def test_setting_overrides_default(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.wordmark = "mona"
		settings.wordmark_bold = "flowers"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		resolved = get_branding()
		self.assertEqual(resolved["wordmark"], "mona")
		self.assertEqual(resolved["wordmark_bold"], "flowers")

	def test_logo_falls_back_to_shipped_asset(self):
		from upande_webstore.theme.branding import get_branding

		self.assertEqual(
			get_branding()["brand_logo"], "/assets/upande_webstore/images/upande-logo.png"
		)


class TestBrandingTables(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_empty_tables_yield_empty_lists(self):
		from upande_webstore.theme.branding import get_branding

		resolved = get_branding()
		self.assertEqual(resolved["hero_stats"], [])
		self.assertEqual(resolved["category_cards"], [])
		self.assertEqual(resolved["footer_columns"], [])

	def test_category_card_href_from_category(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.append("category_cards", {"label": "Fresh Produce", "category": "Fresh Produce"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		card = get_branding()["category_cards"][0]
		self.assertEqual(card["href"], "/store?category=Fresh%20Produce")

	def test_category_card_custom_url_wins(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.append("category_cards", {"label": "Blog", "category": "X", "url": "/blog"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(get_branding()["category_cards"][0]["href"], "/blog")

	def test_footer_links_group_by_column_in_table_order(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		for row in (
			{"column": "Shop", "label": "All", "url": "/store"},
			{"column": "Account", "label": "Portal", "url": "/portal"},
			{"column": "Shop", "label": "Roses", "url": "/store?category=Roses"},
		):
			settings.append("footer_links", row)
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		columns = get_branding()["footer_columns"]
		self.assertEqual([c["heading"] for c in columns], ["Shop", "Account"])
		self.assertEqual([link["label"] for link in columns[0]["links"]], ["All", "Roses"])

	def test_hero_stats_preserve_order(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.append("hero_stats", {"value": "45+", "label": "varieties"})
		settings.append("hero_stats", {"value": "3", "label": "continents"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		stats = get_branding()["hero_stats"]
		self.assertEqual([s["value"] for s in stats], ["45+", "3"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_branding
```

Expected: FAIL — `ModuleNotFoundError: No module named 'upande_webstore.theme.branding'`

- [ ] **Step 3: Write minimal implementation**

Create `upande_webstore/theme/branding.py`:

```python
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
		"Export-grade flowers, coffee and fresh produce from Kenyan growers — "
		"wholesale quantities, quotation-first ordering, cold chain to your door."
	),
	"hero_cta_primary": "Browse the catalog",
	"hero_cta_secondary_guest": "Open a trade account",
	"hero_cta_secondary_member": "Go to your portal",
	# footer
	"footer_tagline": (
		"Export-grade flowers, coffee and fresh produce from Kenyan growers — "
		"ordered online, confirmed by people who know the farms."
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
			"image": row.image or None,
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
```

- [ ] **Step 4: Add the Branding tab fields**

In `webstore_settings.json`, append to `field_order` and `fields`. Every scalar key in `DEFAULTS` needs a field of the same name, plus the three tables and `favicon`.

```json
{"fieldname": "branding_tab", "fieldtype": "Tab Break", "label": "Branding"},
{"fieldname": "identity_section", "fieldtype": "Section Break", "label": "Identity"},
{"fieldname": "site_name", "fieldtype": "Data", "label": "Site Name"},
{"fieldname": "wordmark", "fieldtype": "Data", "label": "Wordmark", "description": "Light-weight part, e.g. 'mona'."},
{"fieldname": "wordmark_bold", "fieldtype": "Data", "label": "Wordmark (bold)", "description": "Accented part, e.g. 'flowers'."},
{"fieldname": "identity_cb", "fieldtype": "Column Break"},
{"fieldname": "wordmark_subtitle", "fieldtype": "Data", "label": "Wordmark Subtitle"},
{"fieldname": "favicon", "fieldtype": "Attach Image", "label": "Favicon"},
{"fieldname": "hero_section", "fieldtype": "Section Break", "label": "Hero"},
{"fieldname": "hero_eyebrow", "fieldtype": "Data", "label": "Eyebrow"},
{"fieldname": "hero_heading", "fieldtype": "Data", "label": "Heading"},
{"fieldname": "hero_heading_em", "fieldtype": "Data", "label": "Heading (emphasis)", "description": "Rendered italic in the display face."},
{"fieldname": "hero_body", "fieldtype": "Small Text", "label": "Body"},
{"fieldname": "hero_cta_cb", "fieldtype": "Column Break"},
{"fieldname": "hero_cta_primary", "fieldtype": "Data", "label": "Primary CTA"},
{"fieldname": "hero_cta_secondary_guest", "fieldtype": "Data", "label": "Secondary CTA (guest)"},
{"fieldname": "hero_cta_secondary_member", "fieldtype": "Data", "label": "Secondary CTA (member)"},
{"fieldname": "hero_stats_section", "fieldtype": "Section Break", "label": "Hero Stats"},
{"fieldname": "hero_stats", "fieldtype": "Table", "label": "Hero Stats", "options": "Webstore Hero Stat"},
{"fieldname": "category_cards_section", "fieldtype": "Section Break", "label": "Category Cards"},
{"fieldname": "category_cards", "fieldtype": "Table", "label": "Category Cards", "options": "Webstore Category Card"},
{"fieldname": "footer_section", "fieldtype": "Section Break", "label": "Footer"},
{"fieldname": "footer_tagline", "fieldtype": "Small Text", "label": "Tagline"},
{"fieldname": "footer_links", "fieldtype": "Table", "label": "Footer Links", "options": "Webstore Footer Link"},
{"fieldname": "footer_contact_email", "fieldtype": "Data", "label": "Contact Email"},
{"fieldname": "footer_hours", "fieldtype": "Data", "label": "Hours"},
{"fieldname": "footer_contact_cb", "fieldtype": "Column Break"},
{"fieldname": "footer_location", "fieldtype": "Data", "label": "Location"},
{"fieldname": "footer_website", "fieldtype": "Data", "label": "Website"},
{"fieldname": "footer_copyright", "fieldtype": "Data", "label": "Copyright Holder", "description": "The year is prepended automatically."},
{"fieldname": "footer_note", "fieldtype": "Data", "label": "Footer Note"},
{"fieldname": "portal_branding_section", "fieldtype": "Section Break", "label": "Portal"},
{"fieldname": "portal_eyebrow", "fieldtype": "Data", "label": "Portal Eyebrow"}
```

- [ ] **Step 5: Run tests**

```bash
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_branding
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add upande_webstore/theme/branding.py upande_webstore/tests/test_branding.py \
        upande_webstore/upande_webstore/doctype/webstore_settings/
git commit -m "feat(branding): DEFAULTS-backed copy resolution and Branding tab"
```

---

### Task 9: Templates read branding

**Files:**
- Modify: `upande_webstore/templates/webstore_base.html`
- Modify: `upande_webstore/templates/webstore_portal_base.html:52`
- Modify: `upande_webstore/www/store.html:35-86`
- Modify: `upande_webstore/services/settings.py`

**Interfaces:**
- Consumes: `branding.get_branding` (Task 8), `webstore_features` (Task 6).
- Produces: context key `webstore_branding`.

- [ ] **Step 1: Inject branding into context**

In `services/settings.py`, add to `update_website_context`:

```python
	from upande_webstore.theme.branding import get_branding

	context.webstore_branding = get_branding(settings)
```

- [ ] **Step 2: Wordmark, logo and favicon in the navbar**

In `templates/webstore_base.html`, replace the `.ws-brand` anchor:

```jinja
		<a class="ws-brand" href="/store" title="{{ webstore_branding.site_name }}">
			<img src="{{ webstore_branding.brand_logo }}" alt="{{ webstore_branding.site_name }}">
			<span data-sub="{{ webstore_branding.wordmark_subtitle }}">{{ webstore_branding.wordmark }}<b>{{ webstore_branding.wordmark_bold }}</b></span>
		</a>
```

Add the favicon inside `{% block style %}`, after the font link:

```jinja
{%- if webstore_branding and webstore_branding.favicon %}
<link rel="icon" href="{{ webstore_branding.favicon }}">
{%- endif %}
```

- [ ] **Step 3: Footer from branding**

Replace the `.ws-footer-grid` and `.ws-footer-bottom` contents in `webstore_base.html`:

```jinja
		<div class="ws-footer-grid">
			<div>
				<div class="ws-footer-brand">{{ webstore_branding.wordmark }}<b>{{ webstore_branding.wordmark_bold }}</b></div>
				<p class="ws-footer-tag">{{ webstore_branding.footer_tagline }}</p>
			</div>
			{% for column in webstore_branding.footer_columns %}
			<div>
				<h6>{{ column.heading }}</h6>
				<ul>
					{% for link in column.links %}
					<li><a href="{{ link.url }}">{{ link.label }}</a></li>
					{% endfor %}
				</ul>
			</div>
			{% endfor %}
			<div>
				<h6>{{ _("Contact") }}</h6>
				<ul>
					<li><a href="mailto:{{ webstore_branding.footer_contact_email }}">{{ webstore_branding.footer_contact_email }}</a></li>
					<li>{{ webstore_branding.footer_hours }}</li>
					<li>{{ webstore_branding.footer_location }}</li>
					<li><a href="{{ webstore_branding.footer_website }}" target="_blank" rel="noopener">{{ webstore_branding.footer_website | replace("https://", "") | replace("http://", "") }}</a></li>
				</ul>
			</div>
		</div>
		<div class="ws-footer-bottom">
			<span>© {{ frappe.utils.now_datetime().year }} {{ webstore_branding.footer_copyright }} {{ _("All rights reserved.") }}</span>
			<span>{{ webstore_branding.footer_note }}</span>
		</div>
```

The Shop and Account columns are now data. Task 13's presets supply them; Task 11's patch does **not** seed them, so a site that has not configured footer links shows only the brand blurb and Contact column. That is intentional — the alternative is hardcoding the very links this work is removing.

- [ ] **Step 4: Portal eyebrow**

In `templates/webstore_portal_base.html` line 52, replace the hardcoded default:

```jinja
			<span class="ws-eyebrow">{% block portal_eyebrow %}{{ webstore_branding.portal_eyebrow }}{% endblock %}</span>
```

- [ ] **Step 5: Hero and category cards from branding**

In `www/store.html`, replace the `{% block hero %}` body. Keep the `rv` reveal classes and the `in` modifiers exactly as they are — they drive the scroll animation.

```jinja
{% block hero %}
{% if webstore_features.hero or webstore_features.category_cards %}
<div class="container ws-storefront-band">
	{% if webstore_features.hero %}
	<div class="ws-hero2">
		<div class="ws-hero2-bg"><img src="{{ webstore_branding.hero_image }}" alt=""></div>
		<div class="ws-hero2-inner">
			<span class="ws-eyebrow on-dark rv in">{{ webstore_branding.hero_eyebrow }}</span>
			<h1 class="rv in">{{ webstore_branding.hero_heading }} <em>{{ webstore_branding.hero_heading_em }}</em></h1>
			<p class="rv rv-1 in">{{ webstore_branding.hero_body }}</p>
			<div class="ws-hero2-actions rv rv-2 in">
				<a href="#catalog" class="btn btn-primary">{{ webstore_branding.hero_cta_primary }}</a>
				{% if frappe.session.user == "Guest" %}
					{% if webstore_features.signup %}
					<a href="/signup" class="btn btn-hero-ghost">{{ webstore_branding.hero_cta_secondary_guest }}</a>
					{% else %}
					<a href="/login" class="btn btn-hero-ghost">{{ _("Member login") }}</a>
					{% endif %}
				{% elif webstore_features.portal %}
				<a href="/portal" class="btn btn-hero-ghost">{{ webstore_branding.hero_cta_secondary_member }}</a>
				{% endif %}
			</div>
			{% if webstore_features.hero_stats and webstore_branding.hero_stats %}
			<div class="ws-hero2-stats rv rv-3 in">
				{% for stat in webstore_branding.hero_stats %}
				<div class="ws-hero2-stat"><b>{{ stat.value }}</b><span>{{ stat.label }}</span></div>
				{% endfor %}
			</div>
			{% endif %}
		</div>
	</div>
	{% endif %}

	{% if webstore_features.category_cards and webstore_branding.category_cards %}
	<div class="ws-cats">
		<span class="ws-eyebrow rv">{{ _("What we grow") }}</span>
		<div class="row mt-3">
			{% for card in webstore_branding.category_cards %}
			<div class="col-md-4 mb-4 rv {{ 'rv-%d' | format(loop.index0) if loop.index0 else '' }}">
				<a class="ws-catcard" href="{{ card.href }}">
					{% if card.image %}<img src="{{ card.image }}" alt="{{ card.label }}" loading="lazy">{% endif %}
					<span class="ws-catcard-arrow">↗</span>
					<span class="ws-catcard-label"><span class="t">{{ card.label }}</span><span class="n">{{ card.subtitle }}</span></span>
				</a>
			</div>
			{% endfor %}
		</div>
	</div>
	{% endif %}
</div>
{% endif %}
{% endblock %}
```

Note the two `and webstore_branding.<table>` guards: an enabled section with an empty table renders nothing rather than an empty shell, matching the spec.

- [ ] **Step 6: Add a rendering test**

Append to `upande_webstore/tests/test_branding.py`:

```python
class TestBrandingRender(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def _render_store(self):
		from frappe.website.serve import get_response_content

		return get_response_content("/store")

	def test_custom_wordmark_appears(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.wordmark = "mona"
		settings.wordmark_bold = "flowers"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		content = self._render_store()
		self.assertIn("mona<b>flowers</b>", content)

	def test_empty_category_table_renders_no_shell(self):
		self.assertNotIn("ws-cats", self._render_store())

	def test_configured_cards_render(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.append("category_cards", {"label": "Roses", "subtitle": "45+ varieties", "category": "Roses"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		content = self._render_store()
		self.assertIn("ws-catcard", content)
		self.assertIn("45+ varieties", content)
		self.assertIn("/store?category=Roses", content)
```

- [ ] **Step 7: Run tests and build**

```bash
bench --site webstore.localhost run-tests --app upande_webstore
bench build --app upande_webstore
```

Expected: PASS. Load `/store` and `/portal` — with nothing configured they must look exactly as before **except** the footer Shop/Account columns and the category cards, which are now empty pending Task 11's patch and Task 13's presets.

- [ ] **Step 8: Commit**

```bash
git add upande_webstore/templates/ upande_webstore/www/store.html upande_webstore/services/settings.py \
        upande_webstore/tests/test_branding.py
git commit -m "feat(branding): templates read resolved branding instead of literals"
```

---

### Task 10: Category image migration patch

**Files:**
- Create: `upande_webstore/patches/move_category_images_to_table.py`
- Modify: `upande_webstore/patches.txt`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`
- Modify: `upande_webstore/tests/test_settings.py`

**Interfaces:**
- Consumes: `Webstore Category Card` (Task 7).
- Produces: `execute()` — idempotent, no return value.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_settings.py`:

```python
class TestCategoryImageMigration(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()
		settings = frappe.get_doc("Webstore Settings")
		settings.set("category_cards", [])
		settings.save(ignore_permissions=True)

	def test_migrates_legacy_images_into_cards(self):
		from upande_webstore.patches.move_category_images_to_table import execute

		frappe.db.set_single_value("Webstore Settings", "flowers_category_image", "/files/f.jpg")
		frappe.db.set_single_value("Webstore Settings", "coffee_category_image", "/files/c.jpg")
		frappe.clear_cache()

		execute()

		cards = frappe.get_doc("Webstore Settings").category_cards
		self.assertEqual([card.label for card in cards], ["Flowers", "Coffee", "Fresh Produce"])
		self.assertEqual(cards[0].image, "/files/f.jpg")
		self.assertEqual(cards[1].image, "/files/c.jpg")
		self.assertIsNone(cards[2].image or None)
		self.assertEqual(cards[0].category, "Flowers")
		self.assertEqual(cards[2].category, "Fresh Produce")

	def test_is_idempotent(self):
		from upande_webstore.patches.move_category_images_to_table import execute

		frappe.db.set_single_value("Webstore Settings", "flowers_category_image", "/files/f.jpg")
		frappe.clear_cache()
		execute()
		execute()
		cards = frappe.get_doc("Webstore Settings").category_cards
		self.assertEqual(len(cards), 3)

	def test_noop_when_no_legacy_images(self):
		from upande_webstore.patches.move_category_images_to_table import execute

		for field in ("flowers_category_image", "coffee_category_image", "produce_category_image"):
			frappe.db.set_single_value("Webstore Settings", field, "")
		frappe.clear_cache()
		execute()
		self.assertEqual(frappe.get_doc("Webstore Settings").category_cards, [])
```

Note the deliberate asymmetry: with **no** legacy images the patch does nothing at all (a site that never uploaded category images should not suddenly gain three cards); with **any** legacy image set it seeds all three rows, because the shipped template always showed all three cards.

- [ ] **Step 2: Run test to verify it fails**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_settings
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the patch**

Create `upande_webstore/patches/move_category_images_to_table.py`:

```python
"""Move the three fixed category-image fields into the Webstore Category Card
child table, preserving the labels and subtitles the template hardcoded."""

import frappe

LEGACY_CARDS = (
	("flowers_category_image", "Flowers", "Roses, lilies & fillers", "Flowers"),
	("coffee_category_image", "Coffee", "AA & specialty grades", "Coffee"),
	("produce_category_image", "Fresh Produce", "Avocado & vegetables", "Fresh Produce"),
)


def execute():
	if not frappe.db.exists("DocType", "Webstore Category Card"):
		return

	settings = frappe.get_doc("Webstore Settings")

	# already migrated, or the admin has built their own cards — leave alone
	if settings.get("category_cards"):
		return

	legacy = {field: settings.get(field) for field, _l, _s, _c in LEGACY_CARDS}
	if not any(legacy.values()):
		# a site that never uploaded category images should not gain cards
		return

	for field, label, subtitle, category in LEGACY_CARDS:
		settings.append(
			"category_cards",
			{"label": label, "subtitle": subtitle, "image": legacy.get(field) or None, "category": category},
		)
	settings.flags.ignore_permissions = True
	settings.flags.ignore_validate = True
	settings.save()
	frappe.clear_cache()
```

- [ ] **Step 4: Register the patch**

In `upande_webstore/patches.txt`, under `[post_model_sync]`, add:

```
upande_webstore.patches.move_category_images_to_table
```

- [ ] **Step 5: Hide the legacy fields**

In `webstore_settings.json`, add `"hidden": 1` to `flowers_category_image`, `coffee_category_image`, `produce_category_image` and `category_images_section`. Keep the fields — dropping them would break the patch on a site migrating from further back. They can be removed in a later release.

Also remove those three from `APPEARANCE_IMAGE_FIELDS` in `services/settings.py`? **No** — leave it, because `tests/test_settings.py::test_get_appearance_defaults` asserts on them and the compatibility alias must keep working.

- [ ] **Step 6: Run tests**

```bash
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_settings
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add upande_webstore/patches/ upande_webstore/patches.txt \
        upande_webstore/upande_webstore/doctype/webstore_settings/ \
        upande_webstore/tests/test_settings.py
git commit -m "feat(branding): migrate fixed category images into the card table"
```

---

## Phase 4 — Transfer and presets

### Task 11: Export, import, apply preset

**Files:**
- Create: `upande_webstore/theme/transfer.py`
- Create: `upande_webstore/tests/test_transfer.py`

**Interfaces:**
- Consumes: `features.FEATURES` (Task 4), `branding.DEFAULTS` (Task 8), the three child tables (Task 7).
- Produces:
  - `SCHEMA_VERSION = 1`
  - `THEME_FIELDS`, `BRANDING_FIELDS`, `TABLE_FIELDS` — tuples of fieldnames.
  - `export_theme() -> dict` (whitelisted) — `{"schema": 1, "fields": {...}, "tables": {...}}`
  - `import_theme(payload) -> dict` (whitelisted) — accepts a dict or JSON string; returns `{"applied": int, "missing_images": [str]}`
  - `apply_preset(name) -> dict` (whitelisted) — same return shape.
  - `list_presets() -> list[str]` (whitelisted)

- [ ] **Step 1: Write the failing test**

Create `upande_webstore/tests/test_transfer.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestExportImport(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_export_has_schema_and_sections(self):
		from upande_webstore.theme.transfer import SCHEMA_VERSION, export_theme

		payload = export_theme()
		self.assertEqual(payload["schema"], SCHEMA_VERSION)
		self.assertIn("fields", payload)
		self.assertIn("tables", payload)
		self.assertIn("category_cards", payload["tables"])

	def test_export_excludes_general_settings(self):
		"""A theme export must not carry company or price-list config."""
		from upande_webstore.theme.transfer import export_theme

		fields = export_theme()["fields"]
		for leaked in ("company", "guest_price_list", "notification_emails"):
			self.assertNotIn(leaked, fields)

	def test_round_trip_restores_every_value(self):
		from upande_webstore.theme.transfer import export_theme, import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.accent = "#1e4d8c"
		settings.ink = "#1a1a1a"
		settings.wordmark = "mona"
		settings.wordmark_bold = "flowers"
		settings.enable_signup = 0
		settings.append("hero_stats", {"value": "45+", "label": "varieties"})
		settings.append("category_cards", {"label": "Roses", "category": "Roses"})
		settings.append("footer_links", {"column": "Shop", "label": "All", "url": "/store"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		payload = export_theme()

		# wipe, then restore
		settings = frappe.get_doc("Webstore Settings")
		settings.accent = ""
		settings.wordmark = ""
		settings.enable_signup = 1
		settings.set("hero_stats", [])
		settings.set("category_cards", [])
		settings.set("footer_links", [])
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		import_theme(payload)

		restored = frappe.get_doc("Webstore Settings")
		self.assertEqual(restored.accent, "#1e4d8c")
		self.assertEqual(restored.wordmark, "mona")
		self.assertEqual(restored.enable_signup, 0)
		self.assertEqual(len(restored.hero_stats), 1)
		self.assertEqual(restored.hero_stats[0].value, "45+")
		self.assertEqual(restored.category_cards[0].label, "Roses")
		self.assertEqual(restored.footer_links[0].column, "Shop")

	def test_import_accepts_json_string(self):
		import json

		from upande_webstore.theme.transfer import export_theme, import_theme

		payload = export_theme()
		result = import_theme(json.dumps(payload))
		self.assertIn("applied", result)

	def test_import_replaces_tables_wholesale(self):
		from upande_webstore.theme.transfer import import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.append("hero_stats", {"value": "old", "label": "old"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		import_theme({
			"schema": 1,
			"fields": {},
			"tables": {"hero_stats": [{"value": "new", "label": "new"}]},
		})
		stats = frappe.get_doc("Webstore Settings").hero_stats
		self.assertEqual(len(stats), 1)
		self.assertEqual(stats[0].value, "new")

	def test_rejects_unknown_schema_version(self):
		from upande_webstore.theme.transfer import import_theme

		with self.assertRaises(frappe.ValidationError):
			import_theme({"schema": 99, "fields": {}, "tables": {}})

	def test_rejects_payload_without_schema(self):
		from upande_webstore.theme.transfer import import_theme

		with self.assertRaises(frappe.ValidationError):
			import_theme({"fields": {}, "tables": {}})

	def test_ignores_unknown_fieldnames(self):
		"""A preset from a newer version must not blow up an older site."""
		from upande_webstore.theme.transfer import import_theme

		result = import_theme({
			"schema": 1,
			"fields": {"accent": "#1e4d8c", "not_a_real_field": "x"},
			"tables": {},
		})
		self.assertEqual(frappe.get_doc("Webstore Settings").accent, "#1e4d8c")
		self.assertNotIn("not_a_real_field", result.get("applied_fields", []))

	def test_reports_missing_images(self):
		from upande_webstore.theme.transfer import import_theme

		result = import_theme({
			"schema": 1,
			"fields": {"brand_logo": "/files/definitely-not-here.png"},
			"tables": {},
		})
		self.assertIn("/files/definitely-not-here.png", result["missing_images"])


class TestPresets(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_lists_shipped_presets(self):
		from upande_webstore.theme.transfer import list_presets

		names = list_presets()
		self.assertIn("mona_flowers", names)
		self.assertIn("upande", names)

	def test_every_preset_loads_and_validates(self):
		from upande_webstore.theme.transfer import apply_preset, list_presets

		for name in list_presets():
			apply_preset(name)  # must not raise

	def test_mona_preset_applies_navy_and_disables_signup(self):
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("mona_flowers")
		settings = frappe.get_doc("Webstore Settings")
		self.assertEqual(settings.accent, "#1e4d8c")
		self.assertEqual(settings.accent_dark, "#143562")
		self.assertEqual(settings.ink_muted, "#878c9c")
		self.assertEqual(settings.accent_drives_primary, 1)
		self.assertEqual(settings.enable_signup, 0)
		self.assertEqual(settings.wordmark_bold, "flowers")
		self.assertEqual(len(settings.category_cards), 2)

	def test_mona_preset_produces_navy_tokens(self):
		from upande_webstore.services.settings import get_settings
		from upande_webstore.theme import tokens
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("mona_flowers")
		result = tokens.get_tokens(get_settings())
		self.assertEqual(result["accent"], "#1e4d8c")
		self.assertEqual(result["primary"], "var(--ws-accent)")
		self.assertEqual(result["ink-mute"], "#878c9c")

	def test_unknown_preset_raises(self):
		from upande_webstore.theme.transfer import apply_preset

		with self.assertRaises(frappe.ValidationError):
			apply_preset("no_such_preset")

	def test_preset_name_cannot_traverse_paths(self):
		from upande_webstore.theme.transfer import apply_preset

		for evil in ("../../../etc/passwd", "..%2fupande", "a/b"):
			with self.assertRaises(frappe.ValidationError):
				apply_preset(evil)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_transfer
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `upande_webstore/theme/transfer.py`:

```python
"""Theme JSON export/import and shipped presets.

Images travel as file URLs, not embedded bytes — embedding base64 would bloat
the payload past usefulness. import_theme therefore reports URLs that do not
resolve on the target site rather than silently rendering broken images.
"""

import json
import os
import re

import frappe
from frappe import _

SCHEMA_VERSION = 1

PRESET_DIR = os.path.join(os.path.dirname(__file__), "presets")
PRESET_NAME_RE = re.compile(r"^[a-z0-9_]+$")

THEME_FIELDS = (
	"accent", "accent_dark", "accent_soft", "accent_drives_primary",
	"ink", "ink_muted", "canvas", "wash", "border", "border_strong",
	"success", "warning", "danger", "info",
	"font_sans", "font_sans_name", "font_display", "font_display_name",
	"font_mono", "font_mono_name", "google_fonts_url",
	"radius", "radius_card", "radius_panel", "custom_css",
)

BRANDING_FIELDS = (
	"site_name", "wordmark", "wordmark_bold", "wordmark_subtitle",
	"brand_logo", "favicon", "hero_image",
	"hero_eyebrow", "hero_heading", "hero_heading_em", "hero_body",
	"hero_cta_primary", "hero_cta_secondary_guest", "hero_cta_secondary_member",
	"footer_tagline", "footer_contact_email", "footer_hours", "footer_location",
	"footer_website", "footer_copyright", "footer_note", "portal_eyebrow",
)

TABLE_FIELDS = ("hero_stats", "category_cards", "footer_links")

IMAGE_FIELDS = ("brand_logo", "favicon", "hero_image")


def _feature_fields():
	from upande_webstore.theme.features import FEATURES

	return tuple(feature.fieldname for feature in FEATURES)


def _all_fields():
	return THEME_FIELDS + BRANDING_FIELDS + _feature_fields()


@frappe.whitelist()
def export_theme():
	frappe.only_for("System Manager")
	settings = frappe.get_doc("Webstore Settings")
	fields = {}
	for fieldname in _all_fields():
		value = settings.get(fieldname)
		if value not in (None, ""):
			fields[fieldname] = value

	tables = {}
	for table in TABLE_FIELDS:
		rows = []
		for row in settings.get(table) or []:
			rows.append(
				{
					key: row.get(key)
					for key in row.meta.get_valid_columns()
					if key not in ("name", "parent", "parenttype", "parentfield", "idx",
					               "owner", "creation", "modified", "modified_by", "docstatus")
					and row.get(key) not in (None, "")
				}
			)
		tables[table] = rows

	return {"schema": SCHEMA_VERSION, "fields": fields, "tables": tables}


def _resolve_payload(payload):
	if isinstance(payload, str):
		payload = json.loads(payload)
	if not isinstance(payload, dict):
		frappe.throw(_("Theme payload must be a JSON object."))
	version = payload.get("schema")
	if version != SCHEMA_VERSION:
		frappe.throw(
			_("Unsupported theme schema version {0}; this site reads version {1}.").format(
				version, SCHEMA_VERSION
			)
		)
	return payload


@frappe.whitelist()
def import_theme(payload):
	frappe.only_for("System Manager")
	payload = _resolve_payload(payload)

	settings = frappe.get_doc("Webstore Settings")
	known = set(_all_fields())
	applied_fields = []
	for fieldname, value in (payload.get("fields") or {}).items():
		if fieldname in known:
			settings.set(fieldname, value)
			applied_fields.append(fieldname)

	for table, rows in (payload.get("tables") or {}).items():
		if table in TABLE_FIELDS:
			settings.set(table, [])
			for row in rows:
				settings.append(table, row)

	settings.flags.ignore_permissions = True
	settings.save()
	frappe.clear_cache()

	return {
		"applied": len(applied_fields),
		"applied_fields": applied_fields,
		"missing_images": _missing_images(settings),
	}


def _missing_images(settings):
	missing = []
	candidates = [settings.get(field) for field in IMAGE_FIELDS]
	candidates += [row.image for row in settings.get("category_cards") or []]
	for url in candidates:
		if not url or not url.startswith("/files/") and not url.startswith("/private/files/"):
			continue
		if not frappe.db.exists("File", {"file_url": url}):
			missing.append(url)
	return missing


@frappe.whitelist()
def list_presets():
	if not os.path.isdir(PRESET_DIR):
		return []
	return sorted(
		filename[:-5] for filename in os.listdir(PRESET_DIR) if filename.endswith(".json")
	)


@frappe.whitelist()
def apply_preset(name):
	frappe.only_for("System Manager")
	if not isinstance(name, str) or not PRESET_NAME_RE.match(name):
		frappe.throw(_("Invalid preset name."))
	path = os.path.join(PRESET_DIR, f"{name}.json")
	if not os.path.isfile(path):
		frappe.throw(_("No shipped preset named {0}.").format(name))
	with open(path, encoding="utf-8") as handle:
		return import_theme(json.load(handle))
```

The `PRESET_NAME_RE` check plus `os.path.isfile` is what makes `test_preset_name_cannot_traverse_paths` pass — the regex rejects `/`, `.` and `%` outright, so no path can escape `PRESET_DIR`.

- [ ] **Step 4: Run test to verify it fails on the missing presets**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_transfer
```

Expected: the `TestExportImport` cases PASS; `TestPresets` FAIL because `presets/` is empty. Task 12 supplies them.

- [ ] **Step 5: Commit**

```bash
git add upande_webstore/theme/transfer.py upande_webstore/tests/test_transfer.py
git commit -m "feat(transfer): theme JSON export, import and preset loader"
```

---

### Task 12: Shipped presets, install seeding, and desk buttons

**Files:**
- Create: `upande_webstore/theme/presets/mona_flowers.json`
- Create: `upande_webstore/theme/presets/upande.json`
- Create: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js`
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json`
- Modify: `upande_webstore/setup/install.py`

**Interfaces:**
- Consumes: `transfer.apply_preset`, `transfer.export_theme`, `transfer.import_theme`, `transfer.list_presets` (Task 11).
- Produces: `install.seed_default_theme()` — applies `mona_flowers` only on a fresh install.

- [ ] **Step 1: Write the Mona Flowers preset**

Create `upande_webstore/theme/presets/mona_flowers.json`. Values are from their live site plus the user-supplied navy palette (Version B).

```json
{
  "schema": 1,
  "fields": {
    "accent": "#1e4d8c",
    "accent_dark": "#143562",
    "accent_soft": "#e8f0fb",
    "accent_drives_primary": 1,
    "ink": "#1a1a1a",
    "ink_muted": "#878c9c",
    "canvas": "#f7f8fa",
    "wash": "#eef0f4",
    "border": "#e2e6ed",
    "border_strong": "#c5cbd6",
    "success": "#2d6a4f",
    "warning": "#9a6700",
    "danger": "#b42318",
    "info": "#175cd3",
    "site_name": "Mona Flowers",
    "wordmark": "mona",
    "wordmark_bold": "flowers",
    "wordmark_subtitle": "Store & Customer Portal",
    "brand_logo": "/files/Mona-Flowers-Main-Logo.png",
    "hero_eyebrow": "Mona Flowers · Eldoret, Kenya",
    "hero_heading": "Graded roses,",
    "hero_heading_em": "cut to order, cooled in hours",
    "hero_body": "Export-grade roses and eucalyptus from our Eldoret farm — 45+ varieties, 40 to 120cm, quotation-first ordering with cold chain to Nairobi, the Gulf and beyond.",
    "hero_cta_primary": "Browse varieties",
    "hero_cta_secondary_guest": "Open a trade account",
    "hero_cta_secondary_member": "Go to your portal",
    "footer_tagline": "Export-grade roses and eucalyptus, grown in Eldoret and graded by stem length — ordered online, confirmed by people who know the farm.",
    "footer_contact_email": "sales@monaflowers.co.ke",
    "footer_hours": "Mon–Sat, 07:00–17:00 EAT",
    "footer_location": "P.O. Box 2707-30100, Eldoret, Kenya",
    "footer_website": "https://upande.com",
    "footer_copyright": "Mona Flowers Kenya Limited",
    "footer_note": "Powered by Upande",
    "portal_eyebrow": "Mona Flowers · Customer Portal",
    "enable_signup": 0
  },
  "tables": {
    "hero_stats": [
      {"value": "45+", "label": "rose varieties"},
      {"value": "40–120cm", "label": "stem grades"},
      {"value": "3", "label": "continents shipped"}
    ],
    "category_cards": [
      {"label": "Roses", "subtitle": "45+ varieties, 40–120cm", "category": "Roses"},
      {"label": "Eucalyptus", "subtitle": "Silver Dollar & Baby Blue", "category": "Eucalyptus"}
    ],
    "footer_links": [
      {"column": "Shop", "label": "All products", "url": "/store"},
      {"column": "Shop", "label": "Roses", "url": "/store?category=Roses"},
      {"column": "Shop", "label": "Eucalyptus", "url": "/store?category=Eucalyptus"},
      {"column": "Account", "label": "Customer portal", "url": "/portal"},
      {"column": "Account", "label": "Quotations", "url": "/portal/quotations"},
      {"column": "Account", "label": "Claims", "url": "/portal/claims"}
    ]
  }
}
```

`brand_logo` points at their existing file. On any other site that URL will not resolve and `import_theme` will report it — which is the intended behaviour, not a bug.

- [ ] **Step 2: Write the Upande preset**

Create `upande_webstore/theme/presets/upande.json` — today's copy and the ink & gold palette, so the current design is recoverable as a preset.

```json
{
  "schema": 1,
  "fields": {
    "accent": "#d9a514",
    "accent_dark": "#a87d0d",
    "accent_soft": "#f7edcd",
    "accent_drives_primary": 0,
    "ink": "#0a0a0a",
    "ink_muted": "#8a8780",
    "canvas": "#f4f3ef",
    "success": "#3f8f4f",
    "warning": "#d9962e",
    "danger": "#c4302b",
    "info": "#228883",
    "site_name": "Upande Store",
    "wordmark": "upande",
    "wordmark_bold": "store",
    "wordmark_subtitle": "Store & Customer Portal",
    "hero_eyebrow": "Upande · Nairobi · Est. for growers",
    "hero_heading": "The harvest,",
    "hero_heading_em": "straight from the farm gate",
    "hero_body": "Export-grade flowers, coffee and fresh produce from Kenyan growers — wholesale quantities, quotation-first ordering, cold chain to your door.",
    "hero_cta_primary": "Browse the catalog",
    "hero_cta_secondary_guest": "Open a trade account",
    "hero_cta_secondary_member": "Go to your portal",
    "footer_tagline": "Export-grade flowers, coffee and fresh produce from Kenyan growers — ordered online, confirmed by people who know the farms.",
    "footer_contact_email": "sales@upande.com",
    "footer_hours": "Mon–Sat, 07:00–17:00 EAT",
    "footer_location": "Nairobi, Kenya",
    "footer_website": "https://upande.com",
    "footer_copyright": "Upande Ltd.",
    "footer_note": "Quotation-first ordering · No payment taken online",
    "portal_eyebrow": "Upande Store · Customer Portal"
  },
  "tables": {
    "hero_stats": [
      {"value": "40+", "label": "partner growers"},
      {"value": "24h", "label": "quotation turnaround"},
      {"value": "4°C", "label": "cold chain, farm to door"}
    ],
    "category_cards": [
      {"label": "Flowers", "subtitle": "Roses, lilies & fillers", "category": "Flowers", "image": "/assets/upande_webstore/images/site/cat-flowers.jpg"},
      {"label": "Coffee", "subtitle": "AA & specialty grades", "category": "Coffee", "image": "/assets/upande_webstore/images/site/cat-coffee.jpg"},
      {"label": "Fresh Produce", "subtitle": "Avocado & vegetables", "category": "Fresh Produce", "image": "/assets/upande_webstore/images/site/cat-produce.jpg"}
    ],
    "footer_links": [
      {"column": "Shop", "label": "All products", "url": "/store"},
      {"column": "Shop", "label": "Flowers", "url": "/store?category=Flowers"},
      {"column": "Shop", "label": "Coffee", "url": "/store?category=Coffee"},
      {"column": "Shop", "label": "Fresh Produce", "url": "/store?category=Fresh%20Produce"},
      {"column": "Account", "label": "Customer portal", "url": "/portal"},
      {"column": "Account", "label": "Quotations", "url": "/portal/quotations"},
      {"column": "Account", "label": "Claims", "url": "/portal/claims"},
      {"column": "Account", "label": "Team desk", "url": "/app"}
    ]
  }
}
```

Note `upande.json` deliberately sets **no** `accent_drives_primary` remap and its category images point at shipped assets (which always resolve), so applying it restores today's look exactly.

- [ ] **Step 3: Run the preset tests**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_transfer
```

Expected: PASS, including `TestPresets`.

- [ ] **Step 4: Add the Transfer tab**

In `webstore_settings.json`, append:

```json
{"fieldname": "transfer_tab", "fieldtype": "Tab Break", "label": "Transfer"},
{"fieldname": "preset_section", "fieldtype": "Section Break", "label": "Shipped Presets"},
{"fieldname": "preset", "fieldtype": "Select", "label": "Preset", "description": "Applying a preset overwrites every Theme, Branding and Features value."},
{"fieldname": "transfer_section", "fieldtype": "Section Break", "label": "Export / Import"},
{"fieldname": "theme_file", "fieldtype": "Attach", "label": "Theme JSON", "description": "Attach an exported theme, then press Import Theme."}
```

- [ ] **Step 5: Write the client script**

Create `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.js`:

```javascript
frappe.ui.form.on("Webstore Settings", {
	refresh(frm) {
		frappe.call("upande_webstore.theme.transfer.list_presets").then((r) => {
			frm.set_df_property("preset", "options", [""].concat(r.message || []).join("\n"));
		});

		frm.add_custom_button(__("Export Theme"), () => {
			frappe.call("upande_webstore.theme.transfer.export_theme").then((r) => {
				const blob = new Blob([JSON.stringify(r.message, null, 2)], {
					type: "application/json",
				});
				const link = document.createElement("a");
				link.href = URL.createObjectURL(blob);
				link.download = "webstore-theme.json";
				link.click();
				URL.revokeObjectURL(link.href);
			});
		}, __("Theme"));

		frm.add_custom_button(__("Import Theme"), () => {
			if (!frm.doc.theme_file) {
				frappe.msgprint(__("Attach a theme JSON first."));
				return;
			}
			frappe.confirm(
				__("This overwrites every Theme, Branding and Features value. Continue?"),
				() => {
					fetch(frm.doc.theme_file)
						.then((res) => res.json())
						.then((payload) =>
							frappe.call("upande_webstore.theme.transfer.import_theme", { payload })
						)
						.then((r) => report(frm, r.message));
				}
			);
		}, __("Theme"));

		frm.add_custom_button(__("Apply Preset"), () => {
			if (!frm.doc.preset) {
				frappe.msgprint(__("Pick a preset first."));
				return;
			}
			frappe.confirm(
				__("Apply preset {0}? This overwrites every Theme, Branding and Features value.", [
					frm.doc.preset,
				]),
				() => {
					frappe
						.call("upande_webstore.theme.transfer.apply_preset", { name: frm.doc.preset })
						.then((r) => report(frm, r.message));
				}
			);
		}, __("Theme"));
	},
});

function report(frm, result) {
	frm.reload_doc();
	let message = __("Applied {0} settings.", [result.applied]);
	if (result.missing_images && result.missing_images.length) {
		message +=
			"<br><br>" +
			__("These images do not exist on this site and need re-uploading:") +
			"<ul><li>" +
			result.missing_images.join("</li><li>") +
			"</li></ul>";
	}
	frappe.msgprint({ title: __("Theme Applied"), message, indicator: "green" });
}
```

Both destructive actions are behind `frappe.confirm`, and the missing-image report surfaces in the same dialog.

- [ ] **Step 6: Seed the preset on fresh install**

In `upande_webstore/setup/install.py`, add:

```python
def seed_default_theme():
	"""Fresh installs get the Mona Flowers preset. A site that already has a
	configured Webstore Settings is never touched, so deploys are safe."""
	if frappe.db.get_single_value("Webstore Settings", "accent"):
		return
	if frappe.get_all("Webstore Category Card", limit=1):
		return
	from upande_webstore.theme.transfer import apply_preset

	apply_preset("mona_flowers")
```

Add `import frappe` at the top if absent, call `seed_default_theme()` from `after_install()` only — **not** from `after_migrate()`:

```python
def after_install():
	create_webstore_custom_fields()
	seed_default_theme()


def after_migrate():
	create_webstore_custom_fields()
```

- [ ] **Step 7: Run the full suite and build**

```bash
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore
bench build --app upande_webstore
```

Expected: PASS.

- [ ] **Step 8: Manually verify the round trip**

Open `/app/webstore-settings`, Transfer tab. Apply `mona_flowers`, confirm, and reload `/store`: navy buttons, navy active nav pill, `mona`**`flowers`** wordmark, two category cards, Eldoret footer, no signup link anywhere. Then apply `upande` and confirm the storefront returns to ink & gold.

- [ ] **Step 9: Commit**

```bash
git add upande_webstore/theme/presets/ upande_webstore/setup/install.py \
        upande_webstore/upande_webstore/doctype/webstore_settings/
git commit -m "feat(transfer): Mona Flowers and Upande presets, desk buttons, install seeding"
```

---

## Phase 5 — Integration

### Task 13: Consolidate the context payload and document

**Files:**
- Modify: `upande_webstore/theme/__init__.py`
- Modify: `upande_webstore/services/settings.py`
- Modify: `README.md`
- Modify: `upande_webstore/tests/test_theme.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `theme.get_theme(settings=None) -> frappe._dict` with keys `tokens`, `custom_css`, `font_link`, `branding`, `features`.

- [ ] **Step 1: Write the failing test**

Append to `upande_webstore/tests/test_theme.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestGetTheme(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_payload_shape(self):
		from upande_webstore.theme import get_theme

		theme = get_theme()
		for key in ("tokens", "custom_css", "font_link", "branding", "features"):
			self.assertIn(key, theme)

	def test_blank_site_emits_no_tokens(self):
		from upande_webstore.theme import get_theme

		self.assertEqual(get_theme().tokens, {})

	def test_context_keys_all_present(self):
		from upande_webstore.services.settings import update_website_context

		context = frappe._dict()
		update_website_context(context)
		for key in (
			"webstore_tokens", "webstore_custom_css", "webstore_font_link",
			"webstore_branding", "webstore_features", "webstore_appearance",
		):
			self.assertIn(key, context)

	def test_appearance_alias_still_works(self):
		"""Backward-compat alias must survive until the next release."""
		from upande_webstore.services.settings import update_website_context

		context = frappe._dict()
		update_website_context(context)
		self.assertIn("colors", context.webstore_appearance)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
bench --site webstore.localhost run-tests --app upande_webstore --module upande_webstore.tests.test_theme
```

Expected: FAIL — `ImportError: cannot import name 'get_theme'`

- [ ] **Step 3: Write the consolidated payload**

Replace `upande_webstore/theme/__init__.py`:

```python
"""Webstore theme: seed-driven tokens, brand copy and feature flags.

One entry point so every website page gets the same payload from one cached
settings read.
"""

import frappe


def get_theme(settings=None):
	from upande_webstore.theme import branding, features, fonts, tokens

	if settings is None:
		from upande_webstore.services.settings import get_settings

		settings = get_settings()

	return frappe._dict(
		tokens=tokens.get_tokens(settings),
		custom_css=tokens.get_custom_css(settings),
		font_link=fonts.resolve(settings)["link"],
		branding=branding.get_branding(settings),
		features=features.enabled(),
	)
```

- [ ] **Step 4: Collapse the context wiring**

In `services/settings.py`, replace the accumulated `update_website_context` with:

```python
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
```

- [ ] **Step 5: Document it**

Replace the README's Appearance section with a Customisation section covering: the five tabs; that every field is optional and blank means shipped default; the 13 seeds and what derives from each; `accent_drives_primary`; the 19 flags and the three enforcement layers; export/import and the two shipped presets; and the note that images travel as URLs so they need re-uploading across sites.

Include this table verbatim:

| Tab | What it controls |
|---|---|
| Theme | 13 color seeds → the full `--ws-*` set, fonts, radii, custom CSS |
| Branding | Logo, favicon, wordmark, hero copy, hero stats, category cards, footer |
| Features | 19 checkboxes; off = hidden **and** 404 **and** API rejected |
| Transfer | Export/import theme JSON, apply a shipped preset |

- [ ] **Step 6: Run everything**

```bash
cd /home/austin/frappe-v16-bench
bench --site webstore.localhost migrate
bench --site webstore.localhost run-tests --app upande_webstore
bench build --app upande_webstore
```

Expected: full suite PASS, clean build.

- [ ] **Step 7: Verify both presets end to end**

Apply `upande`, load `/store` and `/portal`, confirm the ink & gold design is pixel-identical to `main`. Apply `mona_flowers`, confirm navy throughout. Then clear every seed and confirm no `<style>` block is emitted in the page source.

- [ ] **Step 8: Commit**

```bash
git add upande_webstore/theme/__init__.py upande_webstore/services/settings.py \
        README.md upande_webstore/tests/test_theme.py
git commit -m "feat(theme): single get_theme() payload and customisation docs"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: delivery mechanism → 3·6; code organisation → 1,2,4,8,11,13; form layout → 3·4, 4·5, 8·4, 12·4; color seeds → 1,2; ink derivation incl. the measured divergence → 1; surface ladder → 1; accent-drives-primary → 2,3; typography → 2,3; shape/advanced → 2,3; 19 flags → 4; three enforcement layers → 4,5,6; dependent flags → 4·6, 6·6; branding DEFAULTS → 8; three child tables → 7; migration patch → 10; transfer → 11; presets → 12; install behaviour → 12·6; error-handling table → 1 (bad hex), 2 (font host), 11 (schema, missing images), 5 (404/403); all six test files → 1,2,4,5,6,8,10,11,13.

**Deliberate spec deviations, both to avoid re-hardcoding what this work removes:**
1. The footer Shop/Account columns become data with no template fallback, so an unconfigured site shows only the brand blurb and Contact column until a preset is applied. Recorded in Task 9 Step 3.
2. The category migration patch seeds three rows only if at least one legacy image was set. A site that never uploaded any gains no cards. Recorded in Task 10 Step 1.

**Placeholder scan.** No TBDs; every code step carries real code; no "similar to Task N" references.

**Type consistency.** `get_tokens`/`get_custom_css` take a `.get()`-able and return `dict`/`str` (Tasks 2, 3, 13). `fonts.resolve` returns the same four keys everywhere. `features.enabled()` returns `frappe._dict` so Jinja attribute access works (Tasks 4, 6). `branding.get_branding(settings=None)` — the optional arg is used in Tasks 9 and 13. `transfer` returns `{applied, applied_fields, missing_images}` from both `import_theme` and `apply_preset`, which the JS `report()` consumes. Child-table field names are fixed in Task 7 and used identically in 8, 10, 11 and 12. Token keys are bare (no `--ws-` prefix) in `get_tokens`; only the template prepends it.

---

Plan complete and saved to `docs/superpowers/plans/2026-07-28-configurable-ui.md`.
