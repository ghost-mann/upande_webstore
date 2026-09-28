"""Phase 2: an exported theme can dress one storefront.

Without this the transfer tools are site-wide only, so the only way to give
the dairy shop its own look is to set ~60 fields by hand — and importing the
flower theme would repaint both shops.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.settings import get_settings
from upande_webstore.services.store import clear_store_cache
from upande_webstore.theme import transfer
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import delete_all_webstores, setup_webstore_settings


class TransferCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		delete_all_webstores()
		self.settings = setup_webstore_settings()
		clear_store_cache()

	def tearDown(self):
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		frappe.local.webstore_merged_settings = None
		delete_all_webstores()
		frappe.clear_cache()

	def _as(self, slug):
		frappe.local.webstore_slug = slug
		clear_store_cache()
		frappe.local.webstore_merged_settings = None


ROSE = {"schema": transfer.SCHEMA_VERSION, "fields": {"accent": "#9b2242"}, "tables": {}}


class TestImportToOneStore(TransferCase):
	def test_an_import_dresses_only_the_store_it_names(self):
		make_webstore("flowers", title="Flowers")
		make_webstore("dairy", title="Dairy")

		transfer.import_theme(ROSE, webstore="flowers")

		self._as("flowers")
		dressed = get_settings().accent
		self._as("dairy")
		untouched = get_settings().accent

		self.assertEqual(dressed, "#9b2242")
		self.assertNotEqual(dressed, untouched)

	def test_the_site_wide_settings_are_untouched_by_a_store_import(self):
		make_webstore("flowers", title="Flowers")
		before = frappe.db.get_value("Webstore Settings", "Webstore Settings", "accent")

		transfer.import_theme(ROSE, webstore="flowers")

		self.assertEqual(
			frappe.db.get_value("Webstore Settings", "Webstore Settings", "accent"), before
		)

	def test_an_import_with_no_store_still_applies_site_wide(self):
		transfer.import_theme(ROSE)
		self.assertEqual(
			frappe.db.get_value("Webstore Settings", "Webstore Settings", "accent"), "#9b2242"
		)

	def test_an_unknown_slug_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			transfer.import_theme(ROSE, webstore="nope")

	def test_a_checkbox_in_the_payload_lands_as_a_tristate_on_the_store(self):
		"""Feature flags are Checks on the Single and three-state Selects on a
		store; a theme that switches one off has to say Disabled, not 0."""
		make_webstore("flowers", title="Flowers")
		transfer.import_theme(
			{"schema": transfer.SCHEMA_VERSION, "fields": {"enable_wishlist": 0}, "tables": {}},
			webstore="flowers",
		)
		self.assertEqual(frappe.db.get_value("Webstore", "flowers", "enable_wishlist"), "Disabled")

		self._as("flowers")
		self.assertEqual(int(get_settings().enable_wishlist), 0)

	def test_a_portal_flag_in_the_payload_is_ignored_on_a_store(self):
		"""The portal is shared, so a Webstore has no such field — a payload
		naming one must be skipped rather than crash the import."""
		make_webstore("flowers", title="Flowers")
		result = transfer.import_theme(
			{"schema": transfer.SCHEMA_VERSION, "fields": {"enable_invoices": 0}, "tables": {}},
			webstore="flowers",
		)
		self.assertNotIn("enable_invoices", result["applied_fields"])

	def test_a_field_absent_from_the_payload_returns_to_inheriting(self):
		"""On the Single, "reset" means the DocType default. On a store it
		means blank — which is how a store says "show the site's value"."""
		make_webstore("flowers", title="Flowers", hero_heading="Old heading")
		transfer.import_theme(
			{"schema": transfer.SCHEMA_VERSION, "fields": {"accent": "#123456"}, "tables": {}},
			webstore="flowers",
		)
		self.assertFalse(frappe.db.get_value("Webstore", "flowers", "hero_heading"))


class TestExportOneStore(TransferCase):
	def test_export_returns_the_look_a_visitor_actually_sees(self):
		"""Its own overrides on top of what it inherits — "copy this shop's
		appearance" means the appearance, not the half of it the shop states."""
		self.settings.hero_heading = "Inherited heading"
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()
		make_webstore("flowers", title="Flowers", accent="#FF0066")

		payload = transfer.export_theme(webstore="flowers")

		self.assertEqual(payload["fields"]["accent"], "#FF0066")
		self.assertEqual(payload["fields"]["hero_heading"], "Inherited heading")

	def test_exporting_a_store_does_not_disturb_the_current_request(self):
		make_webstore("flowers", title="Flowers", accent="#FF0066")
		make_webstore("dairy", title="Dairy", accent="#0066FF")

		self._as("dairy")
		transfer.export_theme(webstore="flowers")

		self.assertEqual(get_settings().accent, "#0066FF")

	def test_a_look_can_be_copied_from_one_store_to_another(self):
		make_webstore("flowers", title="Flowers", accent="#FF0066", site_name="Karen Roses")
		make_webstore("dairy", title="Dairy")

		transfer.import_theme(transfer.export_theme(webstore="flowers"), webstore="dairy")

		self._as("dairy")
		settings = get_settings()
		self.assertEqual(settings.accent, "#FF0066")
		self.assertEqual(settings.site_name, "Karen Roses")

	def test_export_with_no_store_is_the_site_wide_export(self):
		self.settings.accent = "#ABCDEF"
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(transfer.export_theme()["fields"]["accent"], "#ABCDEF")
