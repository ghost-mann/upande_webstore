import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestCheckoutDates(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-DATE-ITEM")
		make_item_price("WS-DATE-ITEM", "Standard Selling", 10)
		make_portal_user("date.buyer@example.com", "Date Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "date.buyer@example.com"})
		set_stock("WS-DATE-ITEM", 500)
		# column writes only — see the note in test_cart_boxes.setUp
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.db.set_single_value("Webstore Settings", "default_lead_days", 3)
		frappe.clear_cache()
		frappe.set_user("date.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_past_date_rejected(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DATE-ITEM", 1)
		self.assertRaises(
			frappe.ValidationError,
			checkout.place_order,
			shipping_date=add_days(nowdate(), -1),
		)

	def test_date_inside_lead_window_rejected(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DATE-ITEM", 1)
		self.assertRaises(
			frappe.ValidationError,
			checkout.place_order,
			shipping_date=add_days(nowdate(), 1),
		)

	def test_date_on_the_lead_boundary_accepted(self):
		from upande_webstore.api import cart, checkout

		when = add_days(nowdate(), 3)
		cart.add_item("WS-DATE-ITEM", 1)
		result = checkout.place_order(mode="order", shipping_date=when)
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(str(order.delivery_date), when)
		self.assertEqual(str(order.items[0].delivery_date), when)

	def test_omitted_date_uses_configured_lead(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DATE-ITEM", 1)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(str(order.delivery_date), add_days(nowdate(), 3))

	def test_unset_setting_falls_back_to_default_constant(self):
		from upande_webstore.api import cart, checkout
		from upande_webstore.api.checkout import DEFAULT_DELIVERY_DAYS

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "default_lead_days", 0)
		frappe.clear_cache()
		frappe.set_user("date.buyer@example.com")
		cart.add_item("WS-DATE-ITEM", 1)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(
			str(order.delivery_date), add_days(nowdate(), DEFAULT_DELIVERY_DAYS)
		)
