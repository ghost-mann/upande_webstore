import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_test_product, setup_webstore_settings


class TestWebstoreProduct(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def test_route_generated_from_web_title(self):
		product = make_test_product("WS-TEST-WIDGET", web_title="Test Widget Pro")
		self.assertEqual(product.route, "store/test-widget-pro")

	def test_item_must_be_unique(self):
		make_test_product("WS-TEST-UNIQUE")
		duplicate = frappe.get_doc({
			"doctype": "Webstore Product",
			"item": "WS-TEST-UNIQUE",
			"web_title": "Duplicate",
			"published": 1,
		})
		self.assertRaises(frappe.UniqueValidationError, duplicate.insert)

	def test_unpublished_product_not_rendered(self):
		product = make_test_product("WS-TEST-HIDDEN", web_title="Hidden Item", published=0)
		from frappe.utils import get_html_for_route

		# unpublished docs get no route; probe the URL it would occupy
		route = product.route or "store/" + product.scrub(product.web_title)
		html = get_html_for_route(route)
		self.assertNotIn("Hidden Item price", html)
