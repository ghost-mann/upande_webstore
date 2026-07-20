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


class TestCheckout(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CHK-ITEM")
		make_item_price("WS-CHK-ITEM", "Standard Selling", 75)
		make_portal_user("checkout.user@example.com", "Checkout Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "checkout.user@example.com"})
		set_stock("WS-CHK-ITEM", 10)
		frappe.set_user("checkout.user@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_place_order_creates_submitted_quotation(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHK-ITEM", 3)
		result = checkout.place_order(po_reference="PO-123", notes="Deliver Tuesday")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(quotation.docstatus, 1)
		self.assertEqual(quotation.party_name, "Checkout Buyer")
		self.assertEqual(quotation.items[0].item_code, "WS-CHK-ITEM")
		self.assertEqual(quotation.items[0].qty, 3)
		self.assertEqual(quotation.items[0].rate, 75)
		self.assertEqual(str(quotation.valid_till), add_days(nowdate(), 14))
		self.assertEqual(quotation.customer_po_reference, "PO-123")
		self.assertEqual(quotation.webstore_notes, "Deliver Tuesday")
		cart_doc = frappe.get_all(
			"Webstore Cart",
			{"user": "checkout.user@example.com"},
			["status", "quotation"],
		)[0]
		self.assertEqual(cart_doc.status, "Ordered")
		self.assertEqual(cart_doc.quotation, quotation.name)

	def test_empty_cart_rejected(self):
		from upande_webstore.api import checkout

		self.assertRaises(frappe.ValidationError, checkout.place_order)

	def test_stock_revalidated_at_checkout(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHK-ITEM", 3)
		frappe.set_user("Administrator")
		set_stock("WS-CHK-ITEM", 1)
		frappe.set_user("checkout.user@example.com")
		with self.assertRaises(frappe.ValidationError) as ctx:
			checkout.place_order()
		self.assertIn("no longer available", str(ctx.exception))
