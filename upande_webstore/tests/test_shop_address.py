"""The shop address: customers on the gateway's address, staff on the ERP.

See docs/superpowers/specs/2026-10-18-shop-address-design.md.
"""

import contextlib

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from upande_webstore.tests.utils import make_desk_user, make_portal_user, setup_webstore_settings

SECRET = "test-gateway-secret-0123456789abcdefghij"
SHOP = "https://shop.example.com"


def set_shop(address=SHOP, enabled=0, secret=SECRET, **extra):
	"""Write the shop fields straight to the Single, past the interlock: tests
	of other behaviour must not depend on a reachability check."""
	values = {"shop_address": address or "", "send_customers_to_shop": enabled, **extra}
	for field, value in values.items():
		frappe.db.set_single_value("Webstore Settings", field, value)
	if secret is not None:
		from frappe.utils.password import set_encrypted_password

		set_encrypted_password("Webstore Settings", "Webstore Settings", secret, "gateway_secret")
	frappe.clear_document_cache("Webstore Settings", "Webstore Settings")


def clear_shop():
	set_shop(address="", enabled=0, secret=None, shop_extra_pages="", shop_extra_methods="")
	from frappe.utils.password import remove_encrypted_password

	remove_encrypted_password("Webstore Settings", "Webstore Settings", "gateway_secret")


@contextlib.contextmanager
def fake_request(path="/store", headers=None, method="GET", query_string=None):
	"""A real werkzeug Request on frappe.local, so frappe.get_request_header and
	the hooks see exactly what a live request would carry."""
	builder = EnvironBuilder(
		path=path, method=method, headers=headers or {}, query_string=query_string,
		base_url="https://erp.example.com",
	)
	previous = getattr(frappe.local, "request", None)
	frappe.local.request = Request(builder.get_environ())
	try:
		yield frappe.local.request
	finally:
		frappe.local.request = previous


def gateway_headers(secret=SECRET):
	return {"X-Webstore-Gateway": secret, "X-Forwarded-Host": "shop.example.com"}


class ShopTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def setUp(self):
		frappe.set_user("Administrator")
		clear_shop()

	def tearDown(self):
		frappe.set_user("Administrator")
		clear_shop()


class TestShopSettings(ShopTestCase):
	def test_blank_address_is_off(self):
		from upande_webstore.services import shop

		self.assertIsNone(shop.shop_address())
		self.assertFalse(shop.shop_enabled())

	def test_trailing_slash_normalised(self):
		doc = frappe.get_doc("Webstore Settings")
		doc.shop_address = "https://Shop.Example.com/"
		doc.save(ignore_permissions=True)
		from upande_webstore.services import shop

		self.assertEqual(shop.shop_address(), "https://shop.example.com")

	def test_address_with_path_refused(self):
		doc = frappe.get_doc("Webstore Settings")
		doc.shop_address = "https://shop.example.com/store"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_http_address_refused(self):
		doc = frappe.get_doc("Webstore Settings")
		doc.shop_address = "http://shop.example.com"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_local_http_allowed_only_in_developer_mode(self):
		"""A gateway running under `wrangler dev` is plain http on localhost."""
		from upande_webstore.services.shop import normalise_shop_address

		previous = frappe.conf.developer_mode
		try:
			frappe.conf.developer_mode = 1
			self.assertEqual(normalise_shop_address("http://127.0.0.1:8790/"), "http://127.0.0.1:8790")
			self.assertEqual(normalise_shop_address("http://localhost:8790"), "http://localhost:8790")
			with self.assertRaises(frappe.ValidationError):
				normalise_shop_address("http://shop.example.com")
			frappe.conf.developer_mode = 0
			with self.assertRaises(frappe.ValidationError):
				normalise_shop_address("http://127.0.0.1:8790")
		finally:
			frappe.conf.developer_mode = previous

	def test_shop_url_joins_path_and_query(self):
		set_shop()
		from upande_webstore.services import shop

		self.assertEqual(shop.shop_url("/store/athena?x=1"), "https://shop.example.com/store/athena?x=1")
		self.assertEqual(shop.shop_url("portal"), "https://shop.example.com/portal")


