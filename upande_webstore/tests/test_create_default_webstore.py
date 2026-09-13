"""patches.create_default_webstore: the migration that keeps a single-store
site's `/store` working with no manual step — see the module docstring."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.patches.create_default_webstore import execute
from upande_webstore.tests.utils import delete_all_webstores, setup_webstore_settings


class TestCreateDefaultWebstore(IntegrationTestCase):
	def setUp(self):
		self.settings = setup_webstore_settings()
		delete_all_webstores()

	def tearDown(self):
		delete_all_webstores()

	def test_creates_exactly_one_store_with_slug_store(self):
		execute()
		stores = frappe.get_all("Webstore", pluck="name")
		self.assertEqual(stores, ["store"])

	def test_is_idempotent_on_a_second_run(self):
		execute()
		execute()
		self.assertEqual(frappe.db.count("Webstore"), 1)

	def test_copies_the_scalar_fields(self):
		self.settings.checkout_mode = "Quotation only"
		self.settings.minimum_order_stems = 42
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()

		execute()

		store = frappe.get_doc("Webstore", "store")
		self.assertEqual(store.checkout_mode, "Quotation only")
		self.assertEqual(store.minimum_order_stems, 42)

	def test_leaves_default_lead_days_blank_so_it_keeps_inheriting(self):
		"""Webstore Settings ships default_lead_days at 7, not 0/blank, so
		copying "the current value" verbatim would freeze the migrated store
		there and silently stop a later edit to Webstore Settings from ever
		reaching checkout again. Left blank, it inherits indefinitely — not
		just at the moment of migration — which is what "behaves exactly as
		it does today" actually requires here."""
		self.settings.default_lead_days = 21
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()

		execute()

		store = frappe.get_doc("Webstore", "store")
		self.assertFalse(store.default_lead_days)

		# and a later edit to the site-wide setting must still take effect
		frappe.db.set_single_value("Webstore Settings", "default_lead_days", 5)
		frappe.clear_cache()
		from upande_webstore.services.settings import get_settings
		from upande_webstore.services.store import clear_store_cache

		clear_store_cache()
		self.assertEqual(int(get_settings().default_lead_days), 5)

	def test_copies_the_child_tables(self):
		warehouse = self.settings.warehouses[0].warehouse

		execute()

		store = frappe.get_doc("Webstore", "store")
		self.assertEqual([row.warehouse for row in store.warehouses], [warehouse])

	def test_title_falls_back_to_store_when_no_site_name_set(self):
		frappe.db.set_single_value("Webstore Settings", "site_name", "")
		frappe.clear_cache()

		execute()

		self.assertEqual(frappe.db.get_value("Webstore", "store", "title"), "Store")

	def test_title_uses_the_site_name_when_set(self):
		frappe.db.set_single_value("Webstore Settings", "site_name", "Mona Flowers")
		frappe.clear_cache()

		execute()

		self.assertEqual(frappe.db.get_value("Webstore", "store", "title"), "Mona Flowers")

	def test_does_nothing_when_a_store_already_exists(self):
		frappe.get_doc({"doctype": "Webstore", "slug": "flowers", "title": "Flowers"}).insert(
			ignore_permissions=True
		)
		execute()
		self.assertEqual(frappe.get_all("Webstore", pluck="name"), ["flowers"])
