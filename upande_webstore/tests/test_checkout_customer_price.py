"""The Sales Order carries the rate the customer was shown.

Checkout builds the document as Administrator, who has no customer and so no
customer price list; rates are therefore resolved as the buyer beforehand.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_price_list,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)

BUYER = "custprice.buyer@example.com"


class TestCustomerPriceAtCheckout(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CP-ROSE")
		make_item_price("WS-CP-ROSE", "Standard Selling", 10)
		make_price_list("WS Negotiated List")
		make_item_price("WS-CP-ROSE", "WS Negotiated List", 6)
		make_portal_user(BUYER, "Negotiated Buyer", price_list="WS Negotiated List")

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": BUYER})
		set_stock("WS-CP-ROSE", 1000)
		frappe.set_user(BUYER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_quotation_and_order_carry_the_customers_own_rate(self):
		from upande_webstore.api import cart, checkout

		shown = cart.add_item("WS-CP-ROSE", 10)["items"][0]["rate"]
		self.assertEqual(shown, 6)
		name = checkout.place_order(mode="quotation")["quotation"]
		frappe.set_user("Administrator")
		self.assertEqual(frappe.get_doc("Quotation", name).items[0].rate, 6)

		frappe.set_user(BUYER)
		cart.add_item("WS-CP-ROSE", 10)
		name = checkout.place_order(mode="order")["sales_order"]
		frappe.set_user("Administrator")
		self.assertEqual(frappe.get_doc("Sales Order", name).items[0].rate, 6)


class TestForeignCurrencyCustomer(IntegrationTestCase):
	"""A customer priced in another currency than the company's is quoted in
	that currency, with ERPNext converting to the company's."""

	BUYER = "fxprice.buyer@example.com"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		company_currency = frappe.get_cached_value(
			"Company", frappe.defaults.get_global_default("company"), "default_currency"
		)
		cls.foreign = "EUR" if company_currency != "EUR" else "USD"
		frappe.db.set_value("Currency", cls.foreign, "enabled", 1)
		if not frappe.db.exists(
			"Currency Exchange", {"from_currency": cls.foreign, "to_currency": company_currency}
		):
			frappe.get_doc(
				{
					"doctype": "Currency Exchange",
					"date": "2026-01-01",
					"from_currency": cls.foreign,
					"to_currency": company_currency,
					"exchange_rate": 150,
					"for_selling": 1,
				}
			).insert(ignore_permissions=True)
		make_test_product("WS-FX-ROSE")
		make_price_list("WS FX List", currency=cls.foreign)
		make_item_price("WS-FX-ROSE", "WS FX List", 0.2)
		make_portal_user(cls.BUYER, "FX Buyer", price_list="WS FX List")

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": self.BUYER})
		set_stock("WS-FX-ROSE", 1000)
		frappe.set_user(self.BUYER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_document_is_in_the_price_lists_currency(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-FX-ROSE", 100)
		name = checkout.place_order(mode="quotation")["quotation"]
		frappe.set_user("Administrator")
		quotation = frappe.get_doc("Quotation", name)
		self.assertEqual(quotation.currency, self.foreign)
		self.assertAlmostEqual(quotation.items[0].rate, 0.2)
		self.assertGreater(quotation.conversion_rate, 1)
