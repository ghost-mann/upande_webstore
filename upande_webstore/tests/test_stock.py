import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestStock(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-STOCK-ITEM")
		make_test_product("WS-NOSTOCK-ITEM")
		make_test_product("WS-SERVICE-ITEM", is_stock_item=0)

	def test_in_stock(self):
		from upande_webstore.services.stock import get_stock_info, get_stock_qty

		set_stock("WS-STOCK-ITEM", 5)
		self.assertEqual(get_stock_qty("WS-STOCK-ITEM"), 5)
		info = get_stock_info("WS-STOCK-ITEM")
		self.assertTrue(info["in_stock"])
		self.assertFalse(info["show_qty"])  # settings default is badge mode

	def test_out_of_stock(self):
		from upande_webstore.services.stock import get_stock_info

		set_stock("WS-NOSTOCK-ITEM", 0)
		self.assertFalse(get_stock_info("WS-NOSTOCK-ITEM")["in_stock"])

	def test_non_stock_item_always_available(self):
		from upande_webstore.services.stock import get_stock_info

		info = get_stock_info("WS-SERVICE-ITEM")
		self.assertTrue(info["in_stock"])
		self.assertIsNone(info["qty"])

	def test_exact_qty_mode(self):
		from upande_webstore.services.stock import get_stock_info

		settings = frappe.get_doc("Webstore Settings")
		settings.stock_display = "Exact Quantity"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		try:
			set_stock("WS-STOCK-ITEM", 5)
			info = get_stock_info("WS-STOCK-ITEM")
			self.assertTrue(info["show_qty"])
			self.assertEqual(info["qty"], 5)
		finally:
			settings.stock_display = "In/Out Badge"
			settings.save(ignore_permissions=True)
			frappe.clear_cache()
