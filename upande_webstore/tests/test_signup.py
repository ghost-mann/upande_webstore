import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestSignup(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _cleanup(self, email, customer_name):
		contact = frappe.db.get_value("Contact", {"user": email})
		if contact:
			frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)
		if frappe.db.exists("Customer", customer_name):
			frappe.delete_doc("Customer", customer_name, force=True, ignore_permissions=True)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	def test_individual_signup_creates_linked_records(self):
		from upande_webstore.api.account import sign_up

		self._cleanup("jane.doe@example.com", "Jane Doe")
		frappe.set_user("Guest")
		sign_up("jane.doe@example.com", "Jane Doe", "+254700000001")
		frappe.set_user("Administrator")

		user = frappe.get_doc("User", "jane.doe@example.com")
		self.assertEqual(user.user_type, "Website User")
		self.assertIn("Customer", [r.role for r in user.roles])

		customer = frappe.get_doc("Customer", "Jane Doe")
		self.assertEqual(customer.customer_type, "Individual")
		self.assertEqual(customer.customer_group, "Individual")

		contact_name = frappe.db.get_value("Contact", {"user": "jane.doe@example.com"})
		self.assertTrue(contact_name)
		link = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer"},
			"link_name",
		)
		self.assertEqual(link, "Jane Doe")

	def test_company_signup(self):
		from upande_webstore.api.account import sign_up

		self._cleanup("buyer@acme.example", "Acme Ltd")
		frappe.set_user("Guest")
		sign_up("buyer@acme.example", "Bob Buyer", "+254700000002", company_name="Acme Ltd")
		frappe.set_user("Administrator")
		customer = frappe.get_doc("Customer", "Acme Ltd")
		self.assertEqual(customer.customer_type, "Company")

	def test_duplicate_email_rejected(self):
		from upande_webstore.api.account import sign_up

		self._cleanup("dup@example.com", "Dup User")
		frappe.set_user("Guest")
		sign_up("dup@example.com", "Dup User", "+254700000003")
		self.assertRaises(frappe.ValidationError, sign_up, "dup@example.com", "Dup User", "+254700000003")
		frappe.set_user("Administrator")
