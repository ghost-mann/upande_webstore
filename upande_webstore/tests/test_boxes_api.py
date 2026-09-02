"""Desk box endpoints.

Deliberately not in `api/cart.py`: those are wrapped in `@guard("cart")`, so a
farm with the cart feature off could not open Webstore Settings.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	drop_box_type_doctype,
	make_box_type,
	make_item_price,
	make_portal_user,
	make_test_product,
	setup_webstore_settings,
)


class TestBoxesApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	@classmethod
	def tearDownClass(cls):
		drop_box_type_doctype()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		drop_box_type_doctype()

	def test_list_box_types_returns_plain_names(self):
		from upande_webstore.api.boxes import list_box_types

		make_box_type("Xpol", 350)
		make_box_type("Standard", 400)
		self.assertEqual(sorted(list_box_types()), ["Standard", "Xpol"])

	def test_describe_source_names_the_doctype_and_splits_usable_from_not(self):
		from upande_webstore.api.boxes import describe_source

		make_box_type("Xpol", 350)
		make_box_type("Unrated", 0)
		result = describe_source()
		self.assertEqual(result["doctype"], "Box Type")
		self.assertIn("Box Type", result["label"])
		self.assertEqual([b["box_type"] for b in result["usable"]], ["Xpol"])
		self.assertEqual([b["box_type"] for b in result["unusable"]], ["Unrated"])

	def test_describe_source_is_honest_when_there_is_no_source(self):
		"""A farm with neither representation must be told so, not shown
		an empty list that reads like a loading failure."""
		from upande_webstore.api.boxes import describe_source
		from unittest.mock import patch

		with patch("upande_webstore.services.packing._item_has_box_fields", return_value=False):
			from upande_webstore.services.packing import clear_box_source_cache

			clear_box_source_cache()
			result = describe_source()
		clear_box_source_cache()
		self.assertIsNone(result["doctype"])
		self.assertEqual(result["usable"], [])

	def test_describe_source_reports_a_field_mismatch_with_its_row_count(self):
		"""`custom_box_type` still links to `Item` (the shipped test-site shape);
		once a Box Type source resolves that is a mismatch checkout cannot write
		through, and a row already holding a value must be counted, not ignored."""
		from upande_webstore.api.boxes import describe_source

		make_test_product("WS-FM-ITEM")
		make_item_price("WS-FM-ITEM", "Standard Selling", 10)
		_, customer = make_portal_user("fm.buyer@example.com", "FM Buyer")
		# other test modules that ran earlier on this site may leave committed
		# Quotation Item rows behind, so the count that matters is the increase
		# this test causes, not an assumed absolute value.
		baseline = frappe.db.count("Quotation Item", filters=[["custom_box_type", "!=", ""]])
		quotation = frappe.get_doc({
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": customer,
			"company": frappe.defaults.get_global_default("company"),
			"selling_price_list": "Standard Selling",
			"items": [
				{
					"item_code": "WS-FM-ITEM",
					"qty": 1,
					"rate": 10,
					"custom_box_type": "WS-FM-ITEM",
				}
			],
		})
		quotation.flags.ignore_permissions = True
		quotation.insert()
		try:
			make_box_type("Xpol", 350)
			result = describe_source()
		finally:
			frappe.delete_doc("Quotation", quotation.name, force=1, ignore_permissions=True)

		mismatch = next(
			m for m in result["field_mismatches"] if m["doctype"] == "Quotation Item"
		)
		self.assertEqual(mismatch["targets"], "Item")
		self.assertEqual(mismatch["source"], "Box Type")
		self.assertEqual(mismatch["rows"], baseline + 1)

	def test_describe_source_field_mismatches_is_empty_when_the_field_agrees(self):
		from upande_webstore.api.boxes import describe_source

		# no Box Type doctype: the source resolves to Item, which is exactly
		# where the shipped test-site's custom_box_type already points.
		result = describe_source()
		self.assertEqual(result["field_mismatches"], [])

	def test_a_website_user_cannot_read_the_desk_endpoints(self):
		"""Customer has no read on Item or Box Type, so the dynamic permission
		check must keep them out just as the old hardcoded one did — this is
		what proves the guard was replaced, not removed."""
		from upande_webstore.api.boxes import list_box_types
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("box.reader@example.com", "Box Reader Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				list_box_types()
		finally:
			frappe.set_user("Administrator")

	def test_sales_manager_can_list_box_types(self):
		"""Regression for the reported bug: Webstore Product grants Sales
		Manager read/write/create/delete, and its form calls list_box_types on
		every refresh (webstore_product.js:5) — but the old
		frappe.only_for("System Manager") blocked a Sales Manager outright, no
		matter what the box source doctype's own DocPerms said.

		Granting Sales Manager read on the resolved source here is exactly what
		an admin would do in the desk — no code change — and must be enough.
		"""
		from upande_webstore.api.boxes import list_box_types
		from upande_webstore.services.packing import get_box_source
		from upande_webstore.tests.utils import make_desk_user

		make_box_type("Xpol", 350)
		source_doctype = get_box_source().doctype
		frappe.permissions.add_permission(source_doctype, "Sales Manager", 0, "read")
		email = make_desk_user("box.sales.manager@example.com", ["Sales Manager"])
		frappe.set_user(email)
		try:
			self.assertEqual(list_box_types(), ["Xpol"])
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
			frappe.permissions.reset_perms(source_doctype)

	def test_a_website_user_cannot_read_describe_source(self):
		"""describe_source renders the Webstore Settings panel, so it must
		refuse anyone without read on Webstore Settings — Customer is not
		granted it."""
		from upande_webstore.api.boxes import describe_source
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("box.describer@example.com", "Box Describer Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				describe_source()
		finally:
			frappe.set_user("Administrator")

	def test_list_box_types_with_no_source_returns_empty_without_a_permission_question(self):
		"""No source doctype means there is nothing to check permission
		against — this must return [] rather than raise."""
		from upande_webstore.api.boxes import list_box_types
		from unittest.mock import patch

		from upande_webstore.services.packing import clear_box_source_cache

		with patch("upande_webstore.services.packing._item_has_box_fields", return_value=False):
			clear_box_source_cache()
			result = list_box_types()
		clear_box_source_cache()
		self.assertEqual(result, [])

	def test_the_settings_form_has_somewhere_to_render_the_summary(self):
		field = frappe.get_meta("Webstore Settings").get_field("box_source_summary")
		self.assertIsNotNone(field, "Webstore Settings has no box source panel")
		self.assertEqual(field.fieldtype, "HTML")

	def test_the_default_box_type_is_reported_so_the_panel_can_mark_it(self):
		from upande_webstore.api.boxes import describe_source

		make_box_type("Xpol", 350)
		settings = frappe.get_doc("Webstore Settings")
		settings.default_box_type = "Xpol"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		try:
			self.assertEqual(describe_source()["default_box_type"], "Xpol")
		finally:
			settings.default_box_type = ""
			settings.save(ignore_permissions=True)
			frappe.clear_cache()
