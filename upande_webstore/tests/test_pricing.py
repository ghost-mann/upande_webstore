import contextlib

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_price_list,
	make_test_product,
	setup_webstore_settings,
)


@contextlib.contextmanager
def _enforce_item_read_permission():
	"""Reproduce, on this 16.27 bench, the 403 get_item_price hits in
	production (frappe 16.32 / ERPNext 16.33).

	This bench's own `frappe.get_cached_doc("Item", ...)` never checks
	permission on this frappe version (confirmed: `Document.has_permission`
	is real and unmodified here, and correctly denies Guest/Customer read on
	Item when actually asked -- but nothing in `get_item_details`'s call
	graph on this bench ever asks). Production's ERPNext evidently does ask,
	somewhere inside `get_item_details` that is opaque to this app and out
	of its control -- that is the entire premise of the bug being fixed.

	So rather than fake the permission *logic* (already correct and
	unmodified below -- see the confirmed roles Item actually grants), this
	stands in for whatever production's get_item_details does differently:
	it wraps the very entry point `services.pricing.get_item_price` calls,
	and has that wrapper fetch the *same* request-cached Item doc
	get_item_price would have already touched, then calls its real,
	unmodified `check_permission("read")` before handing off to the real
	get_item_details. Deliberately not on frappe.get_cached_doc's raw fetch
	path itself, which is not the problem, per the same evidence, and
	which -- because it runs before get_item_price has a chance to set the
	doc's own flag -- can never be, without contradicting the very fix this
	is meant to prove.

	get_item_price now runs the lookup as Administrator, so the real check
	passes for the lookup alone and nothing is granted to the visitor.
	"""
	import erpnext.stock.get_item_details as get_item_details_module

	real_get_item_details = get_item_details_module.get_item_details

	def fake_get_item_details(ctx, *args, **kwargs):
		item = frappe.get_cached_doc("Item", ctx.get("item_code"))
		item.check_permission("read")
		return real_get_item_details(ctx, *args, **kwargs)

	get_item_details_module.get_item_details = fake_get_item_details
	try:
		yield
	finally:
		get_item_details_module.get_item_details = real_get_item_details


