import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


def make_sales_invoice_for(customer):
	invoice = frappe.get_doc({
		"doctype": "Sales Invoice",
		"customer": customer,
		"company": frappe.defaults.get_global_default("company"),
		"selling_price_list": "Standard Selling",
		"items": [{"item_code": "WS-ORD-ITEM", "qty": 1, "rate": 10}],
	})
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	return invoice


class TestPortalOrders(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-ORD-ITEM", is_stock_item=0)
		make_item_price("WS-ORD-ITEM", "Standard Selling", 10)
		make_portal_user("ord.a@example.com", "Ord Customer A")
		make_portal_user("ord.b@example.com", "Ord Customer B")
		cls.invoice_a = make_sales_invoice_for("Ord Customer A")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_invoice_pdf_for_own_invoice(self):
		from upande_webstore.api.portal import download_invoice_pdf

		frappe.set_user("ord.a@example.com")
		download_invoice_pdf(self.invoice_a.name)
		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertTrue(frappe.local.response.filecontent[:4] == b"%PDF")

	def test_invoice_pdf_blocked_for_other_customer(self):
		from upande_webstore.api.portal import download_invoice_pdf

		frappe.set_user("ord.b@example.com")
		self.assertRaises(frappe.PermissionError, download_invoice_pdf, self.invoice_a.name)