class TestShopRequestDetection(ShopTestCase):
	def test_secret_header_identifies_shop_request(self):
		set_shop()
		from upande_webstore.services import shop

		with fake_request(headers=gateway_headers()):
			self.assertTrue(shop.is_shop_request())
		with fake_request(headers=gateway_headers("wrong-secret")):
			self.assertFalse(shop.is_shop_request())
		with fake_request():
			self.assertFalse(shop.is_shop_request())

	def test_no_shop_request_without_an_address(self):
		set_shop(address="")
		from upande_webstore.services import shop

		with fake_request(headers=gateway_headers()):
			self.assertFalse(shop.is_shop_request())

	def test_no_shop_request_without_a_secret(self):
		clear_shop()
		set_shop(secret=None)
		from upande_webstore.services import shop

		with fake_request(headers={"X-Webstore-Gateway": ""}):
			self.assertFalse(shop.is_shop_request())


class TestAccountClassification(ShopTestCase):
	def test_staff_and_customer_classification(self):
		from upande_webstore.services import shop

		customer, _ = make_portal_user("shop.customer@example.com", "Shop Customer Ltd")
		staff = make_desk_user("shop.staff@example.com", ["Sales User", "Customer"])
		try:
			self.assertFalse(shop.is_staff(customer))
			self.assertTrue(shop.is_customer_account(customer))
			self.assertTrue(shop.is_staff(staff))
			self.assertFalse(shop.is_customer_account(staff))
			self.assertFalse(shop.is_customer_account("Administrator"))
			self.assertTrue(shop.is_staff("Administrator"))
		finally:
			frappe.delete_doc("User", staff, force=True, ignore_permissions=True)


class TestGatewayConfig(ShopTestCase):
	def test_config_refuses_without_secret(self):
		set_shop()
		from upande_webstore.api.gateway import config

		with fake_request(path="/api/method/upande_webstore.api.gateway.config"):
			with self.assertRaises(frappe.PageDoesNotExistError):
				config()
		with fake_request(headers=gateway_headers("nope")):
			with self.assertRaises(frappe.PageDoesNotExistError):
				config()

	def test_config_returns_settings_with_secret(self):
		set_shop(
			enabled=1,
			shop_login_attempts_per_minute=7,
			shop_allow_indexing=1,
			shop_extra_pages="/about\n\n /about/* \n",
			shop_extra_methods="frappe.www.contact.send_message\n",
		)
		from upande_webstore.api.gateway import config
		from upande_webstore.services.shop import CUSTOMER_METHODS

		with fake_request(headers=gateway_headers()):
			result = config()
		self.assertEqual(result["shop_address"], SHOP)
		self.assertTrue(result["send_customers_to_shop"])
		self.assertEqual(result["login_attempts_per_minute"], 7)
		self.assertTrue(result["allow_indexing"])
		self.assertEqual(result["extra_pages"], ["/about", "/about/*"])
		self.assertIn("frappe.www.contact.send_message", result["methods"])
		self.assertTrue(set(CUSTOMER_METHODS) <= set(result["methods"]))

	def test_config_default_login_limit(self):
		set_shop(shop_login_attempts_per_minute=0)
		from upande_webstore.api.gateway import config

		with fake_request(headers=gateway_headers()):
			self.assertEqual(config()["login_attempts_per_minute"], 10)

	def test_every_whitelisted_webstore_method_is_classified(self):
		import importlib
		import pkgutil

		import upande_webstore.api as api_pkg
		from upande_webstore.services.shop import CUSTOMER_METHODS, DESK_ONLY_METHODS, GATEWAY_METHODS

		found = set()
		for info in pkgutil.iter_modules(api_pkg.__path__):
			module = importlib.import_module(f"upande_webstore.api.{info.name}")
			for name in dir(module):
				fn = getattr(module, name)
				if callable(fn) and fn in frappe.whitelisted and getattr(fn, "__module__", "") == module.__name__:
					found.add(f"{module.__name__}.{name}")
		self.assertTrue(found)
		webstore_customer = {m for m in CUSTOMER_METHODS if m.startswith("upande_webstore.")}
		classified = webstore_customer | set(DESK_ONLY_METHODS) | set(GATEWAY_METHODS)
		self.assertEqual(sorted(found - classified), [], "new whitelisted methods must be classified")
		self.assertEqual(sorted(classified - found), [], "classified methods that no longer exist")
		self.assertFalse(webstore_customer & set(DESK_ONLY_METHODS))


