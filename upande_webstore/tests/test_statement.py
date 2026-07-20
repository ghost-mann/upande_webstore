import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.test_portal_orders import make_sales_invoice_for
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


class TestStatement(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-ORD-ITEM", is_stock_item=0)
		make_item_price("WS-ORD-ITEM", "Standard Selling", 10)
		make_portal_user("stmt.a@example.com", "Stmt Customer A")
		make_portal_user("stmt.b@example.com", "Stmt Customer B")
		cls.invoice = make_sales_invoice_for("Stmt Customer A")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_statement_includes_own_invoice(self):
		from upande_webstore.services.statement import get_statement

		frappe.set_user("stmt.a@example.com")
		result = get_statement(add_days(nowdate(), -30), nowdate())
		vouchers = [r["voucher_no"] for r in result["rows"]]
		self.assertIn(self.invoice.name, vouchers)
		self.assertEqual(
			result["closing"],
			result["opening"] + sum(r["debit"] - r["credit"] for r in result["rows"]),
		)

	def test_statement_excludes_other_customer(self):
		from upande_webstore.services.statement import get_statement

		frappe.set_user("stmt.b@example.com")
		result = get_statement(add_days(nowdate(), -30), nowdate())
		vouchers = [r["voucher_no"] for r in result["rows"]]
		self.assertNotIn(self.invoice.name, vouchers)
