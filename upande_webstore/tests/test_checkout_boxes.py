import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.test_cart_boxes import make_box_item
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestCheckoutBoxes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CB-ITEM")
		make_item_price("WS-CB-ITEM", "Standard Selling", 10)
		make_portal_user("cb.buyer@example.com", "CB Buyer")
		cls.zim = make_box_item("WS-CB-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "cb.buyer@example.com"})
		set_stock("WS-CB-ITEM", 20000)
		# column writes only — see the note in test_cart_boxes.setUp
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 1000)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_partial_group_is_blocked(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 1750)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		self.assertIn("1500", str(caught.exception))
		self.assertIn("1800", str(caught.exception))

	def test_below_minimum_is_blocked(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 600)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		self.assertIn("1000", str(caught.exception))

	def test_both_problems_reported_together(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 550)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		message = str(caught.exception)
		self.assertIn("whole boxes", message)
		self.assertIn("Minimum order", message)

	def test_whole_boxes_above_minimum_passes(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 1200)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])

	def test_inert_when_packing_disabled(self):
		from upande_webstore.api import cart, checkout

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")
		cart.add_item("WS-CB-ITEM", 1750)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])

	def test_inert_when_pack_rate_is_zero(self):
		"""Mona live's state today: seven box Items, every rate 0."""
		from upande_webstore.api import cart, checkout

		frappe.set_user("Administrator")
		unrated = make_box_item("WS-CB-NORATE", 0)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", unrated)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 0)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")
		cart.add_item("WS-CB-ITEM", 1750)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])
