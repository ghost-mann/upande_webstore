"""Every per-store field exists on both doctypes, and still means the same thing.

`Webstore`'s fields are generated from `Webstore Settings`' own definitions by
`scripts/generate_webstore_fields.py`. Generated once and committed, they can
go stale the moment someone edits the Single by hand in the desk or adds a
Select option to it — and a store's Checkout Mode silently offering a
different set of options than the site-wide one is the kind of bug nobody
finds until a shop is configured wrong.

So this asserts the two agree, and names the script in its failure message.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services.store_fields import (
	ALL_PER_STORE_FIELDS,
	PER_STORE_SCALARS,
	PER_STORE_TABLES,
	PER_STORE_TRISTATE,
)

REGENERATE = "run `python3 scripts/generate_webstore_fields.py` from the app root"


class TestStoreFieldParity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = frappe.get_meta("Webstore Settings")
		cls.webstore = frappe.get_meta("Webstore")

	def test_every_per_store_field_exists_on_webstore_settings(self):
		"""The registry names fields that must exist on the Single — it is the
		Single that a store overrides, so a name with no counterpart there
		would override nothing."""
		for fieldname in ALL_PER_STORE_FIELDS:
			with self.subTest(fieldname=fieldname):
				self.assertIsNotNone(
					self.settings.get_field(fieldname),
					f"{fieldname} is in store_fields.py but not on Webstore Settings",
				)

	def test_every_per_store_field_exists_on_webstore(self):
		for fieldname in ALL_PER_STORE_FIELDS:
			with self.subTest(fieldname=fieldname):
				self.assertIsNotNone(
					self.webstore.get_field(fieldname),
					f"{fieldname} is missing from the Webstore doctype — {REGENERATE}",
				)

	def test_scalars_and_tables_keep_their_type_and_options(self):
		"""A Link that points somewhere else, or a Select offering different
		options, is the same field in name only."""
		for fieldname in PER_STORE_SCALARS + PER_STORE_TABLES:
			with self.subTest(fieldname=fieldname):
				source = self.settings.get_field(fieldname)
				target = self.webstore.get_field(fieldname)
				self.assertEqual(
					target.fieldtype, source.fieldtype, f"{fieldname} fieldtype — {REGENERATE}"
				)
				self.assertEqual(
					target.options or "", source.options or "", f"{fieldname} options — {REGENERATE}"
				)

	def test_tristates_are_selects_over_a_checkbox_on_the_single(self):
		"""The one deliberate divergence: a Check on the Single becomes a
		three-state Select on the store, because a store must be able to say
		"off" as well as "inherit"."""
		for fieldname in PER_STORE_TRISTATE:
			with self.subTest(fieldname=fieldname):
				self.assertEqual(self.settings.get_field(fieldname).fieldtype, "Check")
				target = self.webstore.get_field(fieldname)
				self.assertEqual(target.fieldtype, "Select", f"{fieldname} — {REGENERATE}")
				self.assertEqual(target.options, "\nEnabled\nDisabled", f"{fieldname} — {REGENERATE}")

	def test_no_per_store_field_is_mandatory_on_a_store(self):
		"""Blank is how a store inherits, so a required override would force
		every store to restate the site default."""
		for fieldname in ALL_PER_STORE_FIELDS:
			with self.subTest(fieldname=fieldname):
				self.assertFalse(self.webstore.get_field(fieldname).reqd, fieldname)

	def test_the_form_is_organised_into_the_same_tabs_as_the_single(self):
		"""A store is configured on the same mental map as the site: same tabs,
		same order, same headings, minus what cannot differ per shop. The
		layout is derived from Webstore Settings' own field order rather than
		invented, so the two forms cannot drift into different shapes."""
		def tabs(meta):
			return [f.label for f in meta.fields if f.fieldtype == "Tab Break" and f.label]

		settings_tabs = tabs(self.settings)
		store_tabs = tabs(self.webstore)

		self.assertEqual(store_tabs[0], "Storefront", "the store's own identity comes first")
		inherited = store_tabs[1:]
		self.assertTrue(inherited, f"expected inherited tabs — {REGENERATE}")
		# every remaining tab exists on the Single, in the Single's own order
		self.assertEqual(
			inherited,
			[t for t in settings_tabs if t in inherited],
			f"tab order diverged from Webstore Settings — {REGENERATE}",
		)

	def test_no_tab_or_section_is_left_empty(self):
		"""Dropping the site-wide fields empties some sections — Roles, the
		portal feature flags — and an empty heading on a form is a dead end."""
		fields = list(self.webstore.fields)
		breaks = ("Tab Break", "Section Break", "Column Break")
		for index, field in enumerate(fields):
			if field.fieldtype not in breaks:
				continue
			wider = {
				"Column Break": breaks,
				"Section Break": ("Section Break", "Tab Break"),
				"Tab Break": ("Tab Break",),
			}[field.fieldtype]
			holds = False
			for later in fields[index + 1 :]:
				if later.fieldtype in wider:
					break
				if later.fieldtype not in breaks:
					holds = True
					break
			with self.subTest(fieldname=field.fieldname):
				self.assertTrue(holds, f"{field.fieldname} holds nothing — {REGENERATE}")

	def test_the_registry_has_no_duplicates(self):
		self.assertEqual(
			len(ALL_PER_STORE_FIELDS),
			len(set(ALL_PER_STORE_FIELDS)),
			"a field is listed twice in store_fields.py",
		)

	def test_the_shared_portal_features_are_not_per_store(self):
		"""One account and one order history across every shop — a portal page
		switched off for one storefront and not the other would describe a
		customer experience that does not exist."""
		from upande_webstore.theme.features import FEATURES

		portal_flags = [f.fieldname for f in FEATURES if f.group == "portal"]
		self.assertTrue(portal_flags)  # sanity: the registry is not empty
		for fieldname in portal_flags:
			with self.subTest(fieldname=fieldname):
				self.assertNotIn(fieldname, ALL_PER_STORE_FIELDS)
				self.assertIsNone(self.webstore.get_field(fieldname))

	def test_every_storefront_feature_is_per_store(self):
		"""The other half of the same rule: anything a visitor to one shop can
		see must be switchable for that shop alone."""
		from upande_webstore.theme.features import FEATURES

		for feature in FEATURES:
			if feature.group != "storefront":
				continue
			with self.subTest(fieldname=feature.fieldname):
				self.assertIn(feature.fieldname, PER_STORE_TRISTATE)

	def test_every_theme_seed_is_per_store(self):
		"""Two shops that cannot differ in colour are not two shops."""
		from upande_webstore.theme.tokens import THEME_FIELDS

		for fieldname in THEME_FIELDS:
			with self.subTest(fieldname=fieldname):
				self.assertIn(fieldname, ALL_PER_STORE_FIELDS)

	def test_every_branding_string_is_per_store(self):
		from upande_webstore.theme.branding import DEFAULTS

		for fieldname in DEFAULTS:
			with self.subTest(fieldname=fieldname):
				self.assertIn(fieldname, ALL_PER_STORE_FIELDS)

	def test_the_ledger_facing_defaults_stay_site_wide(self):
		"""A storefront is a presentation and pricing layer, never a second set
		of books — these belong to the company, not to a shop."""
		for fieldname in (
			"company",
			"default_customer_group",
			"default_territory",
			"quotation_validity_days",
			"notification_emails",
			"catalogue_manager_roles",
			"order_manager_roles",
			"portal_manager_roles",
		):
			with self.subTest(fieldname=fieldname):
				self.assertNotIn(fieldname, ALL_PER_STORE_FIELDS)
				self.assertIsNone(self.webstore.get_field(fieldname))
