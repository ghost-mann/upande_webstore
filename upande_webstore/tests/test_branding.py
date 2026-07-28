import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


def clear_tables():
	settings = frappe.get_doc("Webstore Settings")
	for table in ("hero_stats", "category_cards", "footer_links"):
		settings.set(table, [])
	settings.save(ignore_permissions=True)
	frappe.clear_cache()
	return settings


class TestBrandingDefaults(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()
		clear_tables()

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

	def test_every_default_key_has_a_real_field(self):
		"""A DEFAULTS entry with no DocType field could never be overridden."""
		from upande_webstore.theme.branding import DEFAULTS

		meta = frappe.get_meta("Webstore Settings")
		for key in DEFAULTS:
			self.assertTrue(meta.get_field(key), f"missing field {key}")

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

	def test_whitespace_only_value_falls_back(self):
		from upande_webstore.theme.branding import DEFAULTS, get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.wordmark = "   "
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(get_branding()["wordmark"], DEFAULTS["wordmark"])

	def test_logo_falls_back_to_shipped_asset(self):
		from upande_webstore.theme.branding import SHIPPED_LOGO, get_branding

		self.assertEqual(get_branding()["brand_logo"], SHIPPED_LOGO)

	def test_favicon_has_no_shipped_fallback(self):
		from upande_webstore.theme.branding import get_branding

		self.assertIsNone(get_branding()["favicon"])


class TestBrandingTables(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()
		clear_tables()

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

	def test_category_card_without_category_or_url_links_to_store(self):
		from upande_webstore.theme.branding import get_branding

		settings = frappe.get_doc("Webstore Settings")
		settings.append("category_cards", {"label": "Everything"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(get_branding()["category_cards"][0]["href"], "/store")

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
