"""Multi-currency guest pricing: the guest_price_lists table, cookie
resolution, validation, the storefront picker payload, and the cart
consequences of switching currency mid-basket.

See docs/superpowers/specs/2026-09-02-multi-currency-guest-pricing-design.md.
"""

import frappe
from frappe.auth import CookieManager
from frappe.tests import IntegrationTestCase

from upande_webstore.services.pricing import GUEST_PRICE_LIST_COOKIE
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_price_list,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


def _with_cookie(value):
	"""Simulate an incoming request carrying GUEST_PRICE_LIST_COOKIE=value.

	No real HTTP request exists inside an IntegrationTestCase, so
	frappe.local.request / .cookie_manager are absent entirely (see
	services.pricing._cookie_price_list / _remember_price_list, which check
	for exactly that). This stands in for both, the same objects frappe's own
	request handling installs, just built by hand.
	"""
	frappe.local.request = frappe._dict(cookies={GUEST_PRICE_LIST_COOKIE: value} if value else {})
	frappe.local.cookie_manager = CookieManager()


def _clear_request():
	for attr in ("request", "cookie_manager", "webstore_guest_price_list_override"):
		if hasattr(frappe.local, attr):
			delattr(frappe.local, attr)


def _append_row(settings, price_list, label=None, is_default=0):
	settings.append(
		"guest_price_lists", {"price_list": price_list, "label": label, "is_default": is_default}
	)


class TestGuestCurrencyResolution(IntegrationTestCase):
	"""services.pricing.get_price_list's resolution order."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_price_list("Webstore EUR", currency="EUR")
		make_price_list("Webstore GBP", currency="GBP")
		make_portal_user("currency.customer@example.com", "Currency Customer Ltd", price_list="Webstore GBP")

	def setUp(self):
		self.settings = setup_webstore_settings()

	def tearDown(self):
		frappe.set_user("Administrator")
		_clear_request()

	def test_empty_table_falls_back_to_guest_price_list(self):
		"""Inert path: deploying the feature with nothing configured must
		change nothing about today's behaviour."""
		from upande_webstore.services.pricing import get_price_list

		self.assertEqual(self.settings.guest_price_lists, [])
		self.assertEqual(get_price_list(user="Guest"), "Standard Selling")

	def test_single_row_used_with_no_cookie(self):
		from upande_webstore.services.pricing import get_price_list

		_append_row(self.settings, "Webstore EUR")
		self.settings.save(ignore_permissions=True)
		self.assertEqual(get_price_list(user="Guest"), "Webstore EUR")

	def test_default_row_beats_first_row(self):
		from upande_webstore.services.pricing import get_price_list

		_append_row(self.settings, "Webstore EUR")
		_append_row(self.settings, "Webstore GBP", is_default=1)
		self.settings.save(ignore_permissions=True)
		self.assertEqual(get_price_list(user="Guest"), "Webstore GBP")

	def test_first_row_used_when_no_default(self):
		from upande_webstore.services.pricing import get_price_list

		_append_row(self.settings, "Webstore EUR")
		_append_row(self.settings, "Webstore GBP")
		self.settings.save(ignore_permissions=True)
		self.assertEqual(get_price_list(user="Guest"), "Webstore EUR")

	def test_cookie_beats_default_row(self):
		from upande_webstore.services.pricing import get_price_list

		_append_row(self.settings, "Webstore EUR", is_default=1)
		_append_row(self.settings, "Webstore GBP")
		self.settings.save(ignore_permissions=True)
		_with_cookie("Webstore GBP")
		self.assertEqual(get_price_list(user="Guest"), "Webstore GBP")

	def test_customer_default_beats_cookie(self):
		"""A logged-in visitor's negotiated price list always wins, whatever
		cookie a stale browser tab still carries."""
		from upande_webstore.services.pricing import get_price_list

		_append_row(self.settings, "Webstore EUR", is_default=1)
		self.settings.save(ignore_permissions=True)
		_with_cookie("Webstore EUR")
		self.assertEqual(
			get_price_list(user="currency.customer@example.com"), "Webstore GBP"
		)


