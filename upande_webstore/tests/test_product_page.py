import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_html_for_route

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	make_variant_template,
	set_stock,
	setup_webstore_settings,
)


class TestProductPage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		cls.simple = make_test_product("WS-PAGE-ITEM", web_title="Page Widget")
		make_item_price("WS-PAGE-ITEM", "Standard Selling", 42)
		set_stock("WS-PAGE-ITEM", 3)
		make_variant_template("WS-PAGE-TMPL")
		cls.template = make_test_product("WS-PAGE-TMPL", web_title="Page Template Product")
		cls.oos = make_test_product("WS-PAGE-OOS", web_title="Page OOS Widget")
		make_item_price("WS-PAGE-OOS", "Standard Selling", 9)
		set_stock("WS-PAGE-OOS", 0)

	def test_simple_product_shows_price_and_add_to_cart(self):
		html = get_html_for_route(self.simple.route)
		self.assertIn("Page Widget", html)
		self.assertIn("42", html)
		self.assertIn('data-webstore-add-to-cart="WS-PAGE-ITEM"', html)

	def test_template_product_shows_attribute_picker(self):
		html = get_html_for_route(self.template.route)
		self.assertIn("webstore-attribute", html)
		self.assertIn("WS Size", html)

	def test_out_of_stock_has_no_enabled_add_to_cart(self):
		html = get_html_for_route(self.oos.route)
		self.assertIn("Out of stock", html)
		self.assertNotIn('data-webstore-add-to-cart="WS-PAGE-OOS"', html)
