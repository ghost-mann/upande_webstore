"""frappe ships its own account page at /me (frappe/www/me.py) and it returns
200 for any logged-in website user - unbranded, outside the two surfaces this
app owns (storefront, portal). A portal customer landing there sees a
different-looking site, so a before_request hook sends them to the portal
instead - the same destination get_website_user_home_page already computes
for login, so the two can never disagree.

This app is responsible only for a user with active portal access; anyone
else (no portal access, or a System Manager) must reach /me exactly as they
do today, and the hook must not fire for any other path.
"""

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.exceptions import HTTPException
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from upande_webstore.tests.utils import (
	make_desk_user,
	make_portal_user,
	reset_portal_settings,
	setup_webstore_settings,
)

CUSTOMER = "Me Redirect Customer Ltd"
EMAIL = "me.redirect.customer@example.com"


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


class TestMeRedirect(IntegrationTestCase):
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
		frappe.local.request = None

	def _grant(self, email=EMAIL, customer=CUSTOMER, full_name="Me Redirect Customer"):
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

	def _request(self, path):
		"""Point frappe.local.request at `path`, the way a real inbound request
		would look to a before_request hook - see frappe's own
		TestReferrerValidation for the same construction."""
		builder = EnvironBuilder(path=path)
		frappe.local.request = Request(builder.get_environ())

	# -------------------------------------------------------------- redirect

	def test_portal_customer_requesting_me_is_redirected_to_the_portal(self):
		from upande_webstore.services.portal import redirect_me_to_portal

		doc = self._grant()
		try:
			frappe.set_user(doc.user)
			self._request("/me")
			with self.assertRaises(HTTPException) as ctx:
				redirect_me_to_portal()
			self.assertEqual(ctx.exception.get_response().location, "/portal")
		finally:
			self._cleanup_user(EMAIL)

	def test_redirect_honours_the_configured_landing_page(self):
		from upande_webstore.services.portal import redirect_me_to_portal

		doc = self._grant()
		portal_settings = frappe.get_doc("Webstore Portal Settings")
		portal_settings.landing_page = "Orders"
		portal_settings.save(ignore_permissions=True)
		frappe.clear_cache()
		try:
			frappe.set_user(doc.user)
			self._request("/me")
			with self.assertRaises(HTTPException) as ctx:
				redirect_me_to_portal()
			self.assertEqual(ctx.exception.get_response().location, "/portal/orders")
		finally:
			reset_portal_settings()
			self._cleanup_user(EMAIL)

	# ---------------------------------------------------------- not our user

	def test_user_without_portal_access_is_not_redirected(self):
		from upande_webstore.services.portal import redirect_me_to_portal

		email = "me.redirect.no-access@example.com"
		email, _ = make_portal_user(email, "Me Redirect No Access")
		try:
			frappe.set_user(email)
			self._request("/me")
			redirect_me_to_portal()  # must return normally - no HTTPException
		finally:
			self._cleanup_user(email)

	def test_system_manager_is_not_redirected(self):
		from upande_webstore.services.portal import redirect_me_to_portal

		email = "me.redirect.manager@example.com"
		make_desk_user(email, ["System Manager"])
		try:
			frappe.set_user(email)
			self._request("/me")
			redirect_me_to_portal()  # must return normally
		finally:
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	# ------------------------------------------------------------ too-eager

	def test_other_paths_are_unaffected_even_for_a_portal_customer(self):
		from upande_webstore.services.portal import redirect_me_to_portal

		doc = self._grant()
		try:
			frappe.set_user(doc.user)
			self._request("/portal")
			redirect_me_to_portal()  # must return normally - only /me is intercepted
		finally:
			self._cleanup_user(EMAIL)
