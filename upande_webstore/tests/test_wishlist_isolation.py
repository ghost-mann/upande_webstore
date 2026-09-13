"""Task 2: one wishlist per user *per store*.

`Webstore Wishlist.user` used to be unique site-wide - that rule is replaced
with user+webstore uniqueness (webstore_wishlist.py), so a shopper can
wishlist flowers and yoghurt without one list clobbering the other, and the
old single-wishlist-per-user rule no longer blocks a second store's list.
"""

import frappe
from frappe import _
from frappe.tests import IntegrationTestCase

from upande_webstore.services.store import clear_store_cache
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import delete_all_webstores, make_portal_user, make_test_product, setup_webstore_settings

USER = "wishlist.isolation@example.com"


class TestWishlistIsolation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		# Stores before products, and each product in the store it is
		# wishlisted from — see test_cart_isolation for the same reason.
		delete_all_webstores()
		make_webstore("flowers", title="Flowers")
		make_webstore("dairy", title="Dairy")
		cls.rose = make_test_product(
			"WS-WISH-ISO-ROSE", web_title="Wishlist Rose", primary_store="flowers"
		)
		cls.milk = make_test_product(
			"WS-WISH-ISO-MILK", web_title="Wishlist Milk", primary_store="dairy"
		)
		make_portal_user(USER)

	def setUp(self):
		frappe.set_user(USER)
		frappe.db.delete("Webstore Wishlist", {"user": USER})
		clear_store_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Wishlist", {"user": USER})
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug

	def _as(self, slug):
		frappe.local.webstore_slug = slug
		clear_store_cache()

	def test_wishlisting_in_one_store_leaves_the_other_empty(self):
		from upande_webstore.api import wishlist

		self._as("flowers")
		wishlist.toggle(self.rose.name)

		self._as("dairy")
		self.assertEqual(wishlist.get_wishlist()["count"], 0)

		self._as("flowers")
		self.assertEqual(wishlist.get_wishlist()["count"], 1)

	def test_each_store_gets_its_own_wishlist_row(self):
		from upande_webstore.api import wishlist

		self._as("flowers")
		wishlist.toggle(self.rose.name)
		self._as("dairy")
		wishlist.toggle(self.milk.name)

		rows = frappe.get_all("Webstore Wishlist", filters={"user": USER}, fields=["webstore"])
		self.assertEqual(len(rows), 2)
		self.assertEqual({row.webstore for row in rows}, {"flowers", "dairy"})

	def test_the_old_one_wishlist_per_user_rule_no_longer_blocks_a_second_store(self):
		"""What used to be a column-level unique on `user` alone."""
		first = frappe.get_doc({"doctype": "Webstore Wishlist", "user": USER, "webstore": "flowers"})
		first.insert(ignore_permissions=True)
		second = frappe.get_doc({"doctype": "Webstore Wishlist", "user": USER, "webstore": "dairy"})
		second.insert(ignore_permissions=True)  # must not raise

	def test_a_second_wishlist_for_the_same_user_and_store_is_still_rejected(self):
		first = frappe.get_doc({"doctype": "Webstore Wishlist", "user": USER, "webstore": "flowers"})
		first.insert(ignore_permissions=True)
		duplicate = frappe.get_doc({"doctype": "Webstore Wishlist", "user": USER, "webstore": "flowers"})
		self.assertRaises(frappe.ValidationError, duplicate.insert, ignore_permissions=True)

	def test_a_product_from_another_store_cannot_be_wishlisted(self):
		"""Same rule as the cart: out of catalogue, out of reach."""
		from upande_webstore.api import wishlist

		self._as("flowers")
		with self.assertRaises(frappe.ValidationError):
			wishlist.toggle(self.milk.name)