class TestPricing(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-PRICE-ITEM")
		make_item_price("WS-PRICE-ITEM", "Standard Selling", 100)
		make_price_list("Webstore B2B")
		make_item_price("WS-PRICE-ITEM", "Webstore B2B", 80)
		make_portal_user("b2b.buyer@example.com", "B2B Buyer Ltd", price_list="Webstore B2B")
		make_portal_user("retail.buyer@example.com", "Retail Buyer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_gets_guest_price_list(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="Guest")
		self.assertEqual(price["rate"], 100)
		self.assertEqual(price["price_list"], "Standard Selling")
		self.assertFalse(price["is_customer_price"])

	def test_customer_price_list_wins(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="b2b.buyer@example.com")
		self.assertEqual(price["rate"], 80)
		self.assertEqual(price["price_list"], "Webstore B2B")
		self.assertTrue(price["is_customer_price"])

	def test_customer_without_price_list_falls_back_to_guest(self):
		from upande_webstore.services.pricing import get_item_price

		price = get_item_price("WS-PRICE-ITEM", user="retail.buyer@example.com")
		self.assertEqual(price["rate"], 100)
		self.assertFalse(price["is_customer_price"])

	def test_get_customer_resolution(self):
		from upande_webstore.services.pricing import get_customer

		self.assertEqual(get_customer("b2b.buyer@example.com"), "B2B Buyer Ltd")
		self.assertIsNone(get_customer("Guest"))


class TestGuestAndCustomerPricingSurvivesItemPermissionEnforcement(IntegrationTestCase):
	"""get_item_price's ERPNext price lookup (get_item_details) unconditionally
	loads the Item document -- readable, on newer frappe, by Sales User,
	Stock User and friends, but not by Guest, and not by the Customer role
	either. Both must still get a real price, not a 403 and not a silent 0.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-PRICEPERM-ITEM", web_title="Priceperm Item")
		make_item_price("WS-PRICEPERM-ITEM", "Standard Selling", 65)
		make_portal_user("priceperm.customer@example.com", "Priceperm Customer")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_catalogue_price_survives_item_permission_enforcement(self):
		from upande_webstore.services.catalog import get_products

		with _enforce_item_read_permission():
			frappe.set_user("Guest")
			result = get_products(search="Priceperm Item")
		product = next(p for p in result["products"] if p["web_title"] == "Priceperm Item")
		self.assertIsNotNone(product["price"])
		self.assertGreater(product["price"]["rate"], 0)

	def test_customer_role_catalogue_price_survives_item_permission_enforcement(self):
		from upande_webstore.services.catalog import get_products

		with _enforce_item_read_permission():
			frappe.set_user("priceperm.customer@example.com")
			result = get_products(search="Priceperm Item")
		product = next(p for p in result["products"] if p["web_title"] == "Priceperm Item")
		self.assertIsNotNone(product["price"])
		self.assertGreater(product["price"]["rate"], 0)

	def test_item_permission_bypass_does_not_leak_past_the_call(self):
		"""The Item stays in the request-local document cache; nothing else in
		the same request may inherit a permission bypass on it."""
		from upande_webstore.services.pricing import get_item_price

		with _enforce_item_read_permission():
			frappe.set_user("Guest")
			get_item_price("WS-PRICEPERM-ITEM")
			item = frappe.get_cached_doc("Item", "WS-PRICEPERM-ITEM")
			self.assertFalse(item.flags.ignore_permissions)


@contextlib.contextmanager
def _enforce_pricing_context():
	"""Reproduce, on this 16.27 bench, the checks ERPNext 16.51 added at the
	top of get_item_details (live Mona Flowers runs 16.51.1).

	Upstream, `get_item_details` first calls
	`erpnext.accounts.doctype.pricing_rule.pricing_rule.validate_pricing_context`,
	which authorises the transaction being priced and its party:
	`frappe.has_permission(ctx.doctype, throw=True)` -- the Quotation this
	app names -- and `frappe.has_permission("Customer", "select", doc=...,
	throw=True)` for the customer. Guest and the Customer role hold neither,
	so on live every length a visitor picks fails with "No permission for
	Quotation". This wrapper runs the same two checks, with the same real
	permission engine, before handing off to the real get_item_details.
	"""
	import erpnext.stock.get_item_details as get_item_details_module

	real_get_item_details = get_item_details_module.get_item_details

	def gated_get_item_details(ctx, *args, **kwargs):
		frappe.has_permission(ctx.get("doctype"), throw=True)
		if ctx.get("customer"):
			frappe.has_permission("Customer", "select", doc=ctx.get("customer"), throw=True)
		return real_get_item_details(ctx, *args, **kwargs)

	get_item_details_module.get_item_details = gated_get_item_details
	try:
		yield
	finally:
		get_item_details_module.get_item_details = real_get_item_details


class TestPricingSurvivesPricingContextValidation(IntegrationTestCase):
	"""Guests and portal customers price items without holding Quotation or
	Customer permissions; ERPNext 16.51 demands both of whoever calls
	get_item_details."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-PRICECTX-ITEM", web_title="Pricectx Item")
		make_item_price("WS-PRICECTX-ITEM", "Standard Selling", 42)
		make_price_list("Webstore Ctx B2B")
		make_item_price("WS-PRICECTX-ITEM", "Webstore Ctx B2B", 37)
		make_portal_user("pricectx.buyer@example.com", "Pricectx Buyer Ltd", price_list="Webstore Ctx B2B")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_gets_a_price(self):
		from upande_webstore.services.pricing import get_item_price

		with _enforce_pricing_context():
			frappe.set_user("Guest")
			price = get_item_price("WS-PRICECTX-ITEM")
		self.assertEqual(price["rate"], 42)

	def test_portal_customer_gets_their_own_price(self):
		from upande_webstore.services.pricing import get_item_price

		with _enforce_pricing_context():
			frappe.set_user("pricectx.buyer@example.com")
			price = get_item_price("WS-PRICECTX-ITEM")
		self.assertEqual(price["rate"], 37)
		self.assertTrue(price["is_customer_price"])

	def test_the_caller_is_still_the_session_user_afterwards(self):
		from upande_webstore.services.pricing import get_item_price

		with _enforce_pricing_context():
			frappe.set_user("pricectx.buyer@example.com")
			get_item_price("WS-PRICECTX-ITEM")
			self.assertEqual(frappe.session.user, "pricectx.buyer@example.com")
