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


class TestBoxFieldMapping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-MAP-A")
		make_test_product("WS-MAP-B")
		make_item_price("WS-MAP-A", "Standard Selling", 10)
		make_item_price("WS-MAP-B", "Standard Selling", 10)
		make_portal_user("map.buyer@example.com", "Map Buyer")
		cls.zim = make_box_item("WS-MAP-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "map.buyer@example.com"})
		set_stock("WS-MAP-A", 20000)
		set_stock("WS-MAP-B", 20000)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 0)
		frappe.clear_cache()
		frappe.set_user("map.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_quotation_item_carries_box_fields(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 600)
		result = checkout.place_order()
		row = frappe.get_doc("Quotation", result["quotation"]).items[0]
		self.assertEqual(row.custom_box_type, self.zim)
		self.assertEqual(int(row.custom_pack_rate), 300)
		self.assertEqual(row.custom_number_of_boxes, 2)

	def test_partial_line_records_zero_boxes(self):
		"""A line inside a mixed box has no whole-box count of its own."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 50)
		cart.add_item("WS-MAP-B", 250)
		result = checkout.place_order()
		rows = frappe.get_doc("Quotation", result["quotation"]).items
		self.assertEqual([r.custom_number_of_boxes for r in rows], [0, 0])

	def test_sales_order_flags_mixed_boxes(self):
		"""50 + 250 share one ZIM box, so the desk needs to know."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 50)
		cart.add_item("WS-MAP-B", 250)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes), 1)

	def test_single_line_is_not_mixed(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 300)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes or 0), 0)

	def test_two_whole_box_lines_are_not_mixed(self):
		"""600 and 600 at 300/box each pack alone; nothing shares."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 600)
		cart.add_item("WS-MAP-B", 600)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes or 0), 0)

	def test_box_type_posted_at_checkout_wins(self):
		from upande_webstore.api import cart, checkout
		from upande_webstore.tests.test_cart_boxes import make_box_item

		frappe.set_user("Administrator")
		jumbo = make_box_item("WS-MAP-JUMBO", 500)
		frappe.set_user("map.buyer@example.com")
		cart.add_item("WS-MAP-A", 1000)
		result = checkout.place_order(box_type=jumbo)
		row = frappe.get_doc("Quotation", result["quotation"]).items[0]
		self.assertEqual(row.custom_box_type, jumbo)
		self.assertEqual(int(row.custom_pack_rate), 500)
		self.assertEqual(row.custom_number_of_boxes, 2)
