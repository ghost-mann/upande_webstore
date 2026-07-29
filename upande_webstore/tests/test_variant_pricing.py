"""A template item has no price of its own.

Its whole range is variants, so a catalogue of templates showed no price at all
— only "Multiple options". These tests pin the range that replaced it.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_item_price, make_price_list, setup_webstore_settings

TEMPLATE = "WS-VP-TEMPLATE"
ATTRIBUTE = "WS VP Length"
VALUES = ("40cm", "70cm", "100cm")
RATES = {"40cm": 0.30, "70cm": 0.45, "100cm": 0.60}


def build_template():
	if not frappe.db.exists("Item Attribute", ATTRIBUTE):
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": ATTRIBUTE,
				"item_attribute_values": [
					{"attribute_value": v, "abbr": v.replace("cm", "")} for v in VALUES
				],
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Item", TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": TEMPLATE,
				"item_name": TEMPLATE,
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"has_variants": 1,
				"attributes": [{"attribute": ATTRIBUTE}],
			}
		).insert(ignore_permissions=True)

	from erpnext.controllers.item_variant import create_variant

	for value in VALUES:
		code = f"{TEMPLATE}-{value}"
		if not frappe.db.exists("Item", code):
			variant = create_variant(TEMPLATE, {ATTRIBUTE: value})
			variant.item_code = code
			variant.insert(ignore_permissions=True)
		make_item_price(code, "Standard Selling", RATES[value])


class TestVariantPriceRange(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		build_template()

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_range_spans_cheapest_to_dearest_variant(self):
		from upande_webstore.services.pricing import get_variant_price_range

		found = get_variant_price_range(TEMPLATE)
		self.assertEqual(found["min"], 0.30)
		self.assertEqual(found["max"], 0.60)
		self.assertEqual(found["variants"], len(VALUES))

	def test_guest_sees_the_range(self):
		"""The whole point: an anonymous visitor must see a price."""
		from upande_webstore.services.pricing import get_variant_price_range

		frappe.set_user("Guest")
		try:
			self.assertEqual(get_variant_price_range(TEMPLATE)["min"], 0.30)
		finally:
			frappe.set_user("Administrator")

	def test_a_price_without_the_selling_flag_still_counts(self):
		"""ERPNext sets `selling` from the price list, but an imported or scripted
		Item Price can arrive without it — filtering on it made templates look
		priceless."""
		from upande_webstore.services.pricing import get_variant_price_range

		frappe.db.sql(
			"update `tabItem Price` set selling = 0 where item_code like %s", f"{TEMPLATE}-%"
		)
		frappe.clear_cache()
		try:
			self.assertEqual(get_variant_price_range(TEMPLATE)["min"], 0.30)
		finally:
			frappe.db.sql(
				"update `tabItem Price` set selling = 1 where item_code like %s", f"{TEMPLATE}-%"
			)

	def test_falls_back_to_the_guest_list_when_the_customer_list_is_empty(self):
		"""A customer price list often covers only some items; the public price
		beats showing none."""
		from upande_webstore.services.pricing import get_variant_price_range

		empty = make_price_list("WS VP Empty List")
		settings = frappe.get_doc("Webstore Settings")
		settings.guest_price_list = "Standard Selling"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		found = get_variant_price_range(TEMPLATE, user=None)
		self.assertIsNotNone(found)
		self.assertEqual(found["price_list"], "Standard Selling")
		self.assertTrue(empty)

	def test_template_with_no_priced_variants_returns_nothing(self):
		from upande_webstore.services.pricing import get_variant_price_range

		frappe.db.sql("delete from `tabItem Price` where item_code like %s", f"{TEMPLATE}-%")
		frappe.clear_cache()
		try:
			self.assertIsNone(get_variant_price_range(TEMPLATE))
		finally:
			for value in VALUES:
				make_item_price(f"{TEMPLATE}-{value}", "Standard Selling", RATES[value])

	def test_non_template_returns_nothing(self):
		from upande_webstore.services.pricing import get_variant_price_range

		self.assertIsNone(get_variant_price_range(f"{TEMPLATE}-40cm"))

	def test_catalogue_exposes_the_range_on_the_listing(self):
		from upande_webstore.services.catalog import get_products
		from upande_webstore.tests.utils import make_test_product

		make_test_product(TEMPLATE, has_variants=1)
		frappe.clear_cache()
		listing = next(
			(p for p in get_products()["products"] if p["item"] == TEMPLATE), None
		)
		self.assertIsNotNone(listing, "template listing missing from the catalogue")
		self.assertTrue(listing["has_variants"])
		self.assertIsNone(listing["price"], "a template has no single price")
		self.assertEqual(listing["price_range"]["min"], 0.30)
