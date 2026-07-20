import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


class TestWishlist(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		cls.product = make_test_product("WS-WISH-ITEM", web_title="Wishable Widget")
		make_portal_user("wish.user@example.com")

	def setUp(self):
		frappe.set_user("wish.user@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Wishlist", {"user": "wish.user@example.com"})

	def test_toggle_on_off(self):
		from upande_webstore.api import wishlist

		result = wishlist.toggle(self.product.name)
		self.assertTrue(result["wishlisted"])
		self.assertEqual(result["count"], 1)
		result = wishlist.toggle(self.product.name)
		self.assertFalse(result["wishlisted"])
		self.assertEqual(result["count"], 0)

	def test_get_wishlist(self):
		from upande_webstore.api import wishlist

		wishlist.toggle(self.product.name)
		data = wishlist.get_wishlist()
		self.assertEqual(data["items"][0]["web_title"], "Wishable Widget")
		self.assertIn("price", data["items"][0])

	def test_guest_rejected(self):
		from upande_webstore.api import wishlist

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, wishlist.toggle, self.product.name)
