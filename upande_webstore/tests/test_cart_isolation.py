"""Task 2: one open cart per user *per store* - the open-cart lookup is now
{user, status: "Open", webstore}, so a shopper can hold a basket of roses and
a basket of yoghurt at once without one clearing the other.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.store import clear_store_cache
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import (
	delete_all_webstores,
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)

USER = "cart.isolation@example.com"


class TestCartIsolation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-ISO-ROSE")
		make_item_price("WS-ISO-ROSE", "Standard Selling", 40)
		make_test_product("WS-ISO-MILK")
		make_item_price("WS-ISO-MILK", "Standard Selling", 5)
		make_portal_user(USER)
		set_stock("WS-ISO-ROSE", 50)
		set_stock("WS-ISO-MILK", 50)

	def setUp(self):
		frappe.set_user(USER)
		frappe.db.delete("Webstore Cart", {"user": USER})
		delete_all_webstores()
		make_webstore("flowers", title="Flowers")
		make_webstore("dairy", title="Dairy")
		clear_store_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": USER})
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		delete_all_webstores()

	def _as(self, slug):
		frappe.local.webstore_slug = slug
		clear_store_cache()

	def test_adding_to_one_store_leaves_the_others_cart_empty(self):
		from upande_webstore.api import cart

		self._as("flowers")
		cart.add_item("WS-ISO-ROSE", 2)

		self._as("dairy")
		self.assertEqual(cart.get_cart()["count"], 0)

		self._as("flowers")
		self.assertEqual(cart.get_cart()["count"], 2)

	def test_each_store_gets_its_own_open_cart_row(self):
		from upande_webstore.api import cart

		self._as("flowers")
		cart.add_item("WS-ISO-ROSE", 1)
		self._as("dairy")
		cart.add_item("WS-ISO-MILK", 3)

		open_carts = frappe.get_all(
			"Webstore Cart", filters={"user": USER, "status": "Open"}, fields=["webstore"]
		)
		self.assertEqual(len(open_carts), 2)
		self.assertEqual({row.webstore for row in open_carts}, {"flowers", "dairy"})

	def test_updating_one_stores_cart_does_not_touch_the_other(self):
		from upande_webstore.api import cart

		self._as("flowers")
		cart.add_item("WS-ISO-ROSE", 1)
		self._as("dairy")
		cart.add_item("WS-ISO-MILK", 1)

		self._as("flowers")
		cart.update_qty("WS-ISO-ROSE", 5)

		self._as("dairy")
		result = cart.get_cart()
		self.assertEqual(result["items"][0]["qty"], 1)
