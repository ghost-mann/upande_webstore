import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


class TestDropoff(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-DROP-ITEM")
		make_item_price("WS-DROP-ITEM", "Standard Selling", 10)
		make_portal_user("drop.buyer@example.com", "Drop Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "drop.buyer@example.com"})
		set_stock("WS-DROP-ITEM", 500)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("drop.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_absent_doctype_reports_unavailable(self):
		"""Mona live's state: three Link fields point at a Delivery Point doctype
		that does not exist."""
		from upande_webstore.services import dropoff

		if frappe.db.exists("DocType", "Delivery Point"):
			self.skipTest("site has Delivery Point installed")
		self.assertFalse(dropoff.delivery_points_available())
		self.assertEqual(dropoff.get_delivery_points(), [])

	def test_free_text_dropoff_still_stored(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-DROP-ITEM", 1)
		result = checkout.place_order(dropoff_points="Gate 3")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(quotation.webstore_dropoff_points, "Gate 3")

	def test_delivery_point_ignored_when_doctype_absent(self):
		"""Passing one must not raise — it is simply not stored."""
		from upande_webstore.api import cart, checkout

		if frappe.db.exists("DocType", "Delivery Point"):
			self.skipTest("site has Delivery Point installed")
		cart.add_item("WS-DROP-ITEM", 1)
		result = checkout.place_order(delivery_point="AIRFLO")
		self.assertTrue(result["quotation"])
