import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.utils import setup_webstore_settings

from upande_webstore.theme import color, occasion, tokens

SHIPPED = {"valentines", "womens_day", "mothers_day", "easter", "all_saints", "christmas"}

STATUS_SEEDS = ("success", "warning", "danger", "info")

MONA = {
	"accent": "#1e4d8c",
	"accent_dark": "#143562",
	"accent_soft": "#e8f0fb",
	"ink": "#1a1a1a",
	"ink_muted": "#878c9c",
	"canvas": "#f7f8fa",
	"wash": "#eef0f4",
	"success": "#2d6a4f",
	"danger": "#b42318",
}


class TestLoad(unittest.TestCase):
	def test_loads_a_shipped_occasion(self):
		loaded = occasion.load("valentines")
		self.assertEqual(loaded["name"], "valentines")
		self.assertEqual(loaded["label"], "Valentine's Day")
		self.assertEqual(loaded["seeds"]["accent"], "#b3122d")

	def test_unknown_name_returns_none(self):
		self.assertIsNone(occasion.load("no_such_occasion"))

	def test_path_traversal_is_rejected(self):
		self.assertIsNone(occasion.load("../presets/mona_flowers"))
		self.assertIsNone(occasion.load("valentines.json"))

	def test_non_string_name_returns_none(self):
		self.assertIsNone(occasion.load(None))

	def test_list_names_includes_shipped(self):
		self.assertIn("valentines", occasion.list_names())


class TestShippedOccasions(unittest.TestCase):
	def loaded(self):
		return [occasion.load(name) for name in occasion.list_names()]

	def test_all_six_ship(self):
		self.assertEqual(set(occasion.list_names()), SHIPPED)

	def test_every_file_parses_and_is_labelled(self):
		for loaded in self.loaded():
			self.assertIsNotNone(loaded)
			self.assertTrue(loaded["label"])
			self.assertNotEqual(loaded["label"], loaded["name"])

	def test_every_seed_is_whitelisted_and_valid_hex(self):
		for loaded in self.loaded():
			for field, value in loaded["seeds"].items():
				self.assertIn(field, occasion.SEED_FIELDS)
				self.assertIsNotNone(color.parse(value), f"{loaded['name']}.{field}")

	def test_no_occasion_touches_a_status_colour(self):
		for loaded in self.loaded():
			for seed in STATUS_SEEDS:
				self.assertNotIn(seed, loaded["seeds"])

	def test_every_occasion_has_banner_text(self):
		for loaded in self.loaded():
			self.assertTrue(loaded["banner"].get("text"), loaded["name"])

	def test_every_accent_clears_wcag_aa(self):
		"""on-accent is contrast-picked across the CTA gradient, so a bad accent
		fails here rather than on a farm's live site."""
		for loaded in self.loaded():
			accent = color.parse(loaded["seeds"].get("accent"))
			if not accent:
				continue
			scale = color.accent_scale(
				accent,
				color.parse(loaded["seeds"].get("accent_dark")),
				color.parse(loaded["seeds"].get("accent_soft")),
			)
			deep = color.parse(scale["accent-deep"])
			chosen = color.best_contrast((deep, accent), (color.BLACK, color.WHITE))
			worst = min(color.contrast(bg, chosen) for bg in (deep, accent))
			self.assertGreaterEqual(worst, 4.5, f"{loaded['name']} accent fails AA")


class TestSeedMerge(unittest.TestCase):
	def test_no_occasion_leaves_tokens_untouched(self):
		self.assertEqual(tokens.get_tokens(MONA), tokens.get_tokens(MONA, None))

	def test_occasion_accent_drives_the_whole_derived_ramp(self):
		out = tokens.get_tokens(MONA, occasion.load("valentines"))
		self.assertEqual(out["accent"], "#b3122d")
		self.assertEqual(out["accent-deep"], "#7d0c1f")
		# the derived tokens must follow the occasion, not stay Mona-blue
		self.assertNotEqual(out["accent-hover"], tokens.get_tokens(MONA)["accent-hover"])
		self.assertIn("179, 18, 45", out["ring"])

	def test_farm_accent_soft_does_not_survive_an_occasion_accent(self):
		"""Mona seeds a blue accent_soft; under a red accent that would clash."""
		out = tokens.get_tokens(MONA, occasion.load("valentines"))
		self.assertEqual(out["accent-soft"], "#fdeef0")
		self.assertNotEqual(out["accent-soft"], "#e8f0fb")

	def test_group_omitted_by_the_occasion_keeps_the_farm_value(self):
		"""valentines sets no surface group, so Mona's canvas survives."""
		out = tokens.get_tokens(MONA, occasion.load("valentines"))
		self.assertEqual(out["bg"], "#f7f8fa")

	def test_occasion_surface_group_replaces_the_farm_canvas(self):
		out = tokens.get_tokens(MONA, occasion.load("christmas"))
		self.assertEqual(out["bg"], "#faf7f2")

	def test_status_colours_are_never_touched(self):
		base = tokens.get_tokens(MONA)
		for name in occasion.list_names():
			out = tokens.get_tokens(MONA, occasion.load(name))
			for token in ("success", "destructive"):
				self.assertEqual(out[token], base[token], f"{name} moved {token}")


