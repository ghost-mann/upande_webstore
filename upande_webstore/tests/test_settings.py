import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestWebstoreSettings(IntegrationTestCase):
	def test_settings_roundtrip(self):
		settings = setup_webstore_settings()
		self.assertEqual(settings.quotation_validity_days, 14)
		from upande_webstore.services.settings import get_settings

		cached = get_settings()
		self.assertEqual(cached.guest_price_list, "Standard Selling")
		self.assertTrue(cached.warehouses)
