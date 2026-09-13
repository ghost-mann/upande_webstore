"""Task 2: routing to a store over a real HTTP request.

Exercises the same slice test_me_redirect.py and test_routes.py already use -
a hand-built `frappe.local.request` plus `frappe.website.serve.get_response` -
rather than only the resolution functions in isolation, because the thing
actually under test is the wiring: `website_route_rules` finding the right
controller, and `resolve_webstore_prefix` (the before_request hook) landing
the slug on `frappe.local` before that controller's own get_context() runs.

`get_response()` never calls before_request itself (only frappe.app.application
does, for a real inbound request), so `_hit()` below runs the hook by hand -
exactly the gap `services.store.resolve_webstore_prefix`'s docstring names.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.serve import get_response
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from upande_webstore.services.store import clear_store_cache, resolve_webstore_prefix
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import (
	delete_all_webstores,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


def _hit(path):
	builder = EnvironBuilder(path="/" + path.lstrip("/"))
	frappe.local.request = Request(builder.get_environ())
	if hasattr(frappe.local, "webstore_slug"):
		del frappe.local.webstore_slug
	resolve_webstore_prefix()
	clear_store_cache()
	return get_response(path)


def _reset_request():
	frappe.local.request = None
	clear_store_cache()
	if hasattr(frappe.local, "webstore_slug"):
		del frappe.local.webstore_slug


class TestDefaultStoreRoutesUnchanged(IntegrationTestCase):
	"""The acceptance bar: a single-store site's own URLs are untouched."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_portal_user("routing.customer@example.com", "Routing Customer")

	def setUp(self):
		delete_all_webstores()
		clear_store_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		_reset_request()
		delete_all_webstores()

	def test_bare_store_resolves_with_no_webstore_row_at_all(self):
		"""Before Task 1's patch has ever run, /store must still work."""
		self.assertEqual(_hit("/store").status_code, 200)

	def test_bare_store_resolves_with_the_migrated_default_store(self):
		make_webstore("store", title="Default")
		self.assertEqual(_hit("/store").status_code, 200)

	def test_bare_cart_resolves_for_a_logged_in_customer(self):
		make_webstore("store", title="Default")
		frappe.set_user("routing.customer@example.com")
		self.assertEqual(_hit("/cart").status_code, 200)

	def test_bare_wishlist_resolves_for_a_logged_in_customer(self):
		make_webstore("store", title="Default")
		frappe.set_user("routing.customer@example.com")
		self.assertEqual(_hit("/wishlist").status_code, 200)


class TestPrefixedStoreRouting(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def setUp(self):
		delete_all_webstores()
		make_webstore("store", title="Default")
		make_webstore("flowers", title="Flowers")
		make_webstore("dairy", title="Dairy")
		make_webstore("closed", title="Closed Shop", published=0)
		clear_store_cache()
		make_test_product(
			"WS-ROUTE-ROSE", web_title="Route Test Rose", primary_store="flowers", stores=["flowers"]
		)
		make_test_product(
			"WS-ROUTE-MILK", web_title="Route Test Milk", primary_store="dairy", stores=["dairy"]
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		_reset_request()
		frappe.db.delete("Webstore Product", {"item": ["in", ["WS-ROUTE-ROSE", "WS-ROUTE-MILK"]]})
		delete_all_webstores()

	def test_prefixed_store_resolves_its_own_store(self):
		content = _hit("/flowers/store").data.decode()
		self.assertIn("Route Test Rose", content)

	def test_prefixed_store_does_not_leak_another_stores_catalogue(self):
		content = _hit("/flowers/store").data.decode()
		self.assertNotIn("Route Test Milk", content)

	def test_a_different_prefix_shows_its_own_catalogue_only(self):
		content = _hit("/dairy/store").data.decode()
		self.assertIn("Route Test Milk", content)
		self.assertNotIn("Route Test Rose", content)

	def test_unknown_slug_404s(self):
		self.assertEqual(_hit("/nope/store").status_code, 404)

	def test_unpublished_store_404s_for_a_guest(self):
		frappe.set_user("Guest")
		self.assertEqual(_hit("/closed/store").status_code, 404)

	def test_unpublished_store_is_visible_to_a_system_manager(self):
		frappe.set_user("Administrator")
		self.assertEqual(_hit("/closed/store").status_code, 200)

	def test_a_products_canonical_route_carries_its_own_prefix(self):
		route = frappe.db.get_value("Webstore Product", {"item": "WS-ROUTE-ROSE"}, "route")
		self.assertEqual(route, "flowers/store/route-test-rose")

	def test_the_default_stores_product_route_carries_no_prefix(self):
		product = make_test_product("WS-ROUTE-DEFAULT", web_title="Route Test Default")
		self.assertEqual(product.route, "store/route-test-default")
		frappe.db.delete("Webstore Product", {"item": "WS-ROUTE-DEFAULT"})
