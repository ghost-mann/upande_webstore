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

	def test_get_attributes_survives_item_permission_enforcement(self):
		"""get_attributes is guest-reachable (@frappe.whitelist(allow_guest=True))
		and every template product's own page calls it directly
		(webstore_product.py's get_context) -- it must never need to load the
		Item document to answer "what sizes does this come in". Unlike
		services.pricing.get_item_price (see test_pricing.py), there is no
		legitimate reason for this call to touch Item permission-checked at
		all, flagged or not, so the fakes below raise for Item
		unconditionally -- narrower than the flag-aware simulation pricing
		needs, and correctly so.
		"""
		from upande_webstore.api.variants import get_attributes

		real_get_cached_doc = frappe.get_cached_doc
		real_get_cached_value = frappe.get_cached_value

		def fake_get_cached_doc(doctype, *args, **kwargs):
			if doctype == "Item":
				raise frappe.PermissionError("No permission for Item")
			return real_get_cached_doc(doctype, *args, **kwargs)

		def fake_get_cached_value(doctype, *args, **kwargs):
			if doctype == "Item":
				raise frappe.PermissionError("No permission for Item")
			return real_get_cached_value(doctype, *args, **kwargs)

		frappe.get_cached_doc = fake_get_cached_doc
		frappe.get_cached_value = fake_get_cached_value
		try:
			frappe.set_user("Guest")
			attrs = get_attributes("WS-VAR-SHIRT")
		finally:
			frappe.get_cached_doc = real_get_cached_doc
			frappe.get_cached_value = real_get_cached_value
			frappe.set_user("Administrator")
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