def run_before_request():
	"""The hook, returning the redirect location if it raised one."""
	from werkzeug.exceptions import HTTPException

	from upande_webstore.services import shop

	try:
		shop.before_request()
	except HTTPException as e:
		return e.get_response().location
	return None


class FakeLoginManager:
	def __init__(self, user):
		self.user = user


class TestErpSendsCustomersToTheShop(ShopTestCase):
	def test_customer_path_redirects_when_on(self):
		set_shop(enabled=1)
		for path, query in (
			("/store", None),
			("/store/athena", "length=40cm"),
			("/cart", None),
			("/wishlist", None),
			("/portal/orders", None),
			("/signup", None),
			("/wholesale/store/rose", None),
			("/wholesale/cart", None),
		):
			with fake_request(path=path, query_string=query):
				expected = SHOP + path + (f"?{query}" if query else "")
				self.assertEqual(run_before_request(), expected, path)

	def test_no_redirect_when_off(self):
		set_shop(enabled=0)
		with fake_request(path="/store"):
			self.assertIsNone(run_before_request())

	def test_no_redirect_for_shop_request(self):
		set_shop(enabled=1)
		with fake_request(path="/store", headers=gateway_headers()):
			self.assertIsNone(run_before_request())

	def test_desk_and_login_paths_never_redirect(self):
		set_shop(enabled=1)
		for path in ("/desk", "/app/quotation", "/login", "/update-password", "/", "/api/method/ping", "/storefront-blog"):
			with fake_request(path=path):
				self.assertIsNone(run_before_request(), path)

	def test_logged_in_customer_on_the_erp_is_sent_to_the_shop(self):
		set_shop(enabled=1)
		customer, _ = make_portal_user("shop.erpvisit@example.com", "Shop Erpvisit Ltd")
		frappe.set_user(customer)
		with fake_request(path="/api/method/frappe.auth.get_logged_user"):
			self.assertEqual(run_before_request(), SHOP + "/login")


class TestShopRequestLinks(ShopTestCase):
	def test_get_url_is_shop_address_during_shop_request(self):
		set_shop()
		with fake_request(path="/store", headers=gateway_headers()):
			run_before_request()
			self.assertEqual(frappe.utils.get_url("/update-password?key=x"), SHOP + "/update-password?key=x")

	def test_shared_conf_is_never_mutated(self):
		"""frappe.local.conf is the worker's cached site config; writing the
		shop host into it would leak into every later ERP request."""
		set_shop()
		original = frappe.local.conf
		host_before = original.get("host_name")
		try:
			with fake_request(path="/store", headers=gateway_headers()):
				run_before_request()
				self.assertIsNot(frappe.local.conf, original)
			self.assertEqual(original.get("host_name"), host_before)
		finally:
			frappe.local.conf = original


