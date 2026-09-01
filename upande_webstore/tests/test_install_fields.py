"""The installer must never repoint a custom field another app owns.

Karen Roses runs `Sales Order Item.custom_box_type` as a Link to its own `Box
Type` doctype with 5,019 values on it. `create_custom_fields` updates existing
fields rather than skipping them, so shipping our definition unguarded would
rewrite the link target and orphan all of them.
"""

import frappe
from frappe.tests import IntegrationTestCase

FIELD = {"dt": "Sales Order Item", "fieldname": "custom_box_type"}


class TestInstallFieldConflicts(IntegrationTestCase):
	def setUp(self):
		self.existing = frappe.db.get_value("Custom Field", FIELD, "name")
		self.original = (
			frappe.db.get_value("Custom Field", self.existing, ["fieldtype", "options"], as_dict=True)
			if self.existing
			else None
		)

	def tearDown(self):
		if self.existing and self.original:
			frappe.db.set_value(
				"Custom Field",
				self.existing,
				{"fieldtype": self.original.fieldtype, "options": self.original.options},
			)
		frappe.clear_cache(doctype="Sales Order Item")
		frappe.db.commit()

	def _point_field_elsewhere(self):
		"""Stand in for Karen Roses: the same fieldname, a different target.

		`Item Group` is used rather than `Box Type` so this test needs no
		fixture doctype — only that the target differs from the `Item` we ship.
		"""
		if self.existing:
			frappe.db.set_value(
				"Custom Field", self.existing, {"fieldtype": "Link", "options": "Item Group"}
			)
		else:
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": "Sales Order Item",
					"fieldname": "custom_box_type",
					"label": "Box Type",
					"fieldtype": "Link",
					"options": "Item Group",
					"insert_after": "qty",
				}
			).insert(ignore_permissions=True)
			self.existing = frappe.db.get_value("Custom Field", FIELD, "name")
		frappe.clear_cache(doctype="Sales Order Item")
		frappe.db.commit()

	def test_an_existing_field_with_another_link_target_is_left_alone(self):
		from upande_webstore.setup.install import create_webstore_custom_fields

		self._point_field_elsewhere()
		create_webstore_custom_fields()
		self.assertEqual(
			frappe.db.get_value("Custom Field", self.existing, "options"),
			"Item Group",
			"the installer repointed a field another app owns",
		)

	def test_conflicting_definitions_are_reported(self):
		from upande_webstore.setup.install import _without_conflicts, WEBSTORE_CUSTOM_FIELDS

		self._point_field_elsewhere()
		safe, skipped = _without_conflicts(WEBSTORE_CUSTOM_FIELDS)
		self.assertTrue(any("custom_box_type" in line for line in skipped))
		kept = [df["fieldname"] for df in safe.get("Sales Order Item", [])]
		self.assertNotIn("custom_box_type", kept)
		self.assertIn("custom_pack_rate", kept, "unrelated fields must still be ensured")

	def test_matching_definitions_are_still_ensured(self):
		from upande_webstore.setup.install import _without_conflicts, WEBSTORE_CUSTOM_FIELDS

		safe, skipped = _without_conflicts({"Item": WEBSTORE_CUSTOM_FIELDS["Item"]})
		self.assertEqual(skipped, [])
		self.assertEqual(len(safe["Item"]), 2)
