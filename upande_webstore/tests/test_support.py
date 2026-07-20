import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_portal_user, setup_webstore_settings


class TestSupport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("sup.a@example.com", "Sup Customer A")
		make_portal_user("sup.b@example.com", "Sup Customer B")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_create_and_list_issue(self):
		from upande_webstore.api.support import create_issue, get_issues

		frappe.set_user("sup.a@example.com")
		result = create_issue("Broken sensor", "It stopped reporting data.")
		issue = frappe.get_doc("Issue", result["name"])
		self.assertEqual(issue.customer, "Sup Customer A")
		self.assertEqual(issue.raised_by, "sup.a@example.com")
		names = [i["name"] for i in get_issues()]
		self.assertIn(result["name"], names)

	def test_other_customer_cannot_see_issue(self):
		from upande_webstore.api.support import create_issue, get_issue_or_throw, get_issues

		frappe.set_user("sup.a@example.com")
		result = create_issue("Private issue", "Details")
		frappe.set_user("sup.b@example.com")
		names = [i["name"] for i in get_issues()]
		self.assertNotIn(result["name"], names)
		self.assertRaises(frappe.PermissionError, get_issue_or_throw, result["name"])

	def test_empty_subject_rejected(self):
		from upande_webstore.api.support import create_issue

		frappe.set_user("sup.a@example.com")
		self.assertRaises(frappe.ValidationError, create_issue, "", "no subject")