class TestLoginRules(ShopTestCase):
	def _login(self, user, headers=None):
		from upande_webstore.services import shop

		with fake_request(path="/api/method/login", method="POST", headers=headers):
			shop.on_login(FakeLoginManager(user))

	def test_staff_login_refused_on_shop(self):
		set_shop(enabled=1)
		staff = make_desk_user("shop.staff2@example.com", ["Sales User"])
		try:
			with self.assertRaises(frappe.AuthenticationError) as ctx:
				self._login(staff, gateway_headers())
			self.assertIn("Staff accounts sign in on the ERP.", str(ctx.exception))
			self.assertNotIn("erp.example.com", str(ctx.exception))
		finally:
			frappe.delete_doc("User", staff, force=True, ignore_permissions=True)

	def test_staff_linked_to_customer_refused_on_shop(self):
		set_shop(enabled=1)
		staff = make_desk_user("shop.staffcust@example.com", ["Sales User", "Customer"])
		try:
			with self.assertRaises(frappe.AuthenticationError):
				self._login(staff, gateway_headers())
		finally:
			frappe.delete_doc("User", staff, force=True, ignore_permissions=True)

	def test_secret_with_switch_off_still_refuses_staff(self):
		set_shop(enabled=0)
		with self.assertRaises(frappe.AuthenticationError):
			self._login("Administrator", gateway_headers())

	def test_customer_login_on_shop_allowed(self):
		set_shop(enabled=1)
		customer, _ = make_portal_user("shop.login@example.com", "Shop Login Ltd")
		self._login(customer, gateway_headers())

	def test_customer_login_refused_on_erp_when_on(self):
		set_shop(enabled=1)
		customer, _ = make_portal_user("shop.login@example.com", "Shop Login Ltd")
		with self.assertRaises(frappe.AuthenticationError) as ctx:
			self._login(customer)
		self.assertIn("Please sign in on the shop.", str(ctx.exception))

	def test_customer_login_allowed_on_erp_when_off(self):
		set_shop(enabled=0)
		customer, _ = make_portal_user("shop.login@example.com", "Shop Login Ltd")
		self._login(customer)

	def test_staff_login_on_erp_allowed(self):
		set_shop(enabled=1)
		self._login("Administrator")


class TestCustomerEmailsUseTheShop(ShopTestCase):
	EMAIL = "shop.granted@example.com"
	CUSTOMER = "Shop Granted Ltd"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from upande_webstore.tests.test_portal_access import make_customer

		make_customer(cls.CUSTOMER)

	def setUp(self):
		super().setUp()
		frappe.db.delete("Webstore Portal Access", {"email": self.EMAIL})
		if frappe.db.exists("User", self.EMAIL):
			frappe.delete_doc("User", self.EMAIL, force=True, ignore_permissions=True)

	def _granted(self):
		doc = frappe.get_doc({
			"doctype": "Webstore Portal Access",
			"customer": self.CUSTOMER,
			"full_name": "Shop Granted",
			"email": self.EMAIL,
		}).insert(ignore_permissions=True)
		doc.grant()
		doc.reload()
		return doc

	def test_password_setup_link_uses_shop_address(self):
		set_shop(enabled=1)
		doc = self._granted()
		link = doc.password_setup_link()["link"]
		self.assertTrue(link.startswith(SHOP + "/update-password?key="), link)

	def test_password_setup_link_unchanged_when_off(self):
		set_shop(enabled=0)
		doc = self._granted()
		link = doc.password_setup_link()["link"]
		self.assertFalse(link.startswith(SHOP), link)

	def test_welcome_email_link_uses_shop_address(self):
		"""The link is captured where frappe hands it to the mailer, so the test
		does not depend on this site having a working outgoing Email Account."""
		from unittest.mock import patch

		from frappe.core.doctype.user.user import User

		from upande_webstore.services.provisioning import ensure_user

		set_shop(enabled=1)
		sent = {}

		def capture(self, subject, template, add_args, now=None, custom_template=None):
			sent["link"] = add_args.get("link")

		with patch.object(User, "send_login_mail", capture):
			ensure_user(self.EMAIL, "Shop Granted", send_welcome=True)
		self.assertTrue((sent.get("link") or "").startswith(SHOP + "/update-password?key="), sent)

	def test_conf_restored_after_as_shop(self):
		set_shop(enabled=1)
		from upande_webstore.services.shop import as_shop

		before = frappe.local.conf
		with as_shop():
			self.assertEqual(frappe.utils.get_url("/x"), SHOP + "/x")
		self.assertIs(frappe.local.conf, before)


