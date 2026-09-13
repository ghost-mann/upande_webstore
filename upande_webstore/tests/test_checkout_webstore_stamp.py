"""Task 2: checkout stamps the resolved store onto the Quotation or Sales
Order it creates (`custom_webstore`) - the single most useful thing checkout
can tell the desk once one site can run more than one storefront.
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

USER = "checkout.webstore@example.com"


class TestCheckoutStampsWebstore(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		# The store comes first: the product belongs to the store checkout
		# runs in, since a product outside the current catalogue is not
		# addable to its cart.
		delete_all_webstores()
		make_webstore("flowers", title="Flowers")
		make_test_product("WS-CHKWS-ITEM", primary_store="flowers")
		make_item_price("WS-CHKWS-ITEM", "Standard Selling", 60)
		make_portal_user(USER, "Checkout Webstore Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": USER})
		set_stock("WS-CHKWS-ITEM", 10)
		# test_no_store_resolved_leaves_the_field_blank deletes every store to
		# make its point; put the class's own store back for whichever test
		# runs next rather than leaving the product pointing at nothing.
		if not frappe.db.exists("Webstore", "flowers"):
			make_webstore("flowers", title="Flowers")
		frappe.local.webstore_slug = "flowers"
		clear_store_cache()
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": USER})
		clear_store_cache()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug

	def test_place_order_stamps_the_resolved_store_on_the_quotation(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHKWS-ITEM", 2)
		result = checkout.place_order(po_reference="PO-WS-1")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(quotation.custom_webstore, "flowers")

	def test_direct_order_stamps_the_resolved_store_on_the_sales_order(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHKWS-ITEM", 1)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(order.custom_webstore, "flowers")

	def test_no_store_resolved_leaves_the_field_blank(self):
		"""No `Webstore` rows at all: checkout must still place the order,
		just without a store to stamp."""
		from upande_webstore.api import cart, checkout

		delete_all_webstores()
		if hasattr(frappe.local, "webstore_slug"):
			del frappe.local.webstore_slug
		clear_store_cache()

		cart.add_item("WS-CHKWS-ITEM", 1)
		result = checkout.place_order(po_reference="PO-WS-2")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertFalse(quotation.custom_webstore)
