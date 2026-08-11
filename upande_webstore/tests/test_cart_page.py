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

	def test_page_seeds_box_type_on_a_pre_existing_cart(self):
		"""A cart created before packing was switched on has no box type. The page
		has to seed it, or the checkout picker opens on nothing selected."""
		from upande_webstore.api.cart import _get_open_cart
		from upande_webstore.api import cart as cart_api
		from upande_webstore.www.cart import get_context

		cart_api.add_item("WS-PAGE-BOX", 600)
		doc = _get_open_cart()
		doc.db_set("box_type", None)
		context = frappe._dict()
		get_context(context)
		self.assertEqual(context.cart["items"][0]["box_type"], self.zim)
		self.assertEqual(context.cart["items"][0]["number_of_boxes"], 2)

	def test_context_carries_dropoff_mode(self):
		from upande_webstore.www.cart import get_context

		context = frappe._dict()
		get_context(context)
		self.assertIn("delivery_points_available", context)

	def test_basket_shows_the_box_and_the_block_reason(self):
		"""The box comes from the product, so the basket reports it rather than
		offering a choice."""
		from frappe.utils import get_html_for_route

		from upande_webstore.api import cart

		cart.add_item("WS-PAGE-BOX", 1750)
		html = get_html_for_route("cart")
		self.assertIn(">Box</th>", html)
		self.assertIn("whole boxes", html)
		# the buyer can change it, and the column has room for the control
		self.assertIn('webstore-cart-box" data-item', html)
		self.assertIn('width:240px', html)
		# qty is readable: its own width, and 1750 not 1750.0
		self.assertIn('width:130px', html)
		self.assertIn('value="1750"', html)
		self.assertNotIn('value="1750.0"', html)

	def test_box_column_absent_when_packing_off(self):
		from frappe.utils import get_html_for_route

		from upande_webstore.api import cart

		cart.add_item("WS-PAGE-BOX", 1750)
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("page.box@example.com")
		html = get_html_for_route("cart")
		self.assertNotIn(">Box</th>", html)
