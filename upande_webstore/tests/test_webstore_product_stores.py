"""Task 2: `Webstore Product`'s store links - a `primary_store` Link fixing
the product's one canonical URL, and a `stores` child table controlling
which catalogues list it. See services/catalog.py for the membership rule
and services/store.py for why one product can still have only one route.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import delete_all_webstores, make_test_product, setup_webstore_settings


class TestWebstoreProductPrimaryStoreRoute(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def setUp(self):
		delete_all_webstores()
		make_webstore("flowers", title="Flowers")

	def tearDown(self):
		frappe.db.delete(
			"Webstore Product", {"item": ["like", "WS-PSTORE-%"]}
		)
		delete_all_webstores()

	def test_blank_primary_store_routes_under_the_default_store(self):
		product = make_test_product("WS-PSTORE-DEFAULT", web_title="PStore Default")
		self.assertEqual(product.route, "store/pstore-default")

	def test_a_non_default_primary_store_prefixes_the_route(self):
		product = make_test_product(
			"WS-PSTORE-FLOWERS", web_title="PStore Flowers", primary_store="flowers"
		)
		self.assertEqual(product.route, "flowers/store/pstore-flowers")

	def test_changing_the_primary_store_recomputes_the_route(self):
		make_webstore("dairy", title="Dairy")
		product = make_test_product(
			"WS-PSTORE-MOVE", web_title="PStore Move", primary_store="flowers"
		)
		self.assertEqual(product.route, "flowers/store/pstore-move")

		product.primary_store = "dairy"
		product.save(ignore_permissions=True)
		self.assertEqual(product.route, "dairy/store/pstore-move")

	def test_moving_back_to_the_default_store_drops_the_prefix(self):
		product = make_test_product(
			"WS-PSTORE-BACK", web_title="PStore Back", primary_store="flowers"
		)
		self.assertEqual(product.route, "flowers/store/pstore-back")

		product.primary_store = ""
		product.save(ignore_permissions=True)
		self.assertEqual(product.route, "store/pstore-back")

	def test_stores_table_records_extra_catalogues(self):
		make_webstore("dairy", title="Dairy")
		product = make_test_product(
			"WS-PSTORE-MULTI",
			web_title="PStore Multi",
			primary_store="flowers",
			stores=["flowers", "dairy"],
		)
		self.assertEqual({row.webstore for row in product.stores}, {"flowers", "dairy"})
		# canonical URL is still the one primary_store, regardless of how many
		# catalogues list the product
		self.assertEqual(product.route, "flowers/store/pstore-multi")
