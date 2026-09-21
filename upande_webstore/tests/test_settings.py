import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import setup_webstore_settings


class TestWebstoreSettings(IntegrationTestCase):
	def test_settings_roundtrip(self):
		settings = setup_webstore_settings()
		self.assertEqual(settings.quotation_validity_days, 14)
		from upande_webstore.services.settings import get_settings

		cached = get_settings()
		self.assertEqual(cached.guest_price_list, "Standard Selling")
		self.assertTrue(cached.warehouses)


class TestAppearance(IntegrationTestCase):
	def test_derive_brand_colors(self):
		from upande_webstore.services.settings import derive_brand_colors

		colors = derive_brand_colors("#166534")
		self.assertEqual(colors["primary"], "#166534")
		self.assertEqual(colors["primary_hover"], "#13592e")
		self.assertEqual(colors["primary_soft"], "#ecf3ef")
		self.assertEqual(colors["primary_light"], "#508c67")
		self.assertEqual(colors["primary_deep"], "#104c27")
		self.assertEqual(colors["ring"], "rgba(22, 101, 52, 0.35)")

	def test_derive_brand_colors_rejects_invalid(self):
		from upande_webstore.services.settings import derive_brand_colors

		for bad in (None, "", "#1f0", "green", "#16653g"):
			self.assertEqual(derive_brand_colors(bad), {})

	def test_get_appearance_defaults(self):
		setup_webstore_settings()
		from upande_webstore.services.settings import get_appearance

		appearance = get_appearance()
		self.assertIsNone(appearance["hero_image"])
		self.assertIsNone(appearance["brand_logo"])
		self.assertEqual(appearance["colors"], {})

	def test_get_appearance_with_values(self):
		settings = setup_webstore_settings()
		settings.hero_image = "/files/custom-hero.jpg"
		settings.primary_color = "#1e3a64"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		from upande_webstore.services.settings import get_appearance

		appearance = get_appearance()
		self.assertEqual(appearance["hero_image"], "/files/custom-hero.jpg")
		self.assertEqual(appearance["colors"]["primary"], "#1e3a64")
		self.assertIn("primary_hover", appearance["colors"])

	def test_update_website_context(self):
		setup_webstore_settings()
		from upande_webstore.services.settings import update_website_context

		context = frappe._dict()
		update_website_context(context)
		self.assertIn("colors", context.webstore_appearance)


class TestSettingsDocstatus(IntegrationTestCase):
	"""Both of this app's Singles, not just Webstore Settings.

	The repair used to name one doctype, so Webstore Portal Settings kept a
	stray docstatus of 2 indefinitely — the desk then rendered it as a
	cancelled document and offered Amend instead of Save, on a doctype that is
	not submittable at all. tabSingles is column storage that persists, so once
	the 2 is written, loading the doc reads it back and the next save rewrites
	it: nothing has to keep re-setting it for it to survive every migrate.
	"""

	def _stored(self, doctype):
		rows = frappe.db.sql(
			"select value from tabSingles where doctype = %s and field = 'docstatus'",
			doctype,
		)
		return str(rows[0][0]) if rows else None

	def _set_cancelled(self, doctype):
		frappe.db.sql(
			"update tabSingles set value = '2' where doctype = %s and field = 'docstatus'",
			doctype,
		)

	def test_neither_doctype_is_submittable(self):
		"""No submit workflow exists, so the desk must never offer Submit,
		Cancel or Amend on either form."""
		from upande_webstore.setup.install import NON_SUBMITTABLE_SINGLES

		for doctype in NON_SUBMITTABLE_SINGLES:
			self.assertFalse(
				frappe.get_meta(doctype).get("is_submittable"), f"{doctype} is submittable"
			)

	def test_repair_resets_a_cancelled_docstatus_on_every_single(self):
		from upande_webstore.setup.install import (
			NON_SUBMITTABLE_SINGLES,
			normalise_settings_docstatus,
		)

		stored = [dt for dt in NON_SUBMITTABLE_SINGLES if self._stored(dt) is not None]
		if not stored:
			self.skipTest("no docstatus rows stored for these Singles")
		for doctype in stored:
			self._set_cancelled(doctype)

		normalise_settings_docstatus()

		for doctype in stored:
			self.assertEqual(self._stored(doctype), "0", f"{doctype} still cancelled")

	def test_portal_settings_is_repaired_too(self):
		"""The regression this fixes: the repair named only Webstore Settings."""
		from upande_webstore.setup.install import normalise_settings_docstatus

		if self._stored("Webstore Portal Settings") is None:
			self.skipTest("no docstatus row stored for Webstore Portal Settings")
		self._set_cancelled("Webstore Portal Settings")

		normalise_settings_docstatus()

		self.assertEqual(self._stored("Webstore Portal Settings"), "0")

	def test_repair_is_a_noop_when_already_clean(self):
		from upande_webstore.setup.install import (
			NON_SUBMITTABLE_SINGLES,
			normalise_settings_docstatus,
		)

		normalise_settings_docstatus()
		normalise_settings_docstatus()
		for doctype in NON_SUBMITTABLE_SINGLES:
			self.assertIn(self._stored(doctype), ("0", None))

	def test_the_shipped_patch_still_repairs(self):
		"""patches.txt already ran on existing sites; after_migrate is what
		carries the fix to them, but the patch entry must not break."""
		from upande_webstore.patches.reset_webstore_settings_docstatus import execute

		execute()
		self.assertIn(self._stored("Webstore Settings"), ("0", None))

	def test_saving_settings_keeps_docstatus_zero(self):
		setup_webstore_settings()
		self.assertIn(self._stored("Webstore Settings"), ("0", None))


