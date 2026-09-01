"""The installer creates what a site lacks and touches nothing it already has.

Karen Roses runs `Sales Order Item.custom_box_type` as a Link to its own `Box
Type` doctype with 5,019 values on it, and keeps `custom_number_of_boxes` and
`Quotation Item.custom_pack_rate` editable where we ship them read-only.
`create_custom_fields` updates every changed property of an existing field, so
shipping our definitions unguarded would rewrite all three.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

FIELD = {"dt": "Sales Order Item", "fieldname": "custom_box_type"}

# enough of a Custom Field to rebuild one of ours exactly as shipped
RESTORABLE = (
	"dt",
	"fieldname",
	"label",
	"fieldtype",
	"options",
	"insert_after",
	"read_only",
	"description",
	"default",
	"search_index",
)


class TestInstallFieldConflicts(IntegrationTestCase):
	def setUp(self):
		self.existing = frappe.db.get_value("Custom Field", FIELD, "name")
		self.original = (
			frappe.db.get_value("Custom Field", self.existing, ["fieldtype", "options"], as_dict=True)
			if self.existing
			else None
		)
		self.created = False

	def tearDown(self):
		# frappe.db.commit() below breaks the per-test savepoint rollback, so this
		# is the only safety net: put a pre-existing field back exactly as it
		# was, or delete one this test created itself. Skipping either branch
		# leaves a bogus custom_box_type -> Item Group field in the database for
		# every later test module.
		if self.created:
			frappe.delete_doc("Custom Field", self.existing, force=1, ignore_permissions=True)
		elif self.existing and self.original:
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
			self.created = True
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

	def test_a_field_the_site_models_differently_is_reported_not_ensured(self):
		from upande_webstore.setup.install import _only_missing, _resolved_fields

		self._point_field_elsewhere()
		missing, notable = _only_missing(_resolved_fields())
		self.assertTrue(
			any("custom_box_type" in line and "Item Group" in line for line in notable),
			"the log does not name the target the site actually uses",
		)
		self.assertNotIn(
			"custom_box_type", [df["fieldname"] for df in missing.get("Sales Order Item", [])]
		)


class TestInstallerIsCreateOnly(IntegrationTestCase):
	"""A field that already exists is left entirely alone, not just left pointing
	where it points. `create_custom_fields` would otherwise rewrite read_only,
	label, description and the rest on a field another app owns."""

	def test_an_existing_field_keeps_the_properties_the_site_gave_it(self):
		from upande_webstore.setup.install import create_webstore_custom_fields

		# Karen Roses' Quotation Item.custom_pack_rate is read_only 0; we ship 1.
		# Flipping it would take the field away from staff who edit it today.
		name = frappe.db.get_value(
			"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_pack_rate"}, "name"
		)
		self.assertTrue(name, "this site has no Quotation Item.custom_pack_rate to test with")
		original = frappe.db.get_value("Custom Field", name, "read_only")
		frappe.db.set_value("Custom Field", name, "read_only", 0)
		frappe.clear_cache(doctype="Quotation Item")
		frappe.db.commit()
		try:
			create_webstore_custom_fields()
			self.assertEqual(
				int(frappe.db.get_value("Custom Field", name, "read_only") or 0),
				0,
				"the installer flipped read_only on a field the site owns",
			)
		finally:
			frappe.db.set_value("Custom Field", name, "read_only", original)
			frappe.clear_cache(doctype="Quotation Item")
			frappe.db.commit()

	def test_a_field_matching_our_definition_is_skipped_without_noise(self):
		"""Skipped, but not reported: a steady-state site skips every field on
		every migrate, and logging that would bury the one entry that matters."""
		from upande_webstore.setup.install import WEBSTORE_CUSTOM_FIELDS, _only_missing

		missing, notable = _only_missing({"Item": WEBSTORE_CUSTOM_FIELDS["Item"]})
		self.assertEqual(missing, {}, "an existing field must never be re-ensured")
		self.assertEqual(notable, [])

	def test_a_field_the_site_lacks_is_created(self):
		from upande_webstore.setup.install import _only_missing

		missing, notable = _only_missing(
			{
				"Item": [
					{
						"fieldname": "custom_ws_absent_probe",
						"fieldtype": "Data",
						"label": "Absent Probe",
						"insert_after": "stock_uom",
					}
				]
			}
		)
		self.assertEqual([df["fieldname"] for df in missing["Item"]], ["custom_ws_absent_probe"])
		self.assertEqual(notable, [])


class TestBoxTypeLinkTarget(IntegrationTestCase):
	"""A `custom_box_type` we create must Link to whichever doctype this site
	keeps box types in — `Item` on Mona, `Box Type` on Karen Roses. A hardcoded
	`Item` is how a Box Type site ends up with a quotation field checkout can
	never write to, while the pack rate and box count land anyway."""

	def setUp(self):
		self.name = frappe.db.get_value(
			"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_box_type"}, "name"
		)
		self.original = (
			frappe.db.get_value("Custom Field", self.name, RESTORABLE, as_dict=True)
			if self.name
			else None
		)
		self.replaced = False

	def tearDown(self):
		"""Restore before dropping the fixture doctype, on every path.

		The field is deleted mid-test and recreated pointing at the fixture `Box
		Type`; leaving either state behind would give every later module a
		Quotation Item field linked to a doctype that no longer exists.
		"""
		from upande_webstore.tests.utils import drop_box_type_doctype

		if self.replaced:
			current = frappe.db.get_value(
				"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_box_type"}, "name"
			)
			if current:
				frappe.delete_doc("Custom Field", current, force=1, ignore_permissions=True)
			if self.original:
				frappe.get_doc(
					dict(
						{"doctype": "Custom Field"},
						**{k: v for k, v in self.original.items() if v is not None},
					)
				).insert(ignore_permissions=True)
		drop_box_type_doctype()
		frappe.clear_cache(doctype="Quotation Item")
		frappe.clear_cache()
		frappe.db.commit()

	def test_a_new_field_links_to_the_resolved_box_type_doctype(self):
		from upande_webstore.setup.install import create_webstore_custom_fields
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Xpol", 350)
		self.replaced = True
		if self.name:
			frappe.delete_doc("Custom Field", self.name, force=1, ignore_permissions=True)
			frappe.clear_cache(doctype="Quotation Item")

		create_webstore_custom_fields()

		created = frappe.db.get_value(
			"Custom Field",
			{"dt": "Quotation Item", "fieldname": "custom_box_type"},
			["fieldtype", "options"],
			as_dict=True,
		)
		self.assertTrue(created, "the installer did not create the missing field")
		self.assertEqual(created.fieldtype, "Link")
		self.assertEqual(
			created.options, "Box Type", "a Box Type site got a field linked to Item"
		)

	def test_the_shipped_definition_is_not_mutated_by_resolution(self):
		from upande_webstore.setup.install import WEBSTORE_CUSTOM_FIELDS, _resolved_fields
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Xpol", 350)
		resolved = next(
			df
			for df in _resolved_fields()["Sales Order Item"]
			if df["fieldname"] == "custom_box_type"
		)
		self.assertEqual(resolved["options"], "Box Type")
		shipped = next(
			df
			for df in WEBSTORE_CUSTOM_FIELDS["Sales Order Item"]
			if df["fieldname"] == "custom_box_type"
		)
		self.assertNotIn("options", shipped, "resolution wrote back into the shipped dict")

	def test_no_box_source_means_no_box_type_field_at_all(self):
		"""Nothing to Link to, and packing is inert anyway. The plain-number
		fields are still created: they cost nothing on a site that never fills
		them, and they are what ops reads where another app already writes them.
		"""
		from upande_webstore.setup.install import _resolved_fields

		with patch("upande_webstore.services.packing.get_box_source", return_value=None):
			resolved = _resolved_fields()
		for doctype in ("Quotation Item", "Sales Order Item"):
			names = [df["fieldname"] for df in resolved[doctype]]
			self.assertNotIn("custom_box_type", names, doctype)
			self.assertIn("custom_pack_rate", names, doctype)
			self.assertIn("custom_number_of_boxes", names, doctype)


class TestBoxTypeFieldRepoint(IntegrationTestCase):
	"""The one place create-only bends: a `custom_box_type` this app created
	itself, still empty, gets repointed if the resolved box source moves out
	from under it after creation. A populated one is left untouched exactly
	like every other existing field.

	`Sales Order Item` is used here rather than `Quotation Item`: this site's
	`Quotation Item.custom_box_type` already carries data from other tests'
	fixtures, while `Sales Order Item`'s does not — which is exactly the
	"nothing to orphan" precondition the repoint pass requires.
	"""

	DT = "Sales Order Item"

	def setUp(self):
		frappe.set_user("Administrator")
		self.name = frappe.db.get_value(
			"Custom Field", {"dt": self.DT, "fieldname": "custom_box_type"}, "name"
		)
		self.assertTrue(self.name, "this site has no Sales Order Item.custom_box_type to test with")
		self.original_options = frappe.db.get_value("Custom Field", self.name, "options")
		baseline_rows = frappe.db.count(self.DT, filters=[["custom_box_type", "!=", ""]])
		self.assertEqual(
			baseline_rows, 0, "this site already has custom_box_type data on Sales Order Item"
		)
		from upande_webstore.tests.utils import drop_box_type_doctype

		drop_box_type_doctype()

	def tearDown(self):
		# create_webstore_custom_fields is exercised directly (not mocked), so a
		# real repoint here really writes the Custom Field row; restoring it on
		# every path, assertion failures included, is the only thing standing
		# between this test and every later module inheriting a Sales Order
		# Item field pointed at the wrong doctype.
		from upande_webstore.services.packing import clear_box_source_cache
		from upande_webstore.tests.utils import drop_box_type_doctype

		frappe.db.set_value("Custom Field", self.name, "options", self.original_options)
		# clears whichever row a test set, without deleting the row itself —
		# these are real Sales Order Item lines, only the probe column is ours.
		frappe.db.sql(f"update `tab{self.DT}` set custom_box_type=NULL where custom_box_type != ''")
		drop_box_type_doctype()
		frappe.clear_cache(doctype=self.DT)
		clear_box_source_cache()
		frappe.db.commit()

	def test_an_empty_mismatched_field_is_repointed(self):
		from upande_webstore.setup.install import create_webstore_custom_fields
		from upande_webstore.tests.utils import make_box_type

		make_box_type("Xpol", 350)  # flips the resolved source to Box Type
		create_webstore_custom_fields()
		self.assertEqual(
			frappe.db.get_value("Custom Field", self.name, "options"),
			"Box Type",
			"an empty stale custom_box_type was not repointed to the new source",
		)

	def test_a_populated_mismatched_field_is_not_repointed(self):
		from upande_webstore.setup.install import create_webstore_custom_fields
		from upande_webstore.tests.utils import make_box_type

		row_name = frappe.db.get_value(self.DT, {}, "name")
		self.assertTrue(row_name, "no Sales Order Item row exists to mark as populated")
		frappe.db.set_value(self.DT, row_name, "custom_box_type", "does-not-matter")

		make_box_type("Xpol", 350)
		create_webstore_custom_fields()

		self.assertEqual(
			frappe.db.get_value("Custom Field", self.name, "options"),
			"Item",
			"a populated custom_box_type was repointed despite holding data",
		)

	def test_a_field_already_matching_the_source_is_untouched(self):
		"""No Box Type source resolves here, so custom_box_type already Links to
		Item — the same as what packing.get_box_source() resolves. Nothing
		should change, and nothing should need to."""
		from upande_webstore.setup.install import create_webstore_custom_fields

		create_webstore_custom_fields()
		self.assertEqual(frappe.db.get_value("Custom Field", self.name, "options"), "Item")
		self.assertEqual(
			frappe.db.count(self.DT, filters=[["custom_box_type", "!=", ""]]),
			0,
			"an untouched field must not gain data as a side effect",
		)