class TestIsolationFromTransfer(unittest.TestCase):
	def test_occasion_fields_are_not_theme_fields(self):
		"""Campaign state is not theme state: importing a base theme must not
		kill a running campaign, and exporting must not carry a farm's date."""
		from upande_webstore.theme.transfer import all_fields

		fields = set(all_fields())
		for field in ("occasion", "occasion_runs_until", *occasion.BANNER_OVERRIDES):
			self.assertNotIn(field, fields)


class TestHeroOverlay(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_occasion_hero_beats_the_farms_own_copy(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.hero_heading = "Graded roses,"
		settings.hero_eyebrow = "Mona Flowers · Eldoret, Kenya"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		resolved = get_branding(settings, occasion.load("valentines"))
		self.assertEqual(resolved["hero_heading"], "Red Naomi, graded and")
		self.assertEqual(resolved["hero_eyebrow"], "Valentine's · February allocation")

	def test_farm_copy_survives_keys_the_occasion_omits(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.hero_body = "Export-grade roses from our Eldoret farm."
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		# valentines.json carries no hero body
		resolved = get_branding(settings, occasion.load("valentines"))
		self.assertEqual(resolved["hero_body"], "Export-grade roses from our Eldoret farm.")

	def test_no_occasion_is_unchanged(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		self.assertEqual(
			get_branding(settings)["hero_heading"], get_branding(settings, None)["hero_heading"]
		)


class TestActive(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def set_occasion(self, **values):
		settings = frappe.get_doc("Webstore Settings")
		for field, value in values.items():
			settings.set(field, value)
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		return settings

	def test_blank_is_none(self):
		self.assertIsNone(occasion.active(self.set_occasion(occasion="")))

	def test_named_occasion_resolves(self):
		active = occasion.active(self.set_occasion(occasion="valentines"))
		self.assertEqual(active.name, "valentines")
		self.assertEqual(active.banner["cta_label"], "Talk to us")

	def test_future_end_date_still_resolves(self):
		settings = self.set_occasion(
			occasion="valentines", occasion_runs_until=add_days(nowdate(), 3)
		)
		self.assertIsNotNone(occasion.active(settings))

	def test_todays_end_date_still_resolves(self):
		settings = self.set_occasion(occasion="valentines", occasion_runs_until=nowdate())
		self.assertIsNotNone(occasion.active(settings))

	def test_past_end_date_stops_the_overlay(self):
		settings = self.set_occasion(
			occasion="valentines", occasion_runs_until=add_days(nowdate(), -1)
		)
		self.assertIsNone(occasion.active(settings))

	def test_farm_banner_text_beats_the_file(self):
		settings = self.set_occasion(
			occasion="valentines", occasion_banner_text="Cutoff 20 January — order now"
		)
		self.assertEqual(occasion.active(settings).banner["text"], "Cutoff 20 January — order now")

	def test_blank_override_falls_back_to_the_file(self):
		settings = self.set_occasion(occasion="valentines", occasion_banner_text="   ")
		self.assertIn("February allocation", occasion.active(settings).banner["text"])

	def test_activation_writes_nothing(self):
		"""The overlay is resolved, never persisted — that is what makes it safe
		to switch off without a restore step."""
		self.set_occasion(occasion="valentines")
		occasion.active()
		self.assertEqual(frappe.db.get_single_value("Webstore Settings", "accent") or "", "")

	def test_unknown_name_does_not_raise(self):
		"""Reachable when an app version drops an occasion a site still names —
		validate blocks it through the desk, so this writes past validate."""
		frappe.db.set_single_value("Webstore Settings", "occasion", "no_such_occasion")
		frappe.clear_cache()
		self.assertIsNone(occasion.active(frappe.get_doc("Webstore Settings")))

	def test_validate_rejects_an_unknown_occasion(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.occasion = "no_such_occasion"
		self.assertRaises(frappe.ValidationError, settings.save)


class TestContext(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_theme_exposes_the_occasion(self):
		from upande_webstore.theme import get_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.occasion = "valentines"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		theme = get_theme()
		self.assertEqual(theme.occasion.name, "valentines")
		self.assertEqual(theme.tokens["accent"], "#b3122d")
		self.assertEqual(theme.branding["hero_heading"], "Red Naomi, graded and")

	def test_no_occasion_leaves_the_context_key_empty(self):
		from upande_webstore.theme import get_theme

		self.assertIsNone(get_theme().occasion)
