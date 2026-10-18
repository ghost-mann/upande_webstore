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
	set_shop(address="", enabled=0, secret=None)
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