class TestGuestCurrencyCookieSecurity(IntegrationTestCase):
	"""The security case: a cookie naming a price list the farm never
	offered must never be trusted, whatever the value looks like."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_price_list("Webstore EUR", currency="EUR")
		make_price_list("Unpublished B2B", currency="GBP", selling=1, enabled=1)

	def setUp(self):
		self.settings = setup_webstore_settings()

	def tearDown(self):
		frappe.set_user("Administrator")
		_clear_request()

	def test_cookie_naming_a_price_list_outside_the_table_is_ignored(self):
		"""A visitor who hand-sets the cookie to a real, valid price list the
		farm simply never added to guest_price_lists must not be able to read
		its pricing — only rows in the configured table are ever offered."""
		from upande_webstore.services.pricing import get_price_list

		_append_row(self.settings, "Webstore EUR", is_default=1)
		self.settings.save(ignore_permissions=True)

		_with_cookie("Unpublished B2B")
		self.assertEqual(get_price_list(user="Guest"), "Webstore EUR")

	def test_invalid_cookie_is_overwritten_with_the_resolved_default(self):
		from upande_webstore.services.pricing import get_price_list

		_append_row(self.settings, "Webstore EUR", is_default=1)
		self.settings.save(ignore_permissions=True)

		_with_cookie("does-not-exist-at-all")
		get_price_list(user="Guest")
		self.assertEqual(
			frappe.local.cookie_manager.cookies[GUEST_PRICE_LIST_COOKIE]["value"], "Webstore EUR"
		)


class TestGuestCurrencyValidation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_price_list("Webstore EUR", currency="EUR")
		make_price_list("Webstore GBP", currency="GBP")
		make_price_list("Webstore Buying Only", currency="USD", selling=0)
		make_price_list("Webstore Disabled", currency="USD", enabled=0)

	def setUp(self):
		self.settings = setup_webstore_settings()

	def test_a_buying_only_price_list_is_refused(self):
		_append_row(self.settings, "Webstore Buying Only")
		self.assertRaises(frappe.ValidationError, self.settings.save, ignore_permissions=True)

	def test_a_disabled_price_list_is_refused(self):
		_append_row(self.settings, "Webstore Disabled")
		self.assertRaises(frappe.ValidationError, self.settings.save, ignore_permissions=True)

	def test_two_rows_sharing_a_currency_are_refused(self):
		make_price_list("Webstore EUR Alt", currency="EUR")
		_append_row(self.settings, "Webstore EUR")
		_append_row(self.settings, "Webstore EUR Alt")
		self.assertRaises(frappe.ValidationError, self.settings.save, ignore_permissions=True)

	def test_two_defaults_are_refused(self):
		_append_row(self.settings, "Webstore EUR", is_default=1)
		_append_row(self.settings, "Webstore GBP", is_default=1)
		self.assertRaises(frappe.ValidationError, self.settings.save, ignore_permissions=True)

	def test_one_of_each_is_accepted(self):
		_append_row(self.settings, "Webstore EUR", is_default=1)
		_append_row(self.settings, "Webstore GBP")
		self.settings.save(ignore_permissions=True)
		self.assertEqual(len(self.settings.guest_price_lists), 2)


class TestGuestCurrencyPicker(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_price_list("Webstore EUR", currency="EUR")
		make_price_list("Webstore GBP", currency="GBP")
		make_portal_user("picker.customer@example.com", "Picker Customer Ltd", price_list="Webstore GBP")
		make_portal_user("picker.guest@example.com", "Picker Guest Ltd")

	def setUp(self):
		self.settings = setup_webstore_settings()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_no_picker_when_table_is_empty(self):
		from upande_webstore.services.pricing import get_guest_currency_picker

		self.assertIsNone(get_guest_currency_picker(user="Guest"))

	def test_no_picker_for_a_single_row(self):
		from upande_webstore.services.pricing import get_guest_currency_picker

		_append_row(self.settings, "Webstore EUR")
		self.settings.save(ignore_permissions=True)
		self.assertIsNone(get_guest_currency_picker(user="Guest"))

	def test_picker_renders_for_two_rows(self):
		from upande_webstore.services.pricing import get_guest_currency_picker

		_append_row(self.settings, "Webstore EUR", is_default=1)
		_append_row(self.settings, "Webstore GBP")
		self.settings.save(ignore_permissions=True)
		picker = get_guest_currency_picker(user="Guest")
		self.assertIsNotNone(picker)
		self.assertEqual({o["price_list"] for o in picker["options"]}, {"Webstore EUR", "Webstore GBP"})
		self.assertEqual(picker["current"], "Webstore EUR")

	def test_picker_hidden_for_a_customer_with_their_own_price_list(self):
		from upande_webstore.services.pricing import get_guest_currency_picker

		_append_row(self.settings, "Webstore EUR", is_default=1)
		_append_row(self.settings, "Webstore GBP")
		self.settings.save(ignore_permissions=True)
		self.assertIsNone(get_guest_currency_picker(user="picker.customer@example.com"))

	def test_picker_shown_for_a_logged_in_user_without_a_customer(self):
		"""No linked Customer falls through to the guest table exactly like a
		guest, so the picker must still offer them a real choice."""
		from upande_webstore.services.pricing import get_guest_currency_picker

		_append_row(self.settings, "Webstore EUR", is_default=1)
		_append_row(self.settings, "Webstore GBP")
		self.settings.save(ignore_permissions=True)
		self.assertIsNotNone(get_guest_currency_picker(user="picker.guest@example.com"))


class TestGuestCurrencyCartSwitch(IntegrationTestCase):
	"""The one case with real teeth: a logged-in user with no linked Customer
	can hold a cart, and switching currency must re-price it."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_price_list("Webstore EUR", currency="EUR")
		make_price_list("Webstore GBP", currency="GBP")
		make_test_product("WS-CURR-BOTH")
		make_item_price("WS-CURR-BOTH", "Webstore EUR", 40)
		make_item_price("WS-CURR-BOTH", "Webstore GBP", 35)
		make_test_product("WS-CURR-EUR-ONLY")
		make_item_price("WS-CURR-EUR-ONLY", "Webstore EUR", 15)
		make_portal_user("switcher@example.com")
		set_stock("WS-CURR-BOTH", 10)
		set_stock("WS-CURR-EUR-ONLY", 10)

	def setUp(self):
		self.settings = setup_webstore_settings()
		_append_row(self.settings, "Webstore EUR", is_default=1)
		_append_row(self.settings, "Webstore GBP")
		self.settings.save(ignore_permissions=True)
		frappe.set_user("switcher@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "switcher@example.com"})
		_clear_request()

	def test_switching_currency_reprices_the_open_cart(self):
		"""The cart tracks whatever get_item_price resolves right now, in
		whichever currency is current — not a hardcoded number, since
		ERPNext's own currency conversion between the price list and the
		company's default currency is free to apply and is not this
		feature's concern (see the spec's Non-goals)."""
		from upande_webstore.api import cart, pricing
		from upande_webstore.services.pricing import get_item_price

		frappe.local.request = frappe._dict(cookies={})
		frappe.local.cookie_manager = CookieManager()
		cart.add_item("WS-CURR-BOTH", 2)
		eur_rate = get_item_price("WS-CURR-BOTH", qty=2)["rate"]
		self.assertEqual(cart.get_cart()["items"][0]["rate"], eur_rate)
		self.assertEqual(cart.get_cart()["currency"], "EUR")

		pricing.set_price_list("Webstore GBP")

		result = cart.get_cart()
		self.assertEqual(result["currency"], "GBP")
		self.assertNotEqual(result["items"][0]["rate"], eur_rate)
		self.assertEqual(result["items"][0]["rate"], get_item_price("WS-CURR-BOTH", qty=2)["rate"])

	def test_an_item_unpriced_in_the_new_list_is_dropped_with_a_message(self):
		from upande_webstore.api import cart, pricing

		frappe.local.request = frappe._dict(cookies={})
		frappe.local.cookie_manager = CookieManager()
		cart.add_item("WS-CURR-BOTH", 1)
		cart.add_item("WS-CURR-EUR-ONLY", 1)

		result = pricing.set_price_list("Webstore GBP")

		self.assertIn("WS-CURR-EUR-ONLY", result["dropped"])
		remaining = [r["item_code"] for r in cart.get_cart()["items"]]
		self.assertEqual(remaining, ["WS-CURR-BOTH"])

	def test_the_setter_refuses_a_price_list_not_offered(self):
		from upande_webstore.api import pricing

		frappe.local.request = frappe._dict(cookies={})
		frappe.local.cookie_manager = CookieManager()
		self.assertRaises(frappe.ValidationError, pricing.set_price_list, "Standard Selling")