class TestCategoryImageMigration(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def _set_legacy(self, **images):
		for field, value in images.items():
			frappe.db.set_single_value("Webstore Settings", field, value)
		frappe.clear_cache()

	def test_migrates_legacy_images_into_cards(self):
		from upande_webstore.patches.move_category_images_to_table import execute

		self._set_legacy(
			flowers_category_image="/files/f.jpg", coffee_category_image="/files/c.jpg"
		)
		execute()

		cards = frappe.get_doc("Webstore Settings").category_cards
		self.assertEqual([card.label for card in cards], ["Flowers", "Coffee", "Fresh Produce"])
		self.assertEqual(cards[0].image, "/files/f.jpg")
		self.assertEqual(cards[1].image, "/files/c.jpg")
		self.assertFalse(cards[2].image)
		self.assertEqual(cards[0].category, "Flowers")
		self.assertEqual(cards[2].category, "Fresh Produce")
		# the subtitles the template used to hardcode must survive
		self.assertEqual(cards[0].subtitle, "Roses, lilies & fillers")

	def test_is_idempotent(self):
		from upande_webstore.patches.move_category_images_to_table import execute

		self._set_legacy(flowers_category_image="/files/f.jpg")
		execute()
		execute()
		self.assertEqual(len(frappe.get_doc("Webstore Settings").category_cards), 3)

	def test_noop_when_no_legacy_images(self):
		"""A site that never uploaded category images must not gain cards."""
		from upande_webstore.patches.move_category_images_to_table import execute

		self._set_legacy(
			flowers_category_image="", coffee_category_image="", produce_category_image=""
		)
		execute()
		self.assertEqual(frappe.get_doc("Webstore Settings").category_cards, [])

	def test_migrates_legacy_images_with_no_company_or_guest_price_list(self):
		"""This patch runs on every migrate, including a site whose general
		settings were never filled in yet; it writes only category_cards, so
		it must not be blocked by mandatory fields it has nothing to do with."""
		from upande_webstore.patches.move_category_images_to_table import execute

		settings = frappe.get_doc("Webstore Settings")
		settings.flags.ignore_mandatory = True
		settings.company = ""
		settings.guest_price_list = ""
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

		self._set_legacy(flowers_category_image="/files/f.jpg")
		execute()

		cards = frappe.get_doc("Webstore Settings").category_cards
		self.assertEqual([card.label for card in cards], ["Flowers", "Coffee", "Fresh Produce"])

	def test_leaves_existing_cards_alone(self):
		from upande_webstore.patches.move_category_images_to_table import execute

		settings = frappe.get_doc("Webstore Settings")
		settings.append("category_cards", {"label": "Roses", "category": "Roses"})
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		self._set_legacy(flowers_category_image="/files/f.jpg")

		execute()

		cards = frappe.get_doc("Webstore Settings").category_cards
		self.assertEqual([card.label for card in cards], ["Roses"])
