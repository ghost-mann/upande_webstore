import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from upande_webstore.tests.utils import (
	get_default_warehouse,
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)

ITEM = "WS-DASH-ITEM"


def make_quotation_for(customer):
	quotation = frappe.get_doc({
		"doctype": "Quotation",
		"quotation_to": "Customer",
		"party_name": customer,
		"company": frappe.defaults.get_global_default("company"),
		"selling_price_list": "Standard Selling",
		"items": [{"item_code": ITEM, "qty": 1, "rate": 10}],
	})
	quotation.flags.ignore_permissions = True
	quotation.insert()
	quotation.submit()
	return quotation


def make_sales_order_for(customer, qty=3, rate=50):
	order = frappe.get_doc({
		"doctype": "Sales Order",
		"customer": customer,
		"company": frappe.defaults.get_global_default("company"),
		"selling_price_list": "Standard Selling",
		"delivery_date": nowdate(),
		"items": [{"item_code": ITEM, "qty": qty, "rate": rate, "warehouse": get_default_warehouse()}],
	})
	order.flags.ignore_permissions = True
	order.insert()
	order.submit()
	return order


def make_sales_invoice_for(customer, rate=120):
	invoice = frappe.get_doc({
		"doctype": "Sales Invoice",
		"customer": customer,
		"company": frappe.defaults.get_global_default("company"),
		"selling_price_list": "Standard Selling",
		"items": [{"item_code": ITEM, "qty": 1, "rate": rate}],
	})
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	return invoice


class TestPortalDashboard(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product(ITEM)
		make_item_price(ITEM, "Standard Selling", 50)
		make_portal_user("dash.a@example.com", "Dash Customer A")
		make_portal_user("dash.b@example.com", "Dash Customer B")
		make_quotation_for("Dash Customer A")
		make_sales_order_for("Dash Customer A")
		make_sales_invoice_for("Dash Customer A")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_monthly_spend_scoped(self):
		from upande_webstore.services.portal_data import get_monthly_spend

		frappe.set_user("dash.a@example.com")
		series = get_monthly_spend()
		self.assertEqual(len(series), 12)
		self.assertEqual(sum(month["invoiced"] for month in series), 120.0)
		self.assertEqual(series[-1]["invoiced"], 120.0)

		frappe.set_user("dash.b@example.com")
		series = get_monthly_spend()
		self.assertEqual(sum(month["invoiced"] for month in series), 0.0)

	def test_spend_totals(self):
		from upande_webstore.services.portal_data import get_spend_totals

		frappe.set_user("dash.a@example.com")
		totals = get_spend_totals()
		self.assertEqual(totals["current"], 120.0)
		self.assertEqual(totals["previous"], 0.0)
		self.assertIsNone(totals["pct_change"])

	def test_quotation_mix_scoped(self):
		from upande_webstore.services.portal_data import get_quotation_mix

		frappe.set_user("dash.a@example.com")
		mix = get_quotation_mix()
		self.assertGreaterEqual(mix["Open"], 1)

		frappe.set_user("dash.b@example.com")
		mix = get_quotation_mix()
		self.assertEqual(sum(mix.values()), 0)

	def test_top_items_scoped_with_route(self):
		from upande_webstore.services.portal_data import get_top_items

		frappe.set_user("dash.a@example.com")
		top = get_top_items()
		self.assertTrue(top)
		self.assertEqual(top[0].item_code, ITEM)
		self.assertEqual(top[0].qty, 3)
		self.assertTrue(top[0].route)

		frappe.set_user("dash.b@example.com")
		self.assertEqual(get_top_items(), [])

	def test_sidebar_counts_scoped(self):
		from upande_webstore.services.portal_data import get_sidebar_counts

		frappe.set_user("dash.a@example.com")
		counts = get_sidebar_counts()
		self.assertGreaterEqual(counts["open_quotations"], 1)
		self.assertGreaterEqual(counts["unpaid_invoices"], 1)
		self.assertGreaterEqual(counts["orders_in_progress"], 1)

		frappe.set_user("dash.b@example.com")
		counts = get_sidebar_counts()
		self.assertEqual(counts["open_quotations"], 0)
		self.assertEqual(counts["unpaid_invoices"], 0)
		self.assertEqual(counts["orders_in_progress"], 0)
