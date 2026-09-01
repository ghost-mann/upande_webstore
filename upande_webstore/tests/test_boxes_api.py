"""Desk box endpoints.

Deliberately not in `api/cart.py`: those are wrapped in `@guard("cart")`, so a
farm with the cart feature off could not open Webstore Settings.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	drop_box_type_doctype,
	make_box_type,
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

	def test_a_website_user_cannot_read_the_desk_endpoints(self):
		from upande_webstore.api.boxes import list_box_types
		from upande_webstore.tests.utils import make_portal_user

		email, _customer = make_portal_user("box.reader@example.com", "Box Reader Ltd")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				list_box_types()
		finally:
			frappe.set_user("Administrator")