SHOP_OK_HEADERS = {"X-Webstore-Gateway-Version": "2", "X-Webstore-Shop-Request": "1"}


class FakeResponse:
	def __init__(self, status=200, headers=None):
		self.status_code = status
		self.headers = headers or {}


class TestReachabilityAndInterlock(ShopTestCase):
	def _check(self, response):
		from unittest.mock import patch

		from upande_webstore.services import shop

		with patch("upande_webstore.services.shop.requests.get", return_value=response) as get:
			result = shop.check_shop_address()
		return result, get

	def test_check_succeeds_with_marker_header(self):
		set_shop()
		result, get = self._check(FakeResponse(200, SHOP_OK_HEADERS))
		self.assertTrue(result["ok"])
		self.assertEqual(get.call_args.args[0], SHOP + "/store")
		self.assertTrue(frappe.db.get_single_value("Webstore Settings", "shop_last_check_ok"))

	def test_check_fails_without_marker_header(self):
		set_shop()
		result, _ = self._check(FakeResponse(200, {}))
		self.assertFalse(result["ok"])
		self.assertIn("gateway", result["message"].lower())
		# raw: get_single_value casts a missing Datetime to 0001-01-01
		raw = frappe.db.sql(
			"select value from tabSingles where doctype=%s and field=%s", ("Webstore Settings", "shop_last_check_ok")
		)
		self.assertFalse(raw)
		self.assertFalse(frappe.get_doc("Webstore Settings").shop_last_check_ok)

	def test_check_fails_when_the_erp_did_not_recognise_the_gateway(self):
		"""The gateway answers, but with a missing or wrong secret: turning the
		switch on now would send every customer into a redirect loop."""
		set_shop()
		result, _ = self._check(FakeResponse(200, {"X-Webstore-Gateway-Version": "2"}))
		self.assertFalse(result["ok"])
		self.assertIn("secret", result["message"].lower())

	def test_after_request_marks_shop_requests_only(self):
		from werkzeug.wrappers import Response

		from upande_webstore.services import shop

		set_shop()
		with fake_request(path="/store", headers=gateway_headers()) as request:
			response = Response()
			shop.after_request(response=response, request=request)
			self.assertEqual(response.headers.get("X-Webstore-Shop-Request"), "1")
		with fake_request(path="/store") as request:
			response = Response()
			shop.after_request(response=response, request=request)
			self.assertIsNone(response.headers.get("X-Webstore-Shop-Request"))

	def test_new_secret_refused_while_customers_are_sent_to_the_shop(self):
		from upande_webstore.api.gateway import generate_gateway_secret

		set_shop(enabled=1)
		with self.assertRaises(frappe.ValidationError):
			generate_gateway_secret()

	def test_check_fails_on_connection_error(self):
		from unittest.mock import patch

		import requests

		from upande_webstore.services import shop

		set_shop()
		with patch("upande_webstore.services.shop.requests.get", side_effect=requests.ConnectionError("boom")):
			result = shop.check_shop_address()
		self.assertFalse(result["ok"])

	def test_switch_refused_without_recent_check(self):
		set_shop(enabled=0, shop_last_check_ok=None)
		doc = frappe.get_doc("Webstore Settings")
		doc.send_customers_to_shop = 1
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_switch_refused_with_stale_check(self):
		set_shop(enabled=0, shop_last_check_ok=frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-11))
		doc = frappe.get_doc("Webstore Settings")
		doc.send_customers_to_shop = 1
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_switch_allowed_after_recent_check(self):
		set_shop(enabled=0)
		self._check(FakeResponse(200, SHOP_OK_HEADERS))
		doc = frappe.get_doc("Webstore Settings")
		doc.send_customers_to_shop = 1
		doc.save(ignore_permissions=True)
		self.assertTrue(frappe.db.get_single_value("Webstore Settings", "send_customers_to_shop"))

	def test_address_change_refused_while_switch_is_on(self):
		set_shop(enabled=1)
		doc = frappe.get_doc("Webstore Settings")
		doc.shop_address = "https://other-shop.example.com"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		# switching off in the same save is the way to change it
		doc = frappe.get_doc("Webstore Settings")
		doc.shop_address = "https://other-shop.example.com"
		doc.send_customers_to_shop = 0
		doc.save(ignore_permissions=True)

	def test_resaving_with_switch_on_needs_no_new_check(self):
		set_shop(enabled=1, shop_last_check_ok=None)
		doc = frappe.get_doc("Webstore Settings")
		doc.save(ignore_permissions=True)

	def test_daily_watch_emails_when_unreachable_and_leaves_switch_on(self):
		from unittest.mock import patch

		from upande_webstore.services import shop

		set_shop(enabled=1)
		with patch("upande_webstore.services.shop.requests.get", return_value=FakeResponse(502)), patch(
			"upande_webstore.services.shop.frappe.sendmail"
		) as sendmail:
			shop.daily_watch()
		self.assertTrue(sendmail.called)
		self.assertTrue(frappe.db.get_single_value("Webstore Settings", "send_customers_to_shop"))

	def test_daily_watch_quiet_when_off(self):
		from unittest.mock import patch

		from upande_webstore.services import shop

		set_shop(enabled=0)
		with patch("upande_webstore.services.shop.requests.get") as get:
			shop.daily_watch()
		self.assertFalse(get.called)

	def test_generate_secret_is_long_and_random(self):
		import re

		from upande_webstore.api.gateway import generate_gateway_secret
		from upande_webstore.services.shop import gateway_secret

		set_shop(secret=None)
		first = generate_gateway_secret()["secret"]
		second = generate_gateway_secret()["secret"]
		self.assertGreaterEqual(len(first), 32)
		self.assertRegex(first, r"^[A-Za-z0-9_-]+$")
		self.assertNotEqual(first, second)
		frappe.clear_document_cache("Webstore Settings", "Webstore Settings")
		self.assertEqual(gateway_secret(), second)

	def test_generated_secret_survives_saving_the_settings(self):
		"""frappe deletes a stored password on save when the field holds no
		'*****' placeholder - generating a secret and then saving the form
		silently broke the gateway."""
		from upande_webstore.api.gateway import generate_gateway_secret
		from upande_webstore.services.shop import gateway_secret

		set_shop(secret=None)
		secret = generate_gateway_secret()["secret"]
		doc = frappe.get_doc("Webstore Settings")
		doc.save(ignore_permissions=True)
		frappe.clear_document_cache("Webstore Settings", "Webstore Settings")
		self.assertEqual(gateway_secret(), secret)

	def test_desk_actions_need_system_manager(self):
		from upande_webstore.api.gateway import check_shop_address, generate_gateway_secret

		customer, _ = make_portal_user("shop.nosm@example.com", "Shop Nosm Ltd")
		frappe.set_user(customer)
		with self.assertRaises(frappe.PermissionError):
			generate_gateway_secret()
		with self.assertRaises(frappe.PermissionError):
			check_shop_address()


