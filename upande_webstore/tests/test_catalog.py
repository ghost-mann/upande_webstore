import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	make_variant_template,
	setup_webstore_settings,
)


class TestCatalog(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CAT-ALPHA", web_title="Alpha Sensor", featured=1)
		make_test_product("WS-CAT-BETA", web_title="Beta Gateway")
		make_test_product("WS-CAT-HIDDEN", web_title="Hidden Product", published=0)
		make_item_price("WS-CAT-ALPHA", "Standard Selling", 10)

	def test_only_published_products_listed(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Hidden Product", titles)

	def test_search(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(search="Alpha")
		self.assertEqual(len(result["products"]), 1)
		self.assertEqual(result["products"][0]["web_title"], "Alpha Sensor")
		self.assertEqual(result["products"][0]["price"]["rate"], 10)

	def test_featured_filter(self):
		from upande_webstore.services.catalog import get_products

		result = get_products(featured_only=True, page_length=100)
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Beta Gateway", titles)

	def test_categories(self):
		from upande_webstore.services.catalog import get_categories

		categories = get_categories()
		self.assertTrue(any(c["name"] == "Products" and c["count"] >= 2 for c in categories))

	def test_store_page_renders(self):
		from frappe.utils import get_html_for_route

		html = get_html_for_route("store")
		self.assertIn("Alpha Sensor", html)
		self.assertNotIn("Hidden Product", html)

	def test_guest_can_browse_products(self):
		"""Regression guard once the bench is upgraded past frappe 16.27.

		Unpatched, this passes on both 16.27 (where get_cached_doc/value do not
		enforce role permissions) and 16.32+ (where the source fix reads Item
		fields via frappe.db.get_value, which never checks permissions). It is
		not, on its own, proof the bug is fixed — see
		test_guest_browsing_survives_item_permission_enforcement below, which
		simulates the 16.32 behaviour this bench cannot reproduce natively.
		"""
		from upande_webstore.services.catalog import get_products

		frappe.set_user("Guest")
		try:
			result = get_products(page_length=100)
		finally:
			frappe.set_user("Administrator")
		titles = [p["web_title"] for p in result["products"]]
		self.assertIn("Alpha Sensor", titles)
		self.assertNotIn("Hidden Product", titles)

	def test_guest_browsing_survives_item_permission_enforcement(self):
		"""Reproduce the frappe 16.32 storefront 403, on this 16.27 bench.

		On a live 16.32 site, Guest gets 403 on /store and /store/<product>
		because frappe.get_cached_doc/get_cached_value there enforce role
		permission on Item — and the app never grants Guest read on Item (Item
		carries cost/valuation data). On this 16.27 bench that enforcement does
		not happen, so a plain guest test (see above) passes before and after a
		fix and proves nothing.

		Monkeypatching get_cached_doc/get_cached_value to raise for Item, while
		passing every other doctype through unchanged, reproduces the 16.32
		behaviour here. This must fail before the source fix (which replaced
		those permission-checked reads with frappe.db.get_value, a
		permission-independent field read) and pass after it.

		The fakes below only raise when frappe.flags.ignore_permissions is
		falsy — real permission checks in frappe return early once that flag
		is set, so an unconditional raise here would be stricter than the
		framework and could hide a fix (or push toward the wrong one) that
		relies on the flag, the way services/pricing.get_item_price now does
		for its ERPNext price lookup.
		"""
		real_get_cached_doc = frappe.get_cached_doc
		real_get_cached_value = frappe.get_cached_value

		def fake_get_cached_doc(doctype, *args, **kwargs):
			if doctype == "Item" and not frappe.flags.ignore_permissions:
				raise frappe.PermissionError("No permission for Item")
			return real_get_cached_doc(doctype, *args, **kwargs)

		def fake_get_cached_value(doctype, *args, **kwargs):
			if doctype == "Item" and not frappe.flags.ignore_permissions:
				raise frappe.PermissionError("No permission for Item")
			return real_get_cached_value(doctype, *args, **kwargs)

		# A template item: its listing price comes from get_variant_price_range
		# (plain frappe.get_all queries), not get_item_price — which calls
		# into ERPNext's own get_item_details, itself unconditionally calling
		# frappe.get_cached_doc("Item", ...) and so out of this app's control.
		# Isolating on a template keeps this test to what upande_webstore is
		# responsible for fixing.
		make_variant_template("WS-CAT-GUESTPERM")
		make_test_product("WS-CAT-GUESTPERM", web_title="Guest Perm Template")

		frappe.get_cached_doc = fake_get_cached_doc
		frappe.get_cached_value = fake_get_cached_value
		try:
			frappe.set_user("Guest")
			from upande_webstore.services.catalog import get_products
			from upande_webstore.services.stock import get_stock_info

			result = get_products(search="Guest Perm Template")
			titles = [p["web_title"] for p in result["products"]]
			self.assertIn("Guest Perm Template", titles)
			product = next(p for p in result["products"] if p["web_title"] == "Guest Perm Template")
			self.assertTrue(product["has_variants"])

			info = get_stock_info("WS-CAT-ALPHA")
			self.assertIn("in_stock", info)

			# A non-template product: get_item_price's ERPNext price lookup
			# is the call site the template case above deliberately avoids.
			# WS-CAT-ALPHA has a seeded Item Price (see setUpClass), so a rate
			# of 0 would mean pricing silently failed rather than resolved.
			alpha_result = get_products(search="Alpha Sensor")
			alpha_titles = [p["web_title"] for p in alpha_result["products"]]
			self.assertIn("Alpha Sensor", alpha_titles)
			alpha_product = next(
				p for p in alpha_result["products"] if p["web_title"] == "Alpha Sensor"
			)
			self.assertIsNotNone(alpha_product["price"])
			self.assertGreater(alpha_product["price"]["rate"], 0)
		finally:
			frappe.get_cached_doc = real_get_cached_doc
			frappe.get_cached_value = real_get_cached_value
			frappe.set_user("Administrator")
