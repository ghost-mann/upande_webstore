import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_portal_user, setup_webstore_settings


class TestAccount(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("acct.user@example.com", "Acct Customer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_update_profile(self):
		from upande_webstore.api.account import update_profile

		frappe.set_user("acct.user@example.com")
		update_profile("Updated Name", "+254711111111")
		self.assertEqual(
			frappe.db.get_value("User", "acct.user@example.com", "first_name"), "Updated Name"
		)

	def test_add_address_links_to_customer(self):
		from upande_webstore.api.account import add_address
		from upande_webstore.services.portal_data import get_customer_addresses

		frappe.set_user("acct.user@example.com")
		result = add_address("Acct HQ", "5 Portal Road", "Nairobi", "Kenya")
		rows = get_customer_addresses("Acct Customer")
		self.assertIn(result["name"], [r["name"] for r in rows])

	def test_guest_cannot_update_profile(self):
		from upande_webstore.api.account import update_profile

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, update_profile, "X", "1")

	def test_sign_up_refuses_a_desk_users_email(self):
		"""sign_up already refuses any pre-existing User before it does
		anything else, so a desk user's email is already refused cleanly -
		this pins that down as a Defect A requirement rather than an
		accident."""
		from upande_webstore.api.account import sign_up
		from upande_webstore.tests.utils import make_desk_user

		email = "acct.deskuser@example.com"
		make_desk_user(email, ["Sales User"])
		try:
			with self.assertRaises(frappe.ValidationError):
				sign_up(email, "Desk User Signing Up", "+254700000000")
		finally:
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