class TestErpEnforcesTheShopMethodList(ShopTestCase):
	"""Defence in depth: the gateway is not the only thing between a shop
	visitor and every whitelisted method - the ERP refuses them too."""

	def _status(self, path, cmd=None, headers=None):
		from werkzeug.exceptions import HTTPException

		from upande_webstore.services import shop

		previous = frappe.local.form_dict
		frappe.local.form_dict = frappe._dict({"cmd": cmd} if cmd else {})
		try:
			with fake_request(path=path, headers=headers if headers is not None else gateway_headers()):
				try:
					shop.before_request()
				except HTTPException as e:
					return e.code
			return None
		finally:
			frappe.local.form_dict = previous

	def test_cmd_not_on_the_list_is_refused(self):
		set_shop()
		self.assertEqual(self._status("/store", cmd="frappe.client.get_list"), 404)
		self.assertEqual(
			self._status("/api/method/upande_webstore.api.cart.get_cart", cmd="frappe.client.get_list"), 404
		)

	def test_api_method_not_on_the_list_is_refused(self):
		set_shop()
		self.assertEqual(self._status("/api/method/frappe.client.get_list"), 404)
		self.assertEqual(self._status("/api/method/upande_webstore.api.boxes.list_box_types"), 404)

	def test_other_api_routes_are_refused(self):
		set_shop()
		self.assertEqual(self._status("/api/resource/Customer"), 404)
		self.assertEqual(self._status("/api/v2/document/Customer"), 404)

	def test_listed_methods_and_the_gateway_config_pass(self):
		set_shop()
		self.assertIsNone(self._status("/api/method/upande_webstore.api.cart.get_cart"))
		self.assertIsNone(self._status("/api/method/login", cmd="login"))
		self.assertIsNone(self._status("/", cmd="frappe.core.doctype.user.user.reset_password"))
		self.assertIsNone(self._status("/api/method/upande_webstore.api.gateway.config"))
		self.assertIsNone(self._status("/store"))

	def test_extra_methods_from_settings_pass(self):
		set_shop(shop_extra_methods="frappe.www.contact.send_message")
		self.assertIsNone(self._status("/api/method/frappe.www.contact.send_message"))

	def test_direct_requests_are_not_affected(self):
		set_shop()
		self.assertIsNone(self._status("/api/method/frappe.client.get_list", headers={}))
		self.assertIsNone(self._status("/api/resource/Customer", headers={}))


