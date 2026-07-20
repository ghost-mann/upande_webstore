import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	setup_webstore_settings,
)


class TestCatalog(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CAT-ALPHA", web_title="Alpha Sensor", featured=1)
		make_test_product("WS-CAT-BETA", web_title="Beta Gateway")
		make_test_product("WS-CAT-HIDDEN", web_title="Hidden Product", published=0)
		make_item_price("WS-CAT-ALPHA", "Standard Selling", 10)

	def test_only_published_products_listed(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Hidden Product", titles)

	def test_search(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(search="Alpha")
		self.assertEqual(len(result["products"]), 1)
		self.assertEqual(result["products"][0]["web_title"], "Alpha Sensor")
		self.assertEqual(result["products"][0]["price"]["rate"], 10)

	def test_featured_filter(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(featured_only=True, page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Beta Gateway", titles)

	def test_categories(self):
		from upande_webstore.services.catalog import get_categories

		categories = get_categories()
		self.assertTrue(any(c["name"] == "Products" and c["count"] >= 2 for c in categories))

	def test_store_page_renders(self):
		from frappe.utils import get_html_for_route

		html = get_html_for_route("store")
		self.assertIn("Alpha Sensor", html)
		self.assertNotIn("Hidden Product", html)
