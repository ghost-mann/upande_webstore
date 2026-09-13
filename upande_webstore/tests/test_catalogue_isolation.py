"""Task 2: the catalogue (listing, search and the category filter list) is
filtered by the resolved store, everywhere `services.catalog` is read from -
`www/store.py`'s listing and `api/search.py` both go through `get_products()`.

Membership is the `stores` child table on `Webstore Product` when it carries
any rows at all; an empty table falls back to the product's own
`primary_store` (blank meaning the default store) — see
`services/catalog.py::_store_product_names`.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.catalog import get_categories, get_products
from upande_webstore.services.store import clear_store_cache
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import delete_all_webstores, make_test_product, setup_webstore_settings

ITEMS = ["WS-CAT-ROSE", "WS-CAT-MILK", "WS-CAT-BOTH", "WS-CAT-UNSCOPED"]
GROUPS = ("WS Store Flowers Cat", "WS Store Dairy Cat")


class TestCatalogueIsolation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		for group in GROUPS:
			if not frappe.db.exists("Item Group", group):
				frappe.get_doc(
					{
						"doctype": "Item Group",
						"item_group_name": group,
						"parent_item_group": "All Item Groups",
					}
				).insert(ignore_permissions=True)

	def setUp(self):
		delete_all_webstores()
		make_webstore("flowers", title="Flowers")
		make_webstore("dairy", title="Dairy")
		clear_store_cache()
		make_test_product(
			"WS-CAT-ROSE",
			web_title="Catalogue Rose",
			item_group="WS Store Flowers Cat",
			primary_store="flowers",
			stores=["flowers"],
		)
		make_test_product(
			"WS-CAT-MILK",
			web_title="Catalogue Milk",
			item_group="WS Store Dairy Cat",
			primary_store="dairy",
			stores=["dairy"],
		)
		make_test_product(
			"WS-CAT-BOTH",
			web_title="Catalogue Both",
			item_group="WS Store Flowers Cat",
			primary_store="flowers",
			stores=["flowers", "dairy"],
		)

	def tearDown(self):
		frappe.db.delete("Webstore Product", {"item": ["in", ITEMS]})
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		delete_all_webstores()

	def _titles(self, slug, **kwargs):
		frappe.local.webstore_slug = slug
		clear_store_cache()
		return {p["web_title"] for p in get_products(page_length=100, **kwargs)["products"]}

	def test_a_products_own_store_lists_it(self):
		self.assertIn("Catalogue Rose", self._titles("flowers"))

	def test_a_product_is_absent_from_another_stores_catalogue(self):
		self.assertNotIn("Catalogue Rose", self._titles("dairy"))
		self.assertNotIn("Catalogue Milk", self._titles("flowers"))

	def test_a_product_listed_in_both_stores_appears_in_both(self):
		self.assertIn("Catalogue Both", self._titles("flowers"))
		self.assertIn("Catalogue Both", self._titles("dairy"))

	def test_search_is_scoped_the_same_way(self):
		titles = self._titles("dairy", search="Catalogue")
		self.assertIn("Catalogue Milk", titles)
		self.assertNotIn("Catalogue Rose", titles)

	def test_categories_are_scoped_by_store(self):
		frappe.local.webstore_slug = "flowers"
		clear_store_cache()
		values = {c["value"] for c in get_categories()}
		self.assertIn("WS Store Flowers Cat", values)
		self.assertNotIn("WS Store Dairy Cat", values)

	def test_an_unscoped_product_belongs_only_to_the_default_store(self):
		"""No `stores` rows and no `primary_store`: visible in the default
		store's catalogue (as it always was, before multi-store existed) and
		nowhere else."""
		make_test_product("WS-CAT-UNSCOPED", web_title="Catalogue Unscoped")
		try:
			make_webstore("store", title="Default")
			self.assertIn("Catalogue Unscoped", self._titles("store"))
			self.assertNotIn("Catalogue Unscoped", self._titles("flowers"))
			self.assertNotIn("Catalogue Unscoped", self._titles("dairy"))
		finally:
			frappe.db.delete("Webstore Product", {"item": "WS-CAT-UNSCOPED"})

	def test_no_store_resolved_shows_every_product(self):
		"""No `Webstore` rows at all - the feature is effectively absent, and
		the catalogue must show exactly what it always did."""
		delete_all_webstores()
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		titles = {p["web_title"] for p in get_products(page_length=100)["products"]}
		self.assertIn("Catalogue Rose", titles)
		self.assertIn("Catalogue Milk", titles)
		self.assertIn("Catalogue Both", titles)
