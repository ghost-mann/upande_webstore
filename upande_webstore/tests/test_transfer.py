import json

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
		for table in ("hero_stats", "category_cards", "footer_links"):
			self.assertIn(table, payload["tables"])

	def test_export_excludes_general_settings(self):
		"""A theme export must not carry company or price-list config."""
		from upande_webstore.theme.transfer import export_theme

		fields = export_theme()["fields"]
		for leaked in ("company", "guest_price_list", "notification_emails", "warehouses"):
			self.assertNotIn(leaked, fields)

	def test_export_rows_carry_no_bookkeeping_columns(self):
		from upande_webstore.theme.transfer import export_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.append("hero_stats", {"value": "45+", "label": "varieties"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		row = export_theme()["tables"]["hero_stats"][0]
		self.assertEqual(set(row), {"value", "label"})

	def test_round_trip_restores_every_value(self):
		from upande_webstore.theme.transfer import export_theme, import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.accent = "#1e4d8c"
		settings.ink = "#1a1a1a"
		settings.accent_drives_primary = 1
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
		settings.ink = ""
		settings.accent_drives_primary = 0
		settings.wordmark = ""
		settings.wordmark_bold = ""
		settings.enable_signup = 1
		for table in ("hero_stats", "category_cards", "footer_links"):
			settings.set(table, [])
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		import_theme(payload)

		restored = frappe.get_doc("Webstore Settings")
		self.assertEqual(restored.accent, "#1e4d8c")
		self.assertEqual(restored.ink, "#1a1a1a")
		self.assertEqual(restored.accent_drives_primary, 1)
		self.assertEqual(restored.wordmark, "mona")
		self.assertEqual(restored.wordmark_bold, "flowers")
		self.assertEqual(restored.enable_signup, 0)
		self.assertEqual(len(restored.hero_stats), 1)
		self.assertEqual(restored.hero_stats[0].value, "45+")
		self.assertEqual(restored.category_cards[0].label, "Roses")
		self.assertEqual(restored.footer_links[0].column, "Shop")

	def test_import_accepts_json_string(self):
		from upande_webstore.theme.transfer import export_theme, import_theme

		result = import_theme(json.dumps(export_theme()))
		self.assertIn("applied", result)

	def test_import_replaces_tables_wholesale(self):
		from upande_webstore.theme.transfer import import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.append("hero_stats", {"value": "old", "label": "old"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		import_theme(
			{
				"schema": 1,
				"fields": {},
				"tables": {"hero_stats": [{"value": "new", "label": "new"}]},
			}
		)
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

	def test_rejects_malformed_json(self):
		from upande_webstore.theme.transfer import import_theme

		with self.assertRaises(frappe.ValidationError):
			import_theme("{not json")

	def test_ignores_unknown_fieldnames(self):
		"""A preset from a newer version must not blow up an older site."""
		from upande_webstore.theme.transfer import import_theme

		result = import_theme(
			{
				"schema": 1,
				"fields": {"accent": "#1e4d8c", "not_a_real_field": "x"},
				"tables": {},
			}
		)
		self.assertEqual(frappe.get_doc("Webstore Settings").accent, "#1e4d8c")
		self.assertNotIn("not_a_real_field", result["applied_fields"])
		self.assertIn("accent", result["applied_fields"])

	def test_ignores_unknown_tables(self):
		from upande_webstore.theme.transfer import import_theme

		import_theme({"schema": 1, "fields": {}, "tables": {"warehouses": []}})
		# the general-settings table must survive a theme import untouched
		self.assertTrue(frappe.get_doc("Webstore Settings").warehouses)

	def test_import_resets_fields_absent_from_payload(self):
		"""Replace semantics: a field the payload omits goes back to its default,
		so switching themes cannot leave residue behind."""
		from upande_webstore.theme.transfer import import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.accent = "#1e4d8c"
		settings.wordmark = "mona"
		settings.enable_signup = 0
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		import_theme({"schema": 1, "fields": {"ink": "#000000"}, "tables": {}})

		restored = frappe.get_doc("Webstore Settings")
		self.assertEqual(restored.ink, "#000000")
		self.assertFalse(restored.accent)
		self.assertFalse(restored.wordmark)
		# an omitted flag returns to its DocType default, whatever that is
		self.assertEqual(restored.enable_wishlist, 1, "wishlist ships on")
		self.assertEqual(restored.enable_signup, 0, "signup ships off")

	def test_import_does_not_touch_general_settings(self):
		"""Replace semantics must stop at the theme fields."""
		from upande_webstore.theme.transfer import import_theme

		import_theme({"schema": 1, "fields": {}, "tables": {}})
		settings = frappe.get_doc("Webstore Settings")
		self.assertTrue(settings.company)
		self.assertEqual(settings.guest_price_list, "Standard Selling")
		self.assertEqual(settings.quotation_validity_days, 14)
		self.assertTrue(settings.warehouses)

	def test_reports_missing_images(self):
		from upande_webstore.theme.transfer import import_theme

		result = import_theme(
			{
				"schema": 1,
				"fields": {"brand_logo": "/files/definitely-not-here.png"},
				"tables": {},
			}
		)
		self.assertIn("/files/definitely-not-here.png", result["missing_images"])

	def test_shipped_asset_paths_are_not_reported_missing(self):
		"""/assets/... ships with the app; only /files/... lives in the DB."""
		from upande_webstore.theme.transfer import import_theme

		result = import_theme(
			{
				"schema": 1,
				"fields": {"hero_image": "/assets/upande_webstore/images/site/hero.jpg"},
				"tables": {},
			}
		)
		self.assertEqual(result["missing_images"], [])


class TestPresets(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_lists_shipped_presets(self):
		from upande_webstore.theme.transfer import list_presets

		names = list_presets()
		self.assertIn("mona_flowers", names)
		self.assertIn("upande", names)

	def test_preset_field_options_match_the_shipped_files(self):
		"""The dropdown must be selectable without any client script, and must
		never drift from the presets actually on disk — an empty options list is
		what made the preset unpickable in the desk."""
		from upande_webstore.theme.transfer import list_presets

		field = frappe.get_meta("Webstore Settings").get_field("preset")
		self.assertTrue(field.options, "preset field has no options — dropdown would be empty")
		offered = [o for o in (field.options or "").split("\n") if o]
		self.assertEqual(offered, list_presets())

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
		self.assertEqual(settings.accent_soft, "#e8f0fb")
		self.assertEqual(settings.ink_muted, "#878c9c")
		self.assertEqual(settings.accent_drives_primary, 1)
		self.assertEqual(settings.enable_signup, 0)
		self.assertEqual(settings.wordmark, "mona")
		self.assertEqual(settings.wordmark_bold, "flowers")
		self.assertEqual(len(settings.category_cards), 2)
		self.assertEqual(len(settings.hero_stats), 3)

	def test_mona_preset_produces_navy_tokens(self):
		from upande_webstore.services.settings import get_settings
		from upande_webstore.theme import tokens
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("mona_flowers")
		result = tokens.get_tokens(get_settings())
		self.assertEqual(result["accent"], "#1e4d8c")
		self.assertEqual(result["accent-deep"], "#143562")
		self.assertEqual(result["primary"], "var(--ws-accent)")
		self.assertEqual(result["ink-mute"], "#878c9c")
		self.assertEqual(result["bg"], "#f7f8fa")

	def test_upande_preset_keeps_ink_driving_primary(self):
		from upande_webstore.services.settings import get_settings
		from upande_webstore.theme import tokens
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("upande")
		settings = get_settings()
		self.assertEqual(settings.accent, "#d9a514")
		self.assertFalse(settings.accent_drives_primary)
		self.assertNotIn("primary", tokens.get_tokens(settings))

	def test_switching_presets_leaves_no_residue(self):
		"""mona -> upande must not leave navy-only fields behind."""
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("mona_flowers")
		apply_preset("upande")
		settings = frappe.get_doc("Webstore Settings")
		self.assertEqual(settings.accent, "#d9a514")
		# both presets ship signup off; accounts come from Webstore Portal Access
		self.assertEqual(settings.enable_signup, 0)
		self.assertEqual(len(settings.category_cards), 2)
		self.assertEqual([c.label for c in settings.category_cards][0], "Standard Roses")

	def test_unknown_preset_raises(self):
		from upande_webstore.theme.transfer import apply_preset

		with self.assertRaises(frappe.ValidationError):
			apply_preset("no_such_preset")

	def test_preset_name_cannot_traverse_paths(self):
		from upande_webstore.theme.transfer import apply_preset

		for evil in ("../../../etc/passwd", "..%2fupande", "a/b", "../upande", ".", ""):
			with self.assertRaises(frappe.ValidationError):
				apply_preset(evil)


class TestPresetRendersEndToEnd(IntegrationTestCase):
	"""Applying a preset must actually restyle the served page, not just the doc."""

	def setUp(self):
		setup_webstore_settings()

	def _render_store(self):
		from frappe.website.serve import get_response_content

		return get_response_content("/store")

	def _root_block(self, html):
		import re

		match = re.search(r":root \{(.*?)\n\t\}", html, re.S)
		return match.group(1) if match else ""

	def test_mona_preset_restyles_the_page(self):
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("mona_flowers")
		html = self._render_store()
		tokens_css = self._root_block(html)

		self.assertIn("--ws-accent: #1e4d8c;", tokens_css)
		self.assertIn("--ws-primary: var(--ws-accent);", tokens_css)
		self.assertIn("--ws-bg: #f7f8fa;", tokens_css)
		self.assertIn("--ws-ink-mute: #878c9c;", tokens_css)

		self.assertIn("mona<b>flowers</b>", html)
		self.assertIn("Eldoret", html)
		self.assertIn("Mona Flowers Kenya Limited", html)
		self.assertIn("Powered by Upande", html)
		self.assertEqual(html.count('class="ws-catcard"'), 2)
		self.assertEqual(html.count('class="ws-hero2-stat"'), 3)
		self.assertIn("Single-head, 40–120cm", html)
		self.assertIn("/store?category=Standard%20Roses", html)
		self.assertIn("/store?category=Spray%20Roses", html)
		# navy ink means navy-tinted shadows, not black ones
		self.assertIn("rgba(26, 26, 26,", tokens_css)
		self.assertIn("--ws-grad-ink: linear-gradient(135deg, var(--ws-accent-deep)", tokens_css)

	def test_mona_preset_hides_signup_for_guests(self):
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("mona_flowers")
		frappe.set_user("Guest")
		try:
			html = self._render_store()
			self.assertNotIn('href="/signup"', html)
			self.assertIn("Member login", html)
		finally:
			frappe.set_user("Administrator")

	def test_upande_preset_restores_ink_and_gold(self):
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("upande")
		html = self._render_store()
		tokens_css = self._root_block(html)

		self.assertIn("--ws-accent: #d9a514;", tokens_css)
		# ink still drives primary actions, so no remap is emitted
		self.assertNotIn("--ws-primary:", tokens_css)
		self.assertIn("upande<b>store</b>", html)
		# both presets are roses-only: Standard and Spray
		self.assertEqual(html.count('class="ws-catcard"'), 2)
		self.assertIn("Upande Ltd.", html)

	def test_clearing_seeds_removes_the_override_block_entirely(self):
		"""The blank-site guarantee, asserted through a real render."""
		from upande_webstore.theme.transfer import apply_preset

		apply_preset("mona_flowers")
		self.assertIn("--ws-accent", self._render_store())

		setup_webstore_settings()
		self.assertNotIn("--ws-", self._render_store())


class TestInstallSeeding(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_seeds_default_preset_on_blank_site(self):
		from upande_webstore.setup.install import seed_default_theme

		seed_default_theme()
		settings = frappe.get_doc("Webstore Settings")
		self.assertEqual(settings.accent, "#1e4d8c")
		self.assertEqual(settings.wordmark_bold, "flowers")

	def test_does_not_touch_a_configured_site(self):
		"""Deploying to an existing site must never restyle it."""
		from upande_webstore.setup.install import seed_default_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.accent = "#123456"
		settings.wordmark = "someone-else"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		seed_default_theme()

		settings = frappe.get_doc("Webstore Settings")
		self.assertEqual(settings.accent, "#123456")
		self.assertEqual(settings.wordmark, "someone-else")

	def test_does_not_touch_a_site_with_its_own_cards(self):
		from upande_webstore.setup.install import seed_default_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.append("category_cards", {"label": "Roses", "category": "Roses"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		seed_default_theme()

		cards = frappe.get_doc("Webstore Settings").category_cards
		self.assertEqual([card.label for card in cards], ["Roses"])

	def test_after_migrate_does_not_seed(self):
		from upande_webstore.setup.install import after_migrate

		after_migrate()
		self.assertFalse(frappe.db.get_single_value("Webstore Settings", "accent"))
