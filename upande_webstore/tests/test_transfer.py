import json

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import delete_all_webstores, setup_webstore_settings


class TestExportImport(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_export_has_schema_and_sections(self):
		from upande_webstore.theme.transfer import SCHEMA_VERSION, export_theme

		payload = export_theme()
		self.assertEqual(payload["schema"], SCHEMA_VERSION)
		self.assertIn("fields", payload)
		self.assertIn("tables", payload)
		for table in ("hero_stats", "category_cards", "process_steps", "footer_links"):
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
		"""A theme file from a newer version must not blow up an older site."""
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

	def test_import_theme_succeeds_with_no_company_or_guest_price_list(self):
		"""import_theme only ever touches Theme/Branding/Feature fields, so it
		must not be gated on mandatory fields it never writes."""
		from upande_webstore.theme.transfer import import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.flags.ignore_mandatory = True
		settings.company = ""
		settings.guest_price_list = ""
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		import_theme({"schema": 1, "fields": {"accent": "#1e4d8c"}, "tables": {}})

		restored = frappe.get_doc("Webstore Settings")
		self.assertEqual(restored.accent, "#1e4d8c")
		self.assertFalse(restored.company)
		self.assertFalse(restored.guest_price_list)

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


NAVY = {
	"schema": 1,
	"fields": {
		"accent": "#1e4d8c",
		"accent_dark": "#143562",
		"accent_soft": "#e8f0fb",
		"accent_drives_primary": 1,
		"ink": "#1a1a1a",
		"ink_muted": "#878c9c",
		"canvas": "#f7f8fa",
	},
	"tables": {},
}


class TestPalette(IntegrationTestCase):
	def setUp(self):
		# a site's own storefront rows carry their own overrides, which would
		# otherwise bleed into get_settings() and the rendered page
		from upande_webstore.services.store import clear_store_cache

		delete_all_webstores()
		setup_webstore_settings()
		clear_store_cache()
		frappe.local.webstore_merged_settings = None

	def test_process_steps_survive_a_round_trip(self):
		"""Editable ordering steps are theme content: an export must carry them and
		an import must restore them, or a copied theme silently reverts to shipped copy."""
		from upande_webstore.theme.transfer import export_theme, import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.append("process_steps", {"title": "Pick a box", "description": "By the box."})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		payload = export_theme()
		self.assertEqual(payload["tables"]["process_steps"][0]["title"], "Pick a box")

		setup_webstore_settings()
		self.assertFalse(frappe.get_doc("Webstore Settings").process_steps)

		import_theme(payload)
		steps = frappe.get_doc("Webstore Settings").process_steps
		self.assertEqual([step.title for step in steps], ["Pick a box"])

	def test_a_palette_produces_its_tokens(self):
		from upande_webstore.services.settings import get_settings
		from upande_webstore.theme import tokens
		from upande_webstore.theme.transfer import import_theme

		import_theme(NAVY)
		result = tokens.get_tokens(get_settings())
		self.assertEqual(result["accent"], "#1e4d8c")
		self.assertEqual(result["accent-deep"], "#143562")
		self.assertEqual(result["primary"], "var(--ws-accent)")
		self.assertEqual(result["ink-mute"], "#878c9c")
		self.assertEqual(result["bg"], "#f7f8fa")

	def test_ink_keeps_driving_primary_unless_asked(self):
		from upande_webstore.services.settings import get_settings
		from upande_webstore.theme import tokens
		from upande_webstore.theme.transfer import import_theme

		import_theme({"schema": 1, "fields": {"accent": "#d9a514"}, "tables": {}})
		settings = get_settings()
		self.assertFalse(settings.accent_drives_primary)
		self.assertNotIn("primary", tokens.get_tokens(settings))

	def test_importing_over_a_palette_leaves_no_residue(self):
		from upande_webstore.theme.transfer import import_theme

		import_theme(NAVY)
		import_theme({"schema": 1, "fields": {"accent": "#d9a514"}, "tables": {}})
		settings = frappe.get_doc("Webstore Settings")
		self.assertEqual(settings.accent, "#d9a514")
		self.assertFalse(settings.accent_dark)
		self.assertFalse(settings.canvas)


class TestPaletteRendersEndToEnd(IntegrationTestCase):
	"""A palette must actually restyle the served page, not just the doc."""

	def setUp(self):
		# a site's own storefront rows carry their own overrides, which would
		# otherwise bleed into get_settings() and the rendered page
		from upande_webstore.services.store import clear_store_cache

		delete_all_webstores()
		setup_webstore_settings()
		clear_store_cache()
		frappe.local.webstore_merged_settings = None

	def _render_store(self):
		from frappe.website.serve import get_response_content

		return get_response_content("/store")

	def _root_block(self, html):
		import re

		match = re.search(r":root \{(.*?)\n\t\}", html, re.S)
		return match.group(1) if match else ""

	def test_a_palette_restyles_the_page(self):
		from upande_webstore.theme.transfer import import_theme

		import_theme(NAVY)
		tokens_css = self._root_block(self._render_store())

		self.assertIn("--ws-accent: #1e4d8c;", tokens_css)
		self.assertIn("--ws-primary: var(--ws-accent);", tokens_css)
		self.assertIn("--ws-bg: #f7f8fa;", tokens_css)
		self.assertIn("--ws-ink-mute: #878c9c;", tokens_css)
		self.assertIn("rgba(26, 26, 26,", tokens_css)
		self.assertIn("--ws-grad-ink: linear-gradient(135deg, var(--ws-accent-deep)", tokens_css)

	def test_clearing_seeds_removes_the_override_block_entirely(self):
		"""The blank-site guarantee, asserted through a real render."""
		from upande_webstore.theme.transfer import import_theme

		import_theme(NAVY)
		self.assertIn("--ws-accent", self._render_store())

		setup_webstore_settings()
		frappe.local.webstore_merged_settings = None
		self.assertNotIn("--ws-", self._render_store())


class TestInstall(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_after_migrate_does_not_restyle(self):
		from upande_webstore.setup.install import after_migrate

		after_migrate()
		self.assertFalse(frappe.db.get_single_value("Webstore Settings", "accent"))

	def test_import_needs_no_company_or_guest_price_list(self):
		"""A fresh site has neither field set yet — both are reqd, but a theme
		write must not be blocked by mandatory fields it has nothing to do with."""
		from upande_webstore.theme.transfer import import_theme

		settings = frappe.get_doc("Webstore Settings")
		settings.flags.ignore_mandatory = True
		settings.company = ""
		settings.guest_price_list = ""
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		import_theme(NAVY)

		settings = frappe.get_doc("Webstore Settings")
		self.assertFalse(settings.company)
		self.assertEqual(settings.accent, "#1e4d8c")


class TestTransferPermissions(IntegrationTestCase):
	"""Every theme transfer endpoint used to hardcode frappe.only_for("System
	Manager"), which ignored Webstore Settings' own DocPerms entirely. These
	prove the checks now follow read/write on Webstore Settings instead."""

	def setUp(self):
		setup_webstore_settings()
		frappe.set_user("Administrator")

	def _read_only_user(self):
		from upande_webstore.tests.utils import make_desk_user

		frappe.permissions.add_permission("Webstore Settings", "Sales User", 0, "read")
		return make_desk_user("theme.reader@example.com", ["Sales User"])

	def _cleanup_read_only_user(self, email):
		frappe.set_user("Administrator")
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.permissions.reset_perms("Webstore Settings")

	def test_export_theme_refuses_a_user_without_read(self):
		from upande_webstore.theme.transfer import export_theme
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("theme.export.blocked@example.com", "Theme Blocked Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				export_theme()
		finally:
			frappe.set_user("Administrator")

	def test_import_theme_refuses_a_read_only_user(self):
		from upande_webstore.theme.transfer import SCHEMA_VERSION, import_theme

		email = self._read_only_user()
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				import_theme({"schema": SCHEMA_VERSION, "fields": {}, "tables": {}})
		finally:
			self._cleanup_read_only_user(email)
