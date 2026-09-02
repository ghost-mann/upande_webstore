"""A portal customer must land in the portal on login, and must never be able
to pick up desk access while their portal access stays active.

Two halves, one file: the get_website_user_home_page hook (services/portal.py)
and the User.validate guard (services/provisioning.py) both exist to enforce
the same boundary from opposite ends - where a customer lands, and what roles
they can be given.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_desk_user, setup_webstore_settings

CUSTOMER = "Lockdown Customer Ltd"
EMAIL = "lockdown.customer@example.com"


def make_customer(name):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": "Individual",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)
	return name


class TestPortalLockdown(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_customer(CUSTOMER)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Portal Access", {"email": EMAIL})

	def tearDown(self):
		frappe.set_user("Administrator")

	def _grant(self, email=EMAIL, customer=CUSTOMER, full_name="Lockdown Customer"):
		doc = frappe.get_doc(
			{
				"doctype": "Webstore Portal Access",
				"customer": customer,
				"full_name": full_name,
				"email": email,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.grant()
		doc.reload()
		return doc

	def _cleanup_user(self, email):
		contact = frappe.db.get_value("Contact", {"user": email})
		if contact:
			frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.delete("Webstore Portal Access", {"email": email})

	# ---------------------------------------------------------------- home page

	def test_portal_customer_lands_on_dashboard_by_default(self):
		from upande_webstore.services.portal import get_website_user_home_page

		doc = self._grant()
		try:
			self.assertEqual(get_website_user_home_page(doc.user), "/portal")
		finally:
			self._cleanup_user(EMAIL)

	def test_portal_customer_lands_on_the_configured_landing_route(self):
		from upande_webstore.services.portal import get_website_user_home_page
		from upande_webstore.tests.utils import reset_portal_settings

		doc = self._grant()
		portal_settings = frappe.get_doc("Webstore Portal Settings")
		portal_settings.landing_page = "Orders"
		portal_settings.save(ignore_permissions=True)
		frappe.clear_cache()
		try:
			self.assertEqual(get_website_user_home_page(doc.user), "/portal/orders")
		finally:
			reset_portal_settings()
			self._cleanup_user(EMAIL)

	def test_system_manager_home_page_is_untouched(self):
		"""No active portal access -> None, so frappe's own resolution proceeds."""
		from upande_webstore.services.portal import get_website_user_home_page

		email = "lockdown.manager@example.com"
		make_desk_user(email, ["System Manager"])
		try:
			self.assertIsNone(get_website_user_home_page(email))
		finally:
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	def test_guest_and_administrator_are_never_redirected(self):
		from upande_webstore.services.portal import get_website_user_home_page

		self.assertIsNone(get_website_user_home_page("Guest"))
		self.assertIsNone(get_website_user_home_page("Administrator"))

	# ------------------------------------------------------------- desk guard

	def test_adding_a_desk_role_to_a_portal_customer_is_refused(self):
		doc = self._grant()
		try:
			user = frappe.get_doc("User", doc.user)
			user.append("roles", {"role": "Sales User"})
			with self.assertRaisesRegex(frappe.ValidationError, "Revoke their portal access"):
				user.save(ignore_permissions=True)
		finally:
			self._cleanup_user(EMAIL)

	def test_ensure_user_can_still_grant_the_customer_role(self):
		"""The guard must not break provisioning itself: Customer has no desk
		access, so ensure_user's own role grant must sail through untouched."""
		from upande_webstore.services.provisioning import ensure_user

		try:
			user = ensure_user(EMAIL, "Lockdown Customer")
			self.assertIn("Customer", [r.role for r in user.roles])
			self.assertEqual(user.user_type, "Website User")
		finally:
			self._cleanup_user(EMAIL)

	def test_revoking_access_then_granting_a_desk_role_succeeds(self):
		"""The documented escape hatch: revoke portal access first, then the
		desk role goes through and frappe promotes the user as normal."""
		doc = self._grant()
		try:
			doc.revoke()
			doc.reload()
			self.assertEqual(doc.status, "Revoked")

			user = frappe.get_doc("User", doc.user)
			user.append("roles", {"role": "Sales User"})
			user.save(ignore_permissions=True)
			user.reload()

			self.assertIn("Sales User", [r.role for r in user.roles])
			self.assertEqual(user.user_type, "System User")
		finally:
			self._cleanup_user(EMAIL)

	def test_existing_system_user_who_later_gains_portal_access_is_not_broken(self):
		"""A System Manager who is also a customer contact is a real case: the
		guard must fire only on a NEW desk-role grant, never on the mere
		coexistence of an existing System User and an active portal access
		record."""
		email = "lockdown.dual.role@example.com"
		make_desk_user(email, ["Sales Manager"])
		doc = frappe.get_doc(
			{
				"doctype": "Webstore Portal Access",
				"customer": CUSTOMER,
				"full_name": "Dual Role Person",
				"email": email,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		try:
			doc.grant()  # must not raise, even though this user already has desk access
			doc.reload()
			self.assertEqual(doc.status, "Active")

			user = frappe.get_doc("User", email)
			user.first_name = "Dual Role Person Renamed"
			user.save(ignore_permissions=True)  # no NEW desk role -> must not raise
			user.reload()

			self.assertEqual(user.first_name, "Dual Role Person Renamed")
			self.assertIn("Sales Manager", [r.role for r in user.roles])
		finally:
			frappe.delete_doc("Webstore Portal Access", doc.name, force=True, ignore_permissions=True)
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
