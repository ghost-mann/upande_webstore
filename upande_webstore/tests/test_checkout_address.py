"""The delivery address a buyer picks at checkout must be one of their own
customer's addresses. The quotation is built as Administrator, so nothing
else stops a posted address name from being anyone's."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)

ITEM = "WS-CHKADDR-ITEM"
BUYER = "chkaddr.buyer@example.com"
OTHER = "chkaddr.other@example.com"


def make_address(customer, title):
	name = frappe.db.get_value("Address", {"address_title": title})
	if name:
		return name
	return frappe.get_doc({
		"doctype": "Address",
		"address_title": title,
		"address_type": "Shipping",
		"address_line1": f"{title} Road 1",
		"city": "Eldoret",
		"country": "Kenya",
		"links": [{"link_doctype": "Customer", "link_name": customer}],
	}).insert(ignore_permissions=True).name


class TestCheckoutDeliveryAddress(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product(ITEM)
		make_item_price(ITEM, "Standard Selling", 40)
		_, cls.buyer_customer = make_portal_user(BUYER, "Chkaddr Buyer Ltd")
		_, cls.other_customer = make_portal_user(OTHER, "Chkaddr Other Ltd")
		cls.own_address = make_address(cls.buyer_customer, "Chkaddr Buyer Farm Gate")
		cls.second_own_address = make_address(cls.buyer_customer, "Chkaddr Buyer Airport Store")
		cls.foreign_address = make_address(cls.other_customer, "Chkaddr Other Warehouse")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": BUYER})
		set_stock(ITEM, 100)
		frappe.set_user(BUYER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _order(self, address_name):
		from upande_webstore.api import cart, checkout

		cart.add_item(ITEM, 2)
		return checkout.place_order(address_name=address_name)

	def test_own_address_lands_on_the_quotation(self):
		result = self._order(self.second_own_address)
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(quotation.shipping_address_name, self.second_own_address)
		self.assertEqual(quotation.customer_address, self.second_own_address)
		self.assertIn("Chkaddr Buyer Airport Store Road 1", quotation.shipping_address or quotation.address_display or "")

	def test_another_customers_address_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._order(self.foreign_address)

	def test_unknown_address_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._order("No Such Address-Shipping")

	def test_no_address_is_still_allowed(self):
		result = self._order(None)
		self.assertTrue(result["quotation"])

	def test_cart_page_lists_only_the_buyers_addresses(self):
		from upande_webstore.services.portal_data import get_customer_addresses

		names = {a.name for a in get_customer_addresses(self.buyer_customer)}
		self.assertEqual(names, {self.own_address, self.second_own_address})
