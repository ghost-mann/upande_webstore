import unittest

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings

from upande_webstore.theme import color, fonts, tokens

MONA = {
	"accent": "#1e4d8c",
	"accent_dark": "#143562",
	"accent_soft": "#e8f0fb",
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
	"accent_drives_primary": 1,
}


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
		self.assertEqual(color.to_hex((127.5, 0, 255)), "#8000ff")
		self.assertEqual(color.to_hex((-10, 300, 128)), "#00ff80")

	def test_rgba(self):
		self.assertEqual(color.rgba((22, 101, 52), 0.35), "rgba(22, 101, 52, 0.35)")


class TestInkScale(unittest.TestCase):
	SHIPPED = {
		"ink": "#0a0a0a",
		"ink-1": "#1a1a18",
		"ink-2": "#2a2a26",
		"ink-3": "#3a3a34",
		"ink-4": "#5a5a52",
		"ink-mute": "#8a8780",
		"ink-faint": "#b8b6ae",
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


class TestContrast(unittest.TestCase):
	INK = (10, 10, 10)
	CREAM = (250, 250, 246)

	def test_luminance_endpoints(self):
		self.assertAlmostEqual(color.relative_luminance((0, 0, 0)), 0.0, places=6)
		self.assertAlmostEqual(color.relative_luminance((255, 255, 255)), 1.0, places=6)

	def test_contrast_is_symmetric_and_bounded(self):
		self.assertAlmostEqual(color.contrast(self.INK, self.CREAM), color.contrast(self.CREAM, self.INK))
		self.assertAlmostEqual(color.contrast((0, 0, 0), (255, 255, 255)), 21.0, places=4)
		self.assertAlmostEqual(color.contrast(self.INK, self.INK), 1.0, places=6)

	def test_known_ratio(self):
		# gold accent against ink — the pairing the shipped CTA relies on
		self.assertAlmostEqual(color.contrast((217, 165, 20), self.INK), 8.81, places=1)

	def test_light_background_picks_dark_text(self):
		self.assertEqual(
			color.best_contrast([(217, 165, 20)], (self.INK, self.CREAM)), self.INK
		)

	def test_dark_background_picks_light_text(self):
		self.assertEqual(
			color.best_contrast([(30, 77, 140)], (self.INK, self.CREAM)), self.CREAM
		)

	def test_judges_worst_background_not_the_average(self):
		"""Text over a gradient must clear both ends; a midpoint-only choice
		would let one end fail."""
		pale, deep = (226, 188, 79), (22, 58, 105)
		# cream wins on deep alone, ink wins on pale alone; across both, the
		# choice must be the one whose WORST end is better
		chosen = color.best_contrast([pale, deep], (self.INK, self.CREAM))
		worst_chosen = min(color.contrast(bg, chosen) for bg in (pale, deep))
		other = self.CREAM if chosen == self.INK else self.INK
		worst_other = min(color.contrast(bg, other) for bg in (pale, deep))
		self.assertGreaterEqual(worst_chosen, worst_other)


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
		self.assertEqual(scale["wash"], "rgba(10, 10, 10, 0.04)")
		# must match the SCSS default so seeding ink alone shifts nothing
		self.assertEqual(scale["hairline-strong"], "rgba(10, 10, 10, 0.16)")

	def test_surface_is_a_lift_toward_white(self):
		"""--ws-surface must sit BETWEEN canvas and white, never below canvas."""
		canvas = (247, 248, 250)
		scale = color.surface_scale((26, 26, 26), canvas, None, None, None)
		# banker's rounding: 252.5 -> 252, hence fc not fd on the blue channel
		self.assertEqual(scale["surface"], "#fbfcfc")
		self.assertEqual(scale["card"], "#ffffff")
		# the property the literal above is standing in for
		for channel, base in zip(color.parse(scale["surface"]), canvas):
			self.assertGreaterEqual(channel, base)
			self.assertLessEqual(channel, 255)

	def test_wash_is_sunken_below_canvas(self):
		"""Mona's second surface is DARKER than the canvas: a fill, not a lift."""
		scale = color.surface_scale(
			(26, 26, 26), (247, 248, 250), (238, 240, 244), None, None
		)
		for channel, base in zip(color.parse(scale["wash"]), (247, 248, 250)):
			self.assertLess(channel, base)

	def test_shadows_use_ink_seed_not_hardcoded_black(self):
		scale = color.surface_scale((30, 77, 140), (247, 248, 250), None, None, None)
		self.assertIn("rgba(30, 77, 140", scale["shadow-card"])


class TestStatusScale(unittest.TestCase):
	def test_derives_deep_light_and_soft(self):
		scale = color.status_scale((45, 106, 79))
		self.assertEqual(scale["base"], "#2d6a4f")
		self.assertEqual(scale["deep"], "#285d46")
		self.assertEqual(scale["soft"], "rgba(45, 106, 79, 0.12)")
		# light is the brighter fill tone the two-tone warning pair needs
		self.assertEqual(scale["light"], "#628f7b")
		for light, base in zip(color.parse(scale["light"]), (45, 106, 79)):
			self.assertGreater(light, base)

	def test_returns_empty_without_seed(self):
		self.assertEqual(color.status_scale(None), {})


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
			"",
			None,
		):
			self.assertFalse(fonts.is_allowed_url(bad), f"expected reject for {bad!r}")

	def test_resolve_blank_returns_nones(self):
		resolved = fonts.resolve({})
		self.assertIsNone(resolved["sans"])
		self.assertIsNone(resolved["link"])

	def test_resolve_shipped_family(self):
		resolved = fonts.resolve({"font_sans": "Poppins"})
		self.assertEqual(resolved["sans"], fonts.STACKS["Poppins"])

	def test_resolve_custom_family_uses_name_field(self):
		resolved = fonts.resolve(
			{
				"font_sans": "Custom",
				"font_sans_name": "Inter",
				"google_fonts_url": "https://fonts.googleapis.com/css2?family=Inter",
			}
		)
		self.assertTrue(resolved["sans"].startswith('"Inter"'))
		self.assertEqual(resolved["link"], "https://fonts.googleapis.com/css2?family=Inter")

	def test_disallowed_url_yields_no_link(self):
		resolved = fonts.resolve({"google_fonts_url": "https://evil.example.com/f.css"})
		self.assertIsNone(resolved["link"])


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
		# grad-ink still follows the ink seed, but must not reference the accent
		self.assertNotIn("accent", result["grad-ink"])

	def test_malformed_hex_treated_as_unset(self):
		result = tokens.get_tokens(
			{"accent": "not-a-color", "ink": "#1a1a1a", "canvas": "#f7f8fa"}
		)
		self.assertNotIn("accent", result)
		self.assertEqual(result["ink"], "#1a1a1a")

	def test_shape_and_font_tokens(self):
		result = tokens.get_tokens(
			{
				"radius": "4px",
				"radius_card": "6px",
				"radius_panel": "8px",
				"font_sans": "Poppins",
			}
		)
		self.assertEqual(result["radius"], "4px")
		self.assertEqual(result["radius-card"], "6px")
		self.assertEqual(result["radius-panel"], "8px")
		self.assertIn("Poppins", result["font-sans"])

	def test_status_seed_fills_its_whole_family(self):
		result = tokens.get_tokens({"success": "#2d6a4f"})
		self.assertEqual(result["success"], "#2d6a4f")
		self.assertEqual(result["success-deep"], "#285d46")
		self.assertEqual(result["success-soft"], "rgba(45, 106, 79, 0.12)")

	def test_danger_maps_to_destructive_tokens(self):
		"""The SCSS calls it 'destructive'; the field is 'danger'."""
		result = tokens.get_tokens({"danger": "#b42318"})
		self.assertEqual(result["destructive"], "#b42318")
		self.assertIn("destructive-soft", result)

	def test_on_accent_is_readable_over_the_whole_cta_gradient(self):
		"""The CTA fill runs accent-deep -> accent; the derived text colour must
		clear WCAG AA at both ends, for any client accent."""
		cases = [
			{"accent": "#d9a514", "accent_dark": "#a87d0d", "ink": "#0a0a0a", "canvas": "#f4f3ef"},
			{"accent": "#1e4d8c", "accent_dark": "#143562", "ink": "#1a1a1a", "canvas": "#f7f8fa"},
			{"accent": "#b3123f", "ink": "#14100f", "canvas": "#f6f1ef"},
			{"accent": "#f2e9c9", "ink": "#0a0a0a", "canvas": "#ffffff"},
			{"accent": "#0b1a2b", "ink": "#0a0a0a", "canvas": "#f4f3ef"},
		]
		for seeds in cases:
			result = tokens.get_tokens(seeds)
			text = color.parse(result["on-accent"])
			ends = (color.parse(result["accent-deep"]), color.parse(result["accent"]))
			worst = min(color.contrast(end, text) for end in ends)
			self.assertGreaterEqual(
				worst, 4.5, f"accent {seeds['accent']} -> text {result['on-accent']} only {worst:.2f}:1"
			)

	def test_on_accent_absent_without_accent(self):
		self.assertNotIn("on-accent", tokens.get_tokens({"ink": "#1a1a1a"}))

	def test_gold_takes_ink_and_navy_takes_cream(self):
		gold = tokens.get_tokens({"accent": "#d9a514", "accent_dark": "#a87d0d", "ink": "#0a0a0a"})
		navy = tokens.get_tokens({"accent": "#1e4d8c", "accent_dark": "#143562", "ink": "#1a1a1a"})
		self.assertEqual(gold["on-accent"], "#0a0a0a")
		self.assertNotEqual(navy["on-accent"], "#1a1a1a")

	def test_custom_css_passthrough(self):
		self.assertEqual(tokens.get_custom_css({"custom_css": "--ws-x: 1;"}), "--ws-x: 1;")
		self.assertEqual(tokens.get_custom_css({}), "")

	def test_theme_fields_all_readable(self):
		"""THEME_FIELDS is the export contract; every entry must be one this
		module actually consumes."""
		settings = {field: "" for field in tokens.THEME_FIELDS}
		self.assertEqual(tokens.get_tokens(settings), {})
		self.assertEqual(len(tokens.THEME_FIELDS), len(set(tokens.THEME_FIELDS)))


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
			"webstore_tokens",
			"webstore_custom_css",
			"webstore_font_link",
			"webstore_branding",
			"webstore_features",
			"webstore_appearance",
		):
			self.assertIn(key, context)

	def test_appearance_alias_still_works(self):
		"""Backward-compat alias must survive until the next release."""
		from upande_webstore.services.settings import update_website_context

		context = frappe._dict()
		update_website_context(context)
		self.assertIn("colors", context.webstore_appearance)

	def test_features_are_attribute_accessible_for_jinja(self):
		from upande_webstore.theme import get_theme

		self.assertTrue(get_theme().features.wishlist)

	def test_branding_is_attribute_accessible_for_jinja(self):
		from upande_webstore.theme import get_theme

		self.assertEqual(get_theme().branding.wordmark, "upande")
