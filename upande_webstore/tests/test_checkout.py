import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)



class TestCheckoutModeDependencies(IntegrationTestCase):
	"""A setting must not be able to leave a buyer with no way to check out."""

	def tearDown(self):
		setup_webstore_settings()

	def test_sales_order_only_switches_direct_ordering_back_on(self):
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_direct_order = 0
		settings.checkout_mode = "Sales order only"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self.assertEqual(
			int(frappe.get_doc("Webstore Settings").enable_direct_order),
			1,
			"Sales order only with direct ordering off renders no checkout button at all",
		)


class TestCheckout(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CHK-ITEM")
		make_item_price("WS-CHK-ITEM", "Standard Selling", 75)
		make_portal_user("checkout.user@example.com", "Checkout Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "checkout.user@example.com"})
		set_stock("WS-CHK-ITEM", 10)
		frappe.set_user("checkout.user@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_place_order_creates_submitted_quotation(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHK-ITEM", 3)
		result = checkout.place_order(po_reference="PO-123", notes="Deliver Tuesday")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(quotation.docstatus, 1)
		self.assertEqual(quotation.party_name, "Checkout Buyer")
		self.assertEqual(quotation.items[0].item_code, "WS-CHK-ITEM")
		self.assertEqual(quotation.items[0].qty, 3)
		self.assertEqual(quotation.items[0].rate, 75)
		self.assertEqual(str(quotation.valid_till), add_days(nowdate(), 14))
		self.assertEqual(quotation.customer_po_reference, "PO-123")
		self.assertEqual(quotation.webstore_notes, "Deliver Tuesday")
		cart_doc = frappe.get_all(
			"Webstore Cart",
			{"user": "checkout.user@example.com"},
			["status", "quotation"],
		)[0]
		self.assertEqual(cart_doc.status, "Ordered")
		self.assertEqual(cart_doc.quotation, quotation.name)

	def test_empty_cart_rejected(self):
		from upande_webstore.api import checkout

		self.assertRaises(frappe.ValidationError, checkout.place_order)

	def test_stock_revalidated_at_checkout(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHK-ITEM", 3)
		frappe.set_user("Administrator")
		set_stock("WS-CHK-ITEM", 1)
		frappe.set_user("checkout.user@example.com")
		with self.assertRaises(frappe.ValidationError) as ctx:
			checkout.place_order()
		self.assertIn("no longer available", str(ctx.exception))

	def test_quotation_is_still_the_default_mode(self):
		"""Callers that pass no mode must keep getting a Quotation."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CHK-ITEM", 1)
		result = checkout.place_order()
		self.assertEqual(result["doctype"], "Quotation")
		self.assertIn("quotation", result)


class TestDirectOrder(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-SO-ITEM")
		make_item_price("WS-SO-ITEM", "Standard Selling", 40)
		make_portal_user("direct.buyer@example.com", "Direct Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": "direct.buyer@example.com"})
		set_stock("WS-SO-ITEM", 20)
		frappe.set_user("direct.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_creates_draft_sales_order_of_type_shopping_cart(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 4)
		result = checkout.place_order(po_reference="PO-CREATE", notes="Gate 3", mode="order")

		self.assertEqual(result["doctype"], "Sales Order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(order.docstatus, 0, "must be left as a draft for the sales team")
		self.assertEqual(order.order_type, "Shopping Cart")
		self.assertEqual(order.customer, "Direct Buyer")
		self.assertEqual(order.items[0].item_code, "WS-SO-ITEM")
		self.assertEqual(order.items[0].qty, 4)
		self.assertEqual(order.items[0].rate, 40)

	def test_po_reference_and_notes_survive(self):
		"""Sales Order has no customer_po_reference field — the PO must land in
		the standard po_no, and the notes in the custom webstore_notes."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 1)
		result = checkout.place_order(po_reference="PO-NOTES", notes="Gate 3", mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(order.po_no, "PO-NOTES")
		self.assertEqual(order.webstore_notes, "Gate 3")

	def test_delivery_date_is_set(self):
		from frappe.utils import add_days, nowdate

		from upande_webstore.api import cart, checkout
		from upande_webstore.api.checkout import DEFAULT_DELIVERY_DAYS

		cart.add_item("WS-SO-ITEM", 1)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		expected = add_days(nowdate(), DEFAULT_DELIVERY_DAYS)
		self.assertEqual(str(order.delivery_date), expected)

	def test_cart_records_the_sales_order_not_a_quotation(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 2)
		result = checkout.place_order(mode="order")
		row = frappe.get_all(
			"Webstore Cart",
			{"user": "direct.buyer@example.com"},
			["status", "quotation", "sales_order"],
		)[0]
		self.assertEqual(row.status, "Ordered")
		self.assertEqual(row.sales_order, result["sales_order"])
		self.assertFalse(row.quotation)

	def test_stock_revalidated_for_direct_orders_too(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 5)
		frappe.set_user("Administrator")
		set_stock("WS-SO-ITEM", 1)
		frappe.set_user("direct.buyer@example.com")
		with self.assertRaises(frappe.ValidationError) as ctx:
			checkout.place_order(mode="order")
		self.assertIn("no longer available", str(ctx.exception))

	def test_unknown_mode_rejected(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 1)
		with self.assertRaises(frappe.ValidationError):
			checkout.place_order(mode="invoice")

	def test_blocked_when_direct_ordering_disabled(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 1)
		frappe.set_user("Administrator")
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_direct_order = 0
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		frappe.set_user("direct.buyer@example.com")
		with self.assertRaises(frappe.PermissionError):
			checkout.place_order(mode="order")

	def test_duplicate_po_reference_is_rejected(self):
		"""ERPNext refuses a second Sales Order against the same customer PO
		number, which usefully stops a customer double-ordering. Pinned here so
		the behaviour is visible rather than surprising."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 1)
		checkout.place_order(po_reference="PO-DUPLICATE", mode="order")

		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "direct.buyer@example.com"})
		frappe.set_user("direct.buyer@example.com")
		cart.add_item("WS-SO-ITEM", 1)
		with self.assertRaises(frappe.ValidationError):
			checkout.place_order(po_reference="PO-DUPLICATE", mode="order")

	def test_blank_po_reference_allows_repeat_orders(self):
		"""Most customers do not supply a PO, and they must still be able to
		order more than once."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SO-ITEM", 1)
		first = checkout.place_order(mode="order")

		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "direct.buyer@example.com"})
		frappe.set_user("direct.buyer@example.com")
		cart.add_item("WS-SO-ITEM", 1)
		second = checkout.place_order(mode="order")
		self.assertNotEqual(first["sales_order"], second["sales_order"])

	def test_draft_order_is_visible_to_the_customer_who_placed_it(self):
		"""A draft Sales Order the customer created must appear in their portal —
		otherwise their own order is invisible until the team submits it."""
		from upande_webstore.api import cart, checkout
		from upande_webstore.services.portal import get_customer_docs

		cart.add_item("WS-SO-ITEM", 1)
		result = checkout.place_order(mode="order")
		names = [
			row.name
			for row in get_customer_docs(
				"Sales Order", ["name"], "customer", filters={"docstatus": ["<", 2]}, limit=50
			)
		]
		self.assertIn(result["sales_order"], names)


class TestCheckoutShippingDetails(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-SHIP-ITEM")
		make_item_price("WS-SHIP-ITEM", "Standard Selling", 25)
		make_portal_user("ship.buyer@example.com", "Shipping Details Ltd")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "ship.buyer@example.com"})
		set_stock("WS-SHIP-ITEM", 40)
		frappe.set_user("ship.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_quotation_stores_shipping_date_and_dropoff(self):
		from upande_webstore.api import cart, checkout

		# beyond default_lead_days (7), which is now enforced server-side
		when = add_days(nowdate(), 8)
		cart.add_item("WS-SHIP-ITEM", 2)
		result = checkout.place_order(shipping_date=when, dropoff_points="Gate 3\nDepot B")
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertEqual(str(quotation.webstore_shipping_date), when)
		self.assertIn("Gate 3", quotation.webstore_dropoff_points)

	def test_sales_order_uses_shipping_date_as_delivery_date(self):
		"""ERPNext plans and picks against delivery_date, so the customer's
		requested date has to land there rather than in a side field."""
		from upande_webstore.api import cart, checkout

		when = add_days(nowdate(), 9)
		cart.add_item("WS-SHIP-ITEM", 1)
		result = checkout.place_order(mode="order", shipping_date=when, dropoff_points="Cold room")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(str(order.delivery_date), when)
		self.assertEqual(str(order.items[0].delivery_date), when)
		self.assertEqual(order.webstore_dropoff_points, "Cold room")

	def test_sales_order_falls_back_when_no_date_given(self):
		from upande_webstore.api import cart, checkout
		from upande_webstore.api.checkout import DEFAULT_DELIVERY_DAYS

		cart.add_item("WS-SHIP-ITEM", 1)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(str(order.delivery_date), add_days(nowdate(), DEFAULT_DELIVERY_DAYS))

	def test_both_are_optional(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-SHIP-ITEM", 1)
		result = checkout.place_order()
		quotation = frappe.get_doc("Quotation", result["quotation"])
		self.assertFalse(quotation.webstore_shipping_date)
		self.assertFalse(quotation.webstore_dropoff_points)


class TestCheckoutModeSetting(IntegrationTestCase):
	"""checkout_mode narrows which button the cart page offers, but the button
	is only presentation — place_order re-checks the setting itself, so a
	client posting a mode the farm has switched off is still refused."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-MODE-ITEM")
		make_item_price("WS-MODE-ITEM", "Standard Selling", 20)
		make_portal_user("mode.buyer@example.com", "Mode Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "mode.buyer@example.com"})
		set_stock("WS-MODE-ITEM", 20)
		frappe.set_user("mode.buyer@example.com")

	def tearDown(self):
		# Reset on every path, including an assertion failure, or a mode set
		# by one test narrows checkout for whichever test runs next.
		frappe.set_user("Administrator")
		setup_webstore_settings()

	def _set_checkout_mode(self, mode):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "checkout_mode", mode)
		frappe.clear_cache()
		frappe.set_user("mode.buyer@example.com")

	def _fresh_cart(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "mode.buyer@example.com"})
		frappe.set_user("mode.buyer@example.com")

	def test_blank_checkout_mode_behaves_as_buyer_chooses(self):
		"""An existing site that has never set checkout_mode must keep
		offering both — exactly as before this setting existed."""
		from upande_webstore.api import cart, checkout

		self._set_checkout_mode("")
		cart.add_item("WS-MODE-ITEM", 1)
		self.assertEqual(checkout.place_order()["doctype"], "Quotation")

		self._fresh_cart()
		cart.add_item("WS-MODE-ITEM", 1)
		self.assertEqual(checkout.place_order(mode="order")["doctype"], "Sales Order")

	def test_both_succeed_under_buyer_chooses(self):
		from upande_webstore.api import cart, checkout

		self._set_checkout_mode("Buyer chooses")
		cart.add_item("WS-MODE-ITEM", 1)
		self.assertEqual(checkout.place_order()["doctype"], "Quotation")

		self._fresh_cart()
		cart.add_item("WS-MODE-ITEM", 1)
		self.assertEqual(checkout.place_order(mode="order")["doctype"], "Sales Order")

	def test_order_is_refused_when_quotation_only(self):
		from upande_webstore.api import cart, checkout

		self._set_checkout_mode("Quotation only")
		cart.add_item("WS-MODE-ITEM", 1)
		self.assertRaises(frappe.ValidationError, checkout.place_order, mode="order")

	def test_quotation_is_refused_when_sales_order_only(self):
		from upande_webstore.api import cart, checkout

		self._set_checkout_mode("Sales order only")
		cart.add_item("WS-MODE-ITEM", 1)
		self.assertRaises(frappe.ValidationError, checkout.place_order, mode="quotation")
