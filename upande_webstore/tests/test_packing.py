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
