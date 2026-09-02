import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings

EMAIL = "granted.buyer@example.com"
CUSTOMER = "Granted Access Ltd"


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


class TestPortalAccess(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_customer(CUSTOMER)

	def setUp(self):
		frappe.set_user("Administrator")
		for email in (EMAIL,):
			frappe.db.delete("Webstore Portal Access", {"email": email})

	def _record(self, email=EMAIL, customer=CUSTOMER, full_name="Granted Buyer"):
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
		return doc

	def test_starts_not_granted(self):
		self.assertEqual(self._record().status, "Not Granted")

	def test_grant_creates_a_website_user_with_the_customer_role(self):
		doc = self._record()
		doc.grant()
		doc.reload()

		self.assertEqual(doc.status, "Active")
		self.assertTrue(doc.user)
		user = frappe.get_doc("User", doc.user)
		self.assertEqual(user.user_type, "Website User")
		roles = [r.role for r in user.roles]
		self.assertIn("Customer", roles)
		self.assertNotIn("System Manager", roles)
		self.assertNotIn("Sales User", roles)

	def test_grant_links_the_contact_to_the_customer(self):
		"""This chain is what get_customer() resolves, so the portal and the
		store both depend on it."""
		from upande_webstore.services.pricing import get_customer

		doc = self._record()
		doc.grant()
		doc.reload()

		self.assertTrue(doc.contact)
		self.assertEqual(get_customer(doc.user), CUSTOMER)

	def test_granted_user_can_resolve_their_customer_for_ordering(self):
		doc = self._record()
		doc.grant()
		frappe.set_user(EMAIL)
		try:
			from upande_webstore.services.pricing import get_customer

			self.assertEqual(get_customer(), CUSTOMER)
		finally:
			frappe.set_user("Administrator")

	def test_grant_is_idempotent(self):
		doc = self._record()
		doc.grant()
		doc.grant()
		doc.reload()
		contacts = frappe.get_all("Contact", filters={"user": EMAIL})
		self.assertEqual(len(contacts), 1)
		contact = frappe.get_doc("Contact", doc.contact)
		customer_links = [
			l for l in contact.links if l.link_doctype == "Customer" and l.link_name == CUSTOMER
		]
		self.assertEqual(len(customer_links), 1, "customer link must not be duplicated")

	def test_works_for_a_customer_that_already_exists(self):
		"""The whole point: granting access to an existing customer, not creating
		a new one."""
		before = frappe.db.count("Customer")
		doc = self._record()
		doc.grant()
		self.assertEqual(frappe.db.count("Customer"), before)

	def test_revoke_disables_the_login_but_keeps_the_link(self):
		doc = self._record()
		doc.grant()
		doc.reload()
		doc.revoke()
		doc.reload()

		self.assertEqual(doc.status, "Revoked")
		self.assertFalse(frappe.db.get_value("User", doc.user, "enabled"))
		self.assertTrue(frappe.db.exists("Contact", doc.contact))

	def test_regrant_after_revoke_re_enables(self):
		doc = self._record()
		doc.grant()
		doc.revoke()
		doc.reload()
		doc.grant()
		doc.reload()
		self.assertEqual(doc.status, "Active")
		self.assertTrue(frappe.db.get_value("User", doc.user, "enabled"))

	def test_password_setup_link_is_usable_without_email(self):
		"""The welcome email needs a configured Email Account; this link is how a
		salesperson hands over access when there isn't one."""
		doc = self._record()
		doc.grant()
		doc.reload()

		result = doc.password_setup_link()
		self.assertIn("/update-password?key=", result["link"])
		self.assertTrue(frappe.db.get_value("User", doc.user, "reset_password_key"))

	def test_password_setup_link_requires_access_first(self):
		doc = self._record()
		with self.assertRaises(frappe.ValidationError):
			doc.password_setup_link()

	def test_new_password_link_replaces_the_previous_one(self):
		doc = self._record()
		doc.grant()
		doc.reload()
		first = doc.password_setup_link()["link"]
		key_after_first = frappe.db.get_value("User", doc.user, "reset_password_key")
		second = doc.password_setup_link()["link"]
		key_after_second = frappe.db.get_value("User", doc.user, "reset_password_key")

		self.assertNotEqual(first, second)
		self.assertNotEqual(key_after_first, key_after_second)

	def test_revoke_before_grant_is_rejected(self):
		doc = self._record()
		with self.assertRaises(frappe.ValidationError):
			doc.revoke()

	def test_unknown_customer_rejected(self):
		from upande_webstore.services.provisioning import grant_portal_access

		with self.assertRaises(frappe.ValidationError):
			grant_portal_access("No Such Customer Ltd", "Someone", "someone@example.com")

	def test_invalid_email_rejected(self):
		from upande_webstore.services.provisioning import grant_portal_access

		with self.assertRaises(Exception):
			grant_portal_access(CUSTOMER, "Someone", "not-an-email")

	def test_email_is_lowercased(self):
		doc = self._record(email="Mixed.Case@Example.com")
		self.assertEqual(doc.email, "mixed.case@example.com")
		frappe.db.delete("Webstore Portal Access", {"email": "mixed.case@example.com"})

	def test_grant_refuses_when_email_belongs_to_a_desk_user(self):
		"""Defect: granting portal access to an email that already belongs to a
		System User used to succeed silently, leaving a customer login that
		still reached the desk. It must now be refused outright, naming the
		email, and must not touch the existing account."""
		from upande_webstore.tests.utils import make_desk_user

		email = "granted.deskuser@example.com"
		make_desk_user(email, ["Sales User"])
		doc = self._record(email=email)
		try:
			with self.assertRaisesRegex(frappe.ValidationError, email):
				doc.grant()
			doc.reload()
			self.assertEqual(doc.status, "Not Granted")

			user = frappe.get_doc("User", email)
			self.assertEqual(user.user_type, "System User")
			self.assertIn("Sales User", [r.role for r in user.roles])
		finally:
			frappe.delete_doc("Webstore Portal Access", doc.name, force=True, ignore_permissions=True)
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	def test_grant_succeeds_for_an_email_that_is_already_a_website_user(self):
		"""The normal re-grant path, and must not regress: an email whose User
		already exists as a plain Website User (no desk access) is still
		grantable."""
		from upande_webstore.services.provisioning import ensure_user

		email = "granted.existing.website.user@example.com"
		ensure_user(email, "Existing Website User", send_welcome=False)
		doc = self._record(email=email)
		try:
			doc.grant()
			doc.reload()
			self.assertEqual(doc.status, "Active")

			user = frappe.get_doc("User", doc.user)
			self.assertEqual(user.user_type, "Website User")
			self.assertIn("Customer", [r.role for r in user.roles])
		finally:
			frappe.delete_doc("Webstore Portal Access", doc.name, force=True, ignore_permissions=True)
			contact = frappe.db.get_value("Contact", {"user": email})
			if contact:
				frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	def test_grant_refuses_a_user_without_write_on_portal_access(self):
		"""grant/revoke/password_setup_link used to hardcode a tuple of role
		names that only duplicated Webstore Portal Access's own DocPerms; this
		proves the replacement check still refuses someone without write."""
		from upande_webstore.tests.utils import make_portal_user

		doc = self._record()
		email, _customer = make_portal_user("portal.access.blocked@example.com", "Portal Blocked Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				doc.grant()
		finally:
			frappe.set_user("Administrator")

	def test_revoke_refuses_a_user_without_write_on_portal_access(self):
		from upande_webstore.tests.utils import make_portal_user

		doc = self._record()
		doc.grant()
		doc.reload()
		email, _customer = make_portal_user("portal.access.blocked2@example.com", "Portal Blocked2 Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				doc.revoke()
		finally:
			frappe.set_user("Administrator")

	def test_password_setup_link_refuses_a_user_without_write_on_portal_access(self):
		from upande_webstore.tests.utils import make_portal_user

		doc = self._record()
		doc.grant()
		doc.reload()
		email, _customer = make_portal_user("portal.access.blocked3@example.com", "Portal Blocked3 Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				doc.password_setup_link()
		finally:
			frappe.set_user("Administrator")
