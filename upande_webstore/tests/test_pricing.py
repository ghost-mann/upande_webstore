import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_price_list,
	make_test_product,
	setup_webstore_settings,
)


class TestPricing(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-PRICE-ITEM")
		make_item_price("WS-PRICE-ITEM", "Standard Selling", 100)
		make_price_list("Webstore B2B")
		make_item_price("WS-PRICE-ITEM", "Webstore B2B", 80)
		make_portal_user("b2b.buyer@example.com", "B2B Buyer Ltd", price_list="Webstore B2B")
		make_portal_user("retail.buyer@example.com", "Retail Buyer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_gets_guest_price_list(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="Guest")
		self.assertEqual(price["rate"], 100)
		self.assertEqual(price["price_list"], "Standard Selling")
		self.assertFalse(price["is_customer_price"])

	def test_customer_price_list_wins(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="b2b.buyer@example.com")
		self.assertEqual(price["rate"], 80)
		self.assertEqual(price["price_list"], "Webstore B2B")
		self.assertTrue(price["is_customer_price"])

	def test_customer_without_price_list_falls_back_to_guest(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="retail.buyer@example.com")
		self.assertEqual(price["rate"], 100)
		self.assertFalse(price["is_customer_price"])

	def test_get_customer_resolution(self):
		from upande_webstore.services.pricing import get_customer

		self.assertEqual(get_customer("b2b.buyer@example.com"), "B2B Buyer Ltd")
		self.assertIsNone(get_customer("Guest"))
