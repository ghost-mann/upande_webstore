"""A template's length picker offers only lengths a customer can buy.

The Stem Length attribute lists every grade a farm could cut (40 to 120cm),
but a variety is usually priced at only a few. Offering the rest led nowhere:
the customer chose 120cm and got no price.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import make_item_price, setup_webstore_settings

ATTRIBUTE = "WS VL Length"
VALUES = ("40cm", "50cm", "60cm", "70cm", "80cm")
PRICED = "WS-VL-PRICED"
UNPRICED = "WS-VL-UNPRICED"


def build_template(code, variant_values):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"has_variants": 1,
				"attributes": [{"attribute": ATTRIBUTE}],
			}
		).insert(ignore_permissions=True)

	from erpnext.controllers.item_variant import create_variant

	for value in variant_values:
		variant_code = f"{code}-{value}"
		if not frappe.db.exists("Item", variant_code):
			variant = create_variant(code, {ATTRIBUTE: value})
			variant.item_code = variant_code
			variant.insert(ignore_permissions=True)


def offered(template):
	from upande_webstore.api.variants import get_attributes

	return get_attributes(template)[0]["values"]


class TestVariantLengths(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
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
		# variants at 40-70cm; 80cm has no variant at all
		build_template(PRICED, ("40cm", "50cm", "60cm", "70cm"))
		make_item_price(f"{PRICED}-40cm", "Standard Selling", 0.30)
		make_item_price(f"{PRICED}-60cm", "Standard Selling", 0.40)
		make_item_price(f"{PRICED}-70cm", "Standard Selling", 0.50)
		frappe.db.set_value("Item", f"{PRICED}-70cm", "disabled", 1)
		build_template(UNPRICED, ("50cm", "60cm"))

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()

	def test_only_priced_lengths_are_offered(self):
		self.assertEqual(offered(PRICED), ["40cm", "60cm"])

	def test_guest_is_offered_the_same_lengths(self):
		frappe.set_user("Guest")
		try:
			self.assertEqual(offered(PRICED), ["40cm", "60cm"])
		finally:
			frappe.set_user("Administrator")

	def test_unpriced_template_offers_the_lengths_it_has(self):
		"""A site that prices by length on the template, or has not priced
		yet, must not lose its picker; it keeps the lengths that exist."""
		self.assertEqual(offered(UNPRICED), ["50cm", "60cm"])
