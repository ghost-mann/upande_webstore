import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.test_portal_scope import make_quotation_for
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


class TestPortalQuotations(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-SCOPE-ITEM")
		make_item_price("WS-SCOPE-ITEM", "Standard Selling", 10)
		make_portal_user("pq.a@example.com", "PQ Customer A")
		make_portal_user("pq.b@example.com", "PQ Customer B")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_accept_sets_portal_status(self):
		quotation = make_quotation_for("PQ Customer A")
		from upande_webstore.api.portal import accept_quotation

		frappe.set_user("pq.a@example.com")
		result = accept_quotation(quotation.name)
		self.assertEqual(result["status"], "Accepted")
		self.assertEqual(
			frappe.db.get_value("Quotation", quotation.name, "webstore_portal_status"), "Accepted"
		)

	def test_decline_sets_portal_status(self):
		quotation = make_quotation_for("PQ Customer A")
		from upande_webstore.api.portal import decline_quotation

		frappe.set_user("pq.a@example.com")
		result = decline_quotation(quotation.name)
		self.assertEqual(result["status"], "Declined")

	def test_cannot_act_on_other_customers_quotation(self):
		quotation = make_quotation_for("PQ Customer B")
		from upande_webstore.api.portal import accept_quotation

		frappe.set_user("pq.a@example.com")
		self.assertRaises(frappe.PermissionError, accept_quotation, quotation.name)

	def test_cannot_accept_twice(self):
		quotation = make_quotation_for("PQ Customer A")
		from upande_webstore.api.portal import accept_quotation

		frappe.set_user("pq.a@example.com")
		accept_quotation(quotation.name)
		self.assertRaises(frappe.ValidationError, accept_quotation, quotation.name)
