import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_portal_user, setup_webstore_settings


class TestCartPage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("cartpage.user@example.com", "Cartpage Buyer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_addresses_helper(self):
		from upande_webstore.services.portal_data import get_customer_addresses

		address = frappe.get_doc({
			"doctype": "Address",
			"address_title": "Cartpage Buyer HQ",
			"address_type": "Shipping",
			"address_line1": "1 Test Lane",
			"city": "Nairobi",
			"country": "Kenya",
			"links": [{"link_doctype": "Customer", "link_name": "Cartpage Buyer"}],
		})
		address.insert(ignore_permissions=True)
		rows = get_customer_addresses("Cartpage Buyer")
		self.assertTrue(any(r["name"] == address.name for r in rows))

	def test_cart_page_requires_login(self):
		frappe.set_user("Guest")
		from upande_webstore.www.cart import get_context

		context = frappe._dict()
		self.assertRaises(frappe.Redirect, get_context, context)

	def test_signup_page_renders(self):
		from frappe.utils import get_html_for_route

		frappe.set_user("Guest")
		html = get_html_for_route("signup")
		self.assertIn("webstore-signup-form", html)
