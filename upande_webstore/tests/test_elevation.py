import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.elevation import as_administrator


class TestAsAdministrator(IntegrationTestCase):
	"""`frappe.set_user` overwrites session.sid with the user name, and the
	response writes session.sid into the `sid` cookie — so switching back with
	set_user alone logged the buyer out the moment checkout succeeded."""

	def setUp(self):
		self._session = frappe.local.session
		frappe.local.session = frappe._dict(
			user="Guest", sid="e2e-real-session-id", data=frappe._dict(csrf_token="tok")
		)
		frappe.set_user("Administrator")
		frappe.local.session.sid = "e2e-real-session-id"
		frappe.local.session.data = frappe._dict(csrf_token="tok")

	def tearDown(self):
		frappe.local.session = self._session
		frappe.set_user("Administrator")

	def test_runs_the_block_as_administrator_and_restores_the_session(self):
		frappe.local.session.user = "someone@example.com"
		with as_administrator():
			self.assertEqual(frappe.session.user, "Administrator")

		self.assertEqual(frappe.session.user, "someone@example.com")
		self.assertEqual(frappe.session.sid, "e2e-real-session-id", "the sid cookie would be overwritten")
		self.assertEqual(frappe.session.data.csrf_token, "tok", "the CSRF token would be lost")

	def test_restores_the_session_when_the_block_raises(self):
		frappe.local.session.user = "someone@example.com"
		with self.assertRaises(ValueError):
			with as_administrator():
				raise ValueError

		self.assertEqual(frappe.session.user, "someone@example.com")
		self.assertEqual(frappe.session.sid, "e2e-real-session-id")
