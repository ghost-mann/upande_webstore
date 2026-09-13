"""services.settings.get_settings(): the resolved store's non-empty values
overlaid on the site Single.

This is the change that makes the whole multi-storefront feature tractable —
23 call sites read get_settings() and must keep working whether or not a
store is resolved. The acceptance test below is the literal bar from the
plan: with exactly one store present, get_settings() must return what it
always did.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.settings import get_settings
from upande_webstore.services.store import clear_store_cache
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import delete_all_webstores, setup_webstore_settings


class TestSettingsMergeScalars(IntegrationTestCase):
	def setUp(self):
		delete_all_webstores()
		self.settings = setup_webstore_settings()
		self.settings.checkout_mode = "Quotation only"
		self.settings.minimum_order_stems = 50
		self.settings.default_lead_days = 10
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()
		clear_store_cache()

	def tearDown(self):
		clear_store_cache()
		delete_all_webstores()

	def test_a_blank_store_field_inherits_the_singles_value(self):
		make_webstore("flowers")
		clear_store_cache()
		merged = get_settings()
		self.assertEqual(merged.checkout_mode, "Quotation only")
		self.assertEqual(int(merged.minimum_order_stems), 50)
		self.assertEqual(int(merged.default_lead_days), 10)

	def test_a_set_store_field_wins(self):
		make_webstore("flowers", checkout_mode="Sales order only", minimum_order_stems=200)
		clear_store_cache()
		merged = get_settings()
		self.assertEqual(merged.checkout_mode, "Sales order only")
		self.assertEqual(int(merged.minimum_order_stems), 200)
		# untouched field still inherits
		self.assertEqual(int(merged.default_lead_days), 10)

	def test_a_store_can_turn_box_packing_off_while_the_site_leaves_it_on(self):
		"""The reason enable_box_packing is a tri-state and not a Check: a dairy
		store on the same site as a flower store must be able to say "off"
		rather than only "inherit"."""
		self.settings.enable_box_packing = 1
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()
		make_webstore("dairy", enable_box_packing="Disabled")
		clear_store_cache()
		self.assertEqual(int(get_settings().enable_box_packing), 0)

	def test_blank_box_packing_inherits_the_site_setting(self):
		self.settings.enable_box_packing = 1
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()
		make_webstore("flowers")
		clear_store_cache()
		self.assertEqual(int(get_settings().enable_box_packing), 1)

	def test_a_store_can_turn_box_packing_on_while_the_site_leaves_it_off(self):
		self.settings.enable_box_packing = 0
		self.settings.save(ignore_permissions=True)
		frappe.clear_cache()
		make_webstore("flowers", enable_box_packing="Enabled")
		clear_store_cache()
		self.assertEqual(int(get_settings().enable_box_packing), 1)

	def test_no_resolved_store_returns_the_singles_untouched(self):
		"""No Webstore row at all: get_settings() must hand back the identical
		cached Single, not a copy of it."""
		clear_store_cache()
		self.assertFalse(frappe.get_all("Webstore", filters={"published": 1}))  # sanity
		merged = get_settings()
		self.assertIs(merged, frappe.get_cached_doc("Webstore Settings"))


class TestSettingsMergeTables(IntegrationTestCase):
	def setUp(self):
		delete_all_webstores()
		self.settings = setup_webstore_settings()
		self.warehouse = self.settings.warehouses[0].warehouse
		frappe.clear_cache()
		clear_store_cache()

	def tearDown(self):
		clear_store_cache()
		delete_all_webstores()

	def test_empty_store_table_inherits_the_singles_rows(self):
		make_webstore("flowers")
		clear_store_cache()
		merged = get_settings()
		self.assertEqual([row.warehouse for row in merged.warehouses], [self.warehouse])

	def test_non_empty_store_table_replaces_wholesale(self):
		make_webstore(
			"flowers",
			warehouses=[{"warehouse": self.warehouse}, {"warehouse": self.warehouse}],
		)
		clear_store_cache()
		merged = get_settings()
		# replaced wholesale with the store's own two rows, not merged with
		# the Single's one row (which would give three)
		self.assertEqual(len(merged.warehouses), 2)


class TestSettingsMergeAcceptance(IntegrationTestCase):
	"""The acceptance bar from the plan: with one store present, every field
	the storefront actually reads through get_settings() must come back
	exactly as it did before this feature existed."""

	def setUp(self):
		delete_all_webstores()
		self.settings = setup_webstore_settings()
		clear_store_cache()

	def tearDown(self):
		clear_store_cache()
		delete_all_webstores()

	def test_get_settings_is_unchanged_with_one_store_present(self):
		before = get_settings()
		before_values = {
			field: before.get(field)
			for field in (
				"guest_price_list",
				"checkout_mode",
				"enable_box_packing",
				"default_box_type",
				"minimum_order_stems",
				"default_lead_days",
				"company",
			)
		}
		before_warehouses = [row.warehouse for row in before.warehouses]
		before_categories = [row.item_group for row in before.categories]

		make_webstore("store")
		clear_store_cache()

		after = get_settings()
		for field, value in before_values.items():
			self.assertEqual(after.get(field), value, field)
		self.assertEqual([row.warehouse for row in after.warehouses], before_warehouses)
		self.assertEqual([row.item_group for row in after.categories], before_categories)
