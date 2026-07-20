import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestCart(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CART-ITEM")
		make_item_price("WS-CART-ITEM", "Standard Selling", 50)
		make_test_product("WS-CART-OOS")
		make_item_price("WS-CART-OOS", "Standard Selling", 20)
		make_portal_user("cart.user@example.com")
		set_stock("WS-CART-ITEM", 10)
		set_stock("WS-CART-OOS", 0)

	def setUp(self):
		frappe.set_user("cart.user@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "cart.user@example.com"})

	def test_add_and_reprice(self):
		from upande_webstore.api import cart

		result = cart.add_item("WS-CART-ITEM", 2)
		self.assertEqual(result["count"], 2)
		self.assertEqual(result["items"][0]["rate"], 50)
		self.assertEqual(result["total"], 100)

	def test_single_open_cart(self):
		from upande_webstore.api import cart

		cart.add_item("WS-CART-ITEM", 1)
		cart.add_item("WS-CART-ITEM", 1)
		open_carts = frappe.get_all(
			"Webstore Cart", {"user": "cart.user@example.com", "status": "Open"}
		)
		self.assertEqual(len(open_carts), 1)
		self.assertEqual(cart.get_cart()["items"][0]["qty"], 2)

	def test_out_of_stock_rejected(self):
		from upande_webstore.api import cart

		self.assertRaises(frappe.ValidationError, cart.add_item, "WS-CART-OOS", 1)

	def test_qty_above_stock_rejected(self):
		from upande_webstore.api import cart

		self.assertRaises(frappe.ValidationError, cart.add_item, "WS-CART-ITEM", 11)

	def test_update_and_remove(self):
		from upande_webstore.api import cart

		cart.add_item("WS-CART-ITEM", 2)
		result = cart.update_qty("WS-CART-ITEM", 5)
		self.assertEqual(result["items"][0]["qty"], 5)
		result = cart.remove_item("WS-CART-ITEM")
		self.assertEqual(result["count"], 0)

	def test_guest_rejected(self):
		from upande_webstore.api import cart

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, cart.add_item, "WS-CART-ITEM", 1)
