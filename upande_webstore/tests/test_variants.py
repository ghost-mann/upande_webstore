import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_test_product,
	make_variant_template,
	set_stock,
	setup_webstore_settings,
)


class TestVariants(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_variant_template("WS-VAR-SHIRT")
		make_test_product("WS-VAR-SHIRT", web_title="Variant Shirt")
		make_item_price("WS-VAR-SHIRT-S", "Standard Selling", 30)
		set_stock("WS-VAR-SHIRT-S", 4)

	def test_get_attributes(self):
		from upande_webstore.api.variants import get_attributes

		attrs = get_attributes("WS-VAR-SHIRT")
		self.assertEqual(attrs[0]["attribute"], "WS Size")
		self.assertIn("S", attrs[0]["values"])

	def test_resolve_variant(self):
		from upande_webstore.api.variants import resolve_variant

		result = resolve_variant("WS-VAR-SHIRT", {"WS Size": "S"})
		self.assertEqual(result["item_code"], "WS-VAR-SHIRT-S")
		self.assertEqual(result["price"]["rate"], 30)
		self.assertTrue(result["stock"]["in_stock"])

	def test_resolve_missing_combination(self):
		from upande_webstore.api.variants import resolve_variant

		result = resolve_variant("WS-VAR-SHIRT", {"WS Size": "L"})
		self.assertIsNone(result["item_code"])