class TestStaffEmailsKeepErpLinks(ShopTestCase):
	"""Checkout and accept/decline run inside shop requests, where links are
	built on the shop address - but the sales team's notices must open the
	desk, which the shop does not serve."""

	def _sent_during_shop_request(self, send):
		from unittest.mock import patch

		frappe.db.set_single_value("Webstore Settings", "notification_emails", "sales@example.com")
		frappe.clear_document_cache("Webstore Settings", "Webstore Settings")
		original = frappe.local.conf
		try:
			with fake_request(path="/api/method/upande_webstore.api.checkout.place_order", headers=gateway_headers()):
				run_before_request()
				self.assertTrue(frappe.utils.get_url().startswith(SHOP))
				with patch("frappe.sendmail") as sendmail:
					send()
				self.assertTrue(frappe.utils.get_url().startswith(SHOP), "shop host restored afterwards")
		finally:
			frappe.local.conf = original
		self.assertTrue(sendmail.called)
		return sendmail.call_args.kwargs["message"]

	def test_new_quotation_notice_links_to_the_erp(self):
		set_shop(enabled=1)
		from upande_webstore.api.checkout import _notify_sales_team

		doc = frappe._dict(doctype="Quotation", name="SAL-QTN-TEST-1", party_name="Shop Customer Ltd")
		message = self._sent_during_shop_request(lambda: _notify_sales_team(doc))
		self.assertIn("/desk/quotation/SAL-QTN-TEST-1", message)
		self.assertNotIn("shop.example.com", message)

	def test_accept_notice_links_to_the_erp(self):
		set_shop(enabled=1)
		from upande_webstore.api.portal import _notify

		quotation = frappe._dict(doctype="Quotation", name="SAL-QTN-TEST-2", party_name="Shop Customer Ltd")
		message = self._sent_during_shop_request(lambda: _notify(quotation, "Accepted"))
		self.assertNotIn("shop.example.com", message)


