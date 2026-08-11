import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestPackingSettings(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def test_packing_fields_exist_with_inert_defaults(self):
		meta = frappe.get_meta("Webstore Settings")
		self.assertEqual(meta.get_field("enable_box_packing").default, "0")
		self.assertEqual(meta.get_field("minimum_order_stems").default, "0")
		self.assertEqual(meta.get_field("default_lead_days").default, "7")
		self.assertEqual(meta.get_field("default_box_type").options, "Item")

	def test_setup_helper_resets_packing_config(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_box_packing = 1
		settings.minimum_order_stems = 5000
		settings.save(ignore_permissions=True)
		setup_webstore_settings()
		settings = frappe.get_doc("Webstore Settings")
		self.assertFalse(int(settings.enable_box_packing or 0))
		self.assertEqual(int(settings.minimum_order_stems or 0), 0)
		self.assertEqual(int(settings.default_lead_days or 0), 7)


class TestBoxMaths(IntegrationTestCase):
	def test_exact_multiple_is_full(self):
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(1800, 300)
		self.assertEqual(result["boxes"], 6)
		self.assertEqual(result["remainder"], 0)
		self.assertTrue(result["is_full"])

	def test_remainder_reports_both_neighbours(self):
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(1750, 300)
		self.assertEqual(result["boxes"], 5)
		self.assertEqual(result["remainder"], 250)
		self.assertFalse(result["is_full"])
		self.assertEqual(result["nearest_down"], 1500)
		self.assertEqual(result["nearest_up"], 1800)

	def test_below_one_box_has_no_round_down(self):
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(50, 300)
		self.assertEqual(result["boxes"], 0)
		self.assertEqual(result["nearest_down"], 0)
		self.assertEqual(result["nearest_up"], 300)
		self.assertFalse(result["is_full"])

	def test_zero_pack_rate_never_blocks(self):
		"""Every pack rate on Mona live is 0. If that blocked, enabling the
		feature would take the storefront down."""
		from upande_webstore.services.packing import compute_boxes

		result = compute_boxes(1750, 0)
		self.assertTrue(result["is_full"])
		self.assertEqual(result["pack_rate"], 0)
		self.assertIsNone(result["nearest_up"])

	def test_zero_qty_is_full(self):
		from upande_webstore.services.packing import compute_boxes

		self.assertTrue(compute_boxes(0, 300)["is_full"])

	def test_grouping_sums_stems_across_lines(self):
		from upande_webstore.services.packing import group_by_box_type

		groups = group_by_box_type([
			{"item_code": "A", "qty": 50, "box_type": "ZIM"},
			{"item_code": "B", "qty": 250, "box_type": "ZIM"},
			{"item_code": "C", "qty": 500, "box_type": "JUMBO"},
		])
		self.assertEqual(groups["ZIM"]["stems"], 300)
		self.assertEqual(groups["JUMBO"]["stems"], 500)
		self.assertEqual(sorted(groups["ZIM"]["item_codes"]), ["A", "B"])
