"""Task 2's patch: `stamp_existing_records_with_default_store`.

Every product, cart and wishlist that predates Task 2 has a blank store
field; this patch assigns the default store (slug "store") to all of them,
the same reasoning patches.create_default_webstore used for the store row
itself. Idempotent, and a clean no-op on a site with no `Webstore` row.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.patches.stamp_existing_records_with_default_store import execute
from upande_webstore.services.store import DEFAULT_SLUG, clear_store_cache
from upande_webstore.tests.test_webstore import make_webstore
from upande_webstore.tests.utils import (
	delete_all_webstores,
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)

BUYER = "patch.buyer@example.com"


class TestStampExistingRecordsPatch(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-PATCH-QUOTE-ITEM")
		make_item_price("WS-PATCH-QUOTE-ITEM", "Standard Selling", 30)
		set_stock("WS-PATCH-QUOTE-ITEM", 10)
		make_portal_user(BUYER)

	def setUp(self):
		delete_all_webstores()
		clear_store_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		delete_all_webstores()

	def test_no_ops_cleanly_with_no_webstore_row(self):
		execute()  # must not raise, and must not create one either

	def test_stamps_a_blank_product_cart_and_wishlist(self):
		make_webstore(DEFAULT_SLUG, title="Default")
		product = make_test_product("WS-PATCH-ITEM", web_title="Patch Item")
		# make_test_product (Task 2's own helper) already passes an explicit
		# primary_store; force it blank here to stand in for a genuinely
		# pre-Task-2 row on disk.
		frappe.db.set_value("Webstore Product", product.name, "primary_store", "")

		cart = frappe.get_doc(
			{"doctype": "Webstore Cart", "user": BUYER, "status": "Open"}
		)
		cart.insert(ignore_permissions=True)
		wish = frappe.get_doc({"doctype": "Webstore Wishlist", "user": BUYER})
		wish.insert(ignore_permissions=True)
		try:
			execute()
			self.assertEqual(
				frappe.db.get_value("Webstore Product", product.name, "primary_store"), DEFAULT_SLUG
			)
			self.assertEqual(frappe.db.get_value("Webstore Cart", cart.name, "webstore"), DEFAULT_SLUG)
			self.assertEqual(
				frappe.db.get_value("Webstore Wishlist", wish.name, "webstore"), DEFAULT_SLUG
			)
		finally:
			frappe.db.delete("Webstore Product", {"name": product.name})
			frappe.db.delete("Webstore Cart", {"name": cart.name})
			frappe.db.delete("Webstore Wishlist", {"name": wish.name})

	def test_a_row_already_assigned_to_a_non_default_store_is_left_alone(self):
		make_webstore(DEFAULT_SLUG, title="Default")
		make_webstore("flowers", title="Flowers")
		cart = frappe.get_doc(
			{"doctype": "Webstore Cart", "user": BUYER, "status": "Open", "webstore": "flowers"}
		)
		cart.insert(ignore_permissions=True)
		try:
			execute()
			self.assertEqual(frappe.db.get_value("Webstore Cart", cart.name, "webstore"), "flowers")
		finally:
			frappe.db.delete("Webstore Cart", {"name": cart.name})

	def test_idempotent(self):
		make_webstore(DEFAULT_SLUG, title="Default")
		execute()
		execute()  # must not raise on a second run

	def test_stamps_an_existing_quotation_once_the_custom_field_exists(self):
		make_webstore(DEFAULT_SLUG, title="Default")
		clear_store_cache()

		from upande_webstore.api import cart, checkout

		frappe.set_user(BUYER)
		cart.add_item("WS-PATCH-QUOTE-ITEM", 1)
		result = checkout.place_order(po_reference="PO-PATCH-STAMP")
		frappe.set_user("Administrator")

		# stand in for a pre-Task-2 quotation: blank out what checkout's own
		# stamp would already have set, so the patch is what puts it back.
		frappe.db.set_value("Quotation", result["quotation"], "custom_webstore", "")

		execute()

		self.assertEqual(
			frappe.db.get_value("Quotation", result["quotation"], "custom_webstore"), DEFAULT_SLUG
		)


	def test_a_quotation_no_cart_ever_produced_is_left_alone(self):
		"""custom_webstore means "this order came from a shop". A blanket
		back-fill would stamp every quotation a sales rep ever raised in the
		desk and destroy that meaning on its very first migration.

		The desk quotation is built by copying the storefront's own — same
		company, currency and price list, so it is valid — and then simply
		never linked to a cart, which is the only thing that distinguishes
		the two.
		"""
		make_webstore(DEFAULT_SLUG, title="Default")
		clear_store_cache()

		from upande_webstore.api import cart, checkout

		frappe.set_user(BUYER)
		cart.add_item("WS-PATCH-QUOTE-ITEM", 1)
		result = checkout.place_order(po_reference="PO-PATCH-DESK")
		frappe.set_user("Administrator")

		from_store = result["quotation"]
		desk = frappe.copy_doc(frappe.get_doc("Quotation", from_store))
		desk.custom_webstore = ""
		desk.flags.ignore_permissions = True
		desk.insert()

		# both look like a pre-Task-2 document; only one came from a cart
		frappe.db.set_value("Quotation", from_store, "custom_webstore", "")

		execute()

		self.assertEqual(
			frappe.db.get_value("Quotation", from_store, "custom_webstore"),
			DEFAULT_SLUG,
			"the quotation a cart produced was not stamped",
		)
		self.assertFalse(
			frappe.db.get_value("Quotation", desk.name, "custom_webstore"),
			"a quotation raised in the desk was stamped as coming from a storefront",
		)
