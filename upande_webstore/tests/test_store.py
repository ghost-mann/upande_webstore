"""services.store.current_store(): resolution and caching only.

No routing knowledge here — Task 2 resolves the path prefix and sets
`frappe.local.webstore_slug` (or whatever it lands on); this module only has
to answer "given that override, or none, which Webstore is current".
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.store import clear_store_cache, current_store
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import delete_all_webstores


class TestCurrentStore(IntegrationTestCase):
	def setUp(self):
		# The site under test has already run patches.create_default_webstore,
		# so a "store" row exists before any test does. Resolution is exactly
		# what these tests vary, so start from none every time.
		delete_all_webstores()
		clear_store_cache()

	def tearDown(self):
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		delete_all_webstores()
		clear_store_cache()

	def test_no_store_at_all_resolves_to_none(self):
		clear_store_cache()
		self.assertIsNone(current_store())

	def test_the_single_published_store_resolves(self):
		make_webstore("flowers")
		clear_store_cache()
		store = current_store()
		self.assertEqual(store.name, "flowers")

	def test_two_stores_with_neither_slugged_store_resolves_to_none(self):
		"""Without a path-derived slug (Task 2) and with no single published
		store and no slug "store", there is nothing safe to guess."""
		make_webstore("flowers")
		make_webstore("dairy")
		clear_store_cache()
		self.assertIsNone(current_store())

	def test_falls_back_to_the_slug_store_when_ambiguous(self):
		make_webstore("flowers")
		make_webstore("store")
		clear_store_cache()
		store = current_store()
		self.assertEqual(store.name, "store")

	def test_an_explicit_override_wins(self):
		make_webstore("flowers")
		make_webstore("dairy")
		frappe.local.webstore_slug = "dairy"
		clear_store_cache()
		store = current_store()
		self.assertEqual(store.name, "dairy")

	def test_result_is_cached_within_a_request(self):
		make_webstore("flowers")
		clear_store_cache()
		first = current_store()
		make_webstore("dairy")
		# a second store now exists, but the cached resolution must not change
		second = current_store()
		self.assertIs(first, second)

	def test_clear_store_cache_forces_re_resolution(self):
		make_webstore("flowers")
		clear_store_cache()
		current_store()
		make_webstore("store")
		clear_store_cache()
		store = current_store()
		self.assertEqual(store.name, "store")

	def test_unpublished_store_is_not_the_single_published_store(self):
		make_webstore("flowers", published=0)
		clear_store_cache()
		self.assertIsNone(current_store())
