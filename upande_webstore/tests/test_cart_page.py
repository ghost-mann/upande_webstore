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


class TestCartPageBoxes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from upande_webstore.tests.test_cart_boxes import make_box_item
		from upande_webstore.tests.utils import make_item_price, make_test_product

		setup_webstore_settings()
		make_test_product("WS-PAGE-BOX")
		make_item_price("WS-PAGE-BOX", "Standard Selling", 10)
		make_portal_user("page.box@example.com", "Page Box Buyer")
		cls.zim = make_box_item("WS-PAGE-ZIM", 300)

	def setUp(self):
		from upande_webstore.tests.utils import set_stock

		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "page.box@example.com"})
		set_stock("WS-PAGE-BOX", 5000)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 0)
		frappe.clear_cache()
		frappe.set_user("page.box@example.com")

	def test_context_carries_box_types_and_dropoff_mode(self):
		from upande_webstore.www.cart import get_context

		context = frappe._dict()
		get_context(context)
		self.assertIn(self.zim, [box["item_code"] for box in context.box_types])
		self.assertIn("delivery_points_available", context)

	def test_page_shows_box_select_and_the_block_reason(self):
		from frappe.utils import get_html_for_route

		from upande_webstore.api import cart

		cart.add_item("WS-PAGE-BOX", 1750)
		html = get_html_for_route("cart")
		self.assertIn('webstore-cart-box" data-item', html)
		self.assertIn("whole boxes", html)

	def test_box_column_absent_when_packing_off(self):
		from frappe.utils import get_html_for_route

		from upande_webstore.api import cart

		cart.add_item("WS-PAGE-BOX", 1750)
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("page.box@example.com")
		html = get_html_for_route("cart")
		# the class name still appears in the page's static JS; the column must not
		self.assertNotIn('webstore-cart-box" data-item', html)
		self.assertNotIn(">Box</th>", html)