class TestPasswordLinksOnTheErp(ShopTestCase):
	"""A reset link made outside a shop request - desk "Reset Password", the
	ERP's own forgot-password page - points at the ERP. For a customer that
	page would set the password and then refuse the login, losing it."""

	def _key_for(self, user):
		from urllib.parse import parse_qs, urlsplit

		link = frappe.get_doc("User", user)._reset_password(send_email=False)
		return parse_qs(urlsplit(link).query)["key"][0]

	def test_customer_reset_link_is_sent_to_the_shop(self):
		set_shop(enabled=1)
		customer, _ = make_portal_user("shop.reset@example.com", "Shop Reset Ltd")
		key = self._key_for(customer)
		with fake_request(path="/update-password", query_string=f"key={key}"):
			self.assertEqual(run_before_request(), f"{SHOP}/update-password?key={key}")

	def test_staff_reset_link_stays_on_the_erp(self):
		set_shop(enabled=1)
		staff = make_desk_user("shop.staffreset@example.com", ["Sales User"])
		try:
			key = self._key_for(staff)
			with fake_request(path="/update-password", query_string=f"key={key}"):
				self.assertIsNone(run_before_request())
		finally:
			frappe.delete_doc("User", staff, force=True, ignore_permissions=True)

	def test_unknown_key_stays_on_the_erp(self):
		set_shop(enabled=1)
		with fake_request(path="/update-password", query_string="key=not-a-real-key"):
			self.assertIsNone(run_before_request())


class TestExtraAllowListsAreValidated(ShopTestCase):
	def _save(self, **values):
		doc = frappe.get_doc("Webstore Settings")
		doc.shop_address = SHOP
		doc.update(values)
		doc.save(ignore_permissions=True)

	def test_extra_pages_cannot_open_built_in_blocks(self):
		for bad in ("/*", "/", "/api/method/frappe.client.get_list", "/desk", "/app/*", "/printview", "/socket.io/*", "about"):
			with self.assertRaises(frappe.ValidationError, msg=bad):
				self._save(shop_extra_pages=bad)

	def test_reasonable_extra_pages_are_kept(self):
		self._save(shop_extra_pages="/about\n/about/*\n/contact-us")

	def test_extra_methods_cannot_add_desk_or_generic_methods(self):
		for bad in (
			"frappe.client.get_list",
			"frappe.desk.search.search_link",
			"upande_webstore.api.boxes.list_box_types",
			"upande_webstore.api.gateway.config",
			"no_such_app.api.thing",
			"upande_webstore.services.shop.shop_url",  # exists, not whitelisted
		):
			with self.assertRaises(frappe.ValidationError, msg=bad):
				self._save(shop_extra_methods=bad)

	def test_whitelisted_extra_method_is_kept(self):
		self._save(shop_extra_methods="frappe.www.contact.send_message")

	def test_invalid_entries_written_past_validation_are_dropped(self):
		set_shop(shop_extra_methods="frappe.client.get_list\nfrappe.www.contact.send_message", shop_extra_pages="/*\n/about")
		from upande_webstore.services.shop import gateway_config

		config = gateway_config()
		self.assertNotIn("frappe.client.get_list", config["methods"])
		self.assertIn("frappe.www.contact.send_message", config["methods"])
		self.assertEqual(config["extra_pages"], ["/about"])


class TestSwitchWarnsAboutCustomersWithDeskAccounts(ShopTestCase):
	"""A customer login that is a System User counts as staff, so the shop
	would refuse it. On a site where a desk-access role (e.g. Wiki User)
	turned customers into System Users, switching on would lock them out."""

	def test_turning_on_names_customer_logins_that_are_desk_accounts(self):
		from upande_webstore.services.shop import customer_logins_with_desk_accounts

		email, customer = make_portal_user("shop.deskcust@example.com", "Shop Deskcust Ltd")
		frappe.db.set_value("User", email, "user_type", "System User")
		try:
			self.assertIn(email, customer_logins_with_desk_accounts())
			set_shop(enabled=0, shop_last_check_ok=frappe.utils.now_datetime())
			frappe.clear_messages()
			doc = frappe.get_doc("Webstore Settings")
			doc.send_customers_to_shop = 1
			doc.save(ignore_permissions=True)
			messages = " ".join(str(m) for m in frappe.get_message_log())
			self.assertIn(email, messages)
		finally:
			frappe.db.set_value("User", email, "user_type", "Website User")

	def test_website_user_customers_are_not_named(self):
		from upande_webstore.services.shop import customer_logins_with_desk_accounts

		email, _ = make_portal_user("shop.webcust@example.com", "Shop Webcust Ltd")
		self.assertNotIn(email, customer_logins_with_desk_accounts())
