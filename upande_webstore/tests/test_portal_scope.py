import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


def make_quotation_for(customer):
	quotation = frappe.get_doc({
		"doctype": "Quotation",
		"quotation_to": "Customer",
		"party_name": customer,
		"company": frappe.defaults.get_global_default("company"),
		"selling_price_list": "Standard Selling",
		"items": [{"item_code": "WS-SCOPE-ITEM", "qty": 1, "rate": 10}],
	})
	quotation.flags.ignore_permissions = True
	quotation.insert()
	quotation.submit()
	return quotation


class TestPortalScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-SCOPE-ITEM")
		make_item_price("WS-SCOPE-ITEM", "Standard Selling", 10)
		make_portal_user("scope.a@example.com", "Scope Customer A")
		make_portal_user("scope.b@example.com", "Scope Customer B")
		cls.quotation_a = make_quotation_for("Scope Customer A")
		cls.quotation_b = make_quotation_for("Scope Customer B")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_get_current_customer(self):
		from upande_webstore.services.portal import get_current_customer

		frappe.set_user("scope.a@example.com")
		self.assertEqual(get_current_customer(), "Scope Customer A")

	def test_guest_raises(self):
		from upande_webstore.services.portal import get_current_customer

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, get_current_customer)

	def test_docs_are_scoped_to_own_customer(self):
		from upande_webstore.services.portal import get_customer_docs

		frappe.set_user("scope.a@example.com")
		names = [q["name"] for q in get_customer_docs("Quotation", ["name"], "party_name", limit=100)]
		self.assertIn(self.quotation_a.name, names)
		self.assertNotIn(self.quotation_b.name, names)

	def test_assert_customer_doc_blocks_other_customer(self):
		from upande_webstore.services.portal import assert_customer_doc

		frappe.set_user("scope.a@example.com")
		doc = assert_customer_doc("Quotation", self.quotation_a.name, "party_name")
		self.assertEqual(doc.name, self.quotation_a.name)
		self.assertRaises(
			frappe.PermissionError,
			assert_customer_doc, "Quotation", self.quotation_b.name, "party_name",
		)

	def test_outstanding_balance_returns_number(self):
		from upande_webstore.services.portal import get_outstanding_balance

		frappe.set_user("scope.a@example.com")
		self.assertIsInstance(get_outstanding_balance(), float)
