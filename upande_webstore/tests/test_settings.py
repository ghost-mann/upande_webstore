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
