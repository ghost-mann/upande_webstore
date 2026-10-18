"""A product published as a template is ordered as one of its variants: the
product page resolves the chosen length to e.g. Athena-40cm and puts that in
the basket. Every rose on Mona Flowers is published this way."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	make_variant_template,
	set_stock,
	setup_webstore_settings,
)

TEMPLATE = "WS-CARTVAR-T"
USER = "cartvar.user@example.com"


class TestCartAcceptsVariantsOfPublishedTemplates(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_variant_template(TEMPLATE)
		make_test_product(TEMPLATE)
		for size in ("S", "M"):
			make_item_price(f"{TEMPLATE}-{size}", "Standard Selling", 12)
			set_stock(f"{TEMPLATE}-{size}", 100)
		make_portal_user(USER)

	def setUp(self):
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": USER})

	def test_variant_of_a_published_template_can_be_added(self):
		from upande_webstore.api import cart

		result = cart.add_item(f"{TEMPLATE}-S", 5)
		self.assertEqual(result["count"], 5)
		self.assertEqual(result["items"][0]["item_code"], f"{TEMPLATE}-S")
		self.assertEqual(result["items"][0]["rate"], 12)

	def test_variant_of_an_unpublished_template_is_refused(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		name = frappe.db.get_value("Webstore Product", {"item": TEMPLATE})
		frappe.db.set_value("Webstore Product", name, "published", 0)
		frappe.set_user(USER)
		try:
			with self.assertRaises(frappe.ValidationError):
				cart.add_item(f"{TEMPLATE}-M", 1)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Webstore Product", name, "published", 1)

	def test_disabled_variant_is_refused(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		frappe.db.set_value("Item", f"{TEMPLATE}-M", "disabled", 1)
		frappe.set_user(USER)
		try:
			with self.assertRaises(frappe.ValidationError):
				cart.add_item(f"{TEMPLATE}-M", 1)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Item", f"{TEMPLATE}-M", "disabled", 0)

	def test_the_template_itself_is_not_orderable(self):
		"""A template has no stock or price of its own; the length must be chosen."""
		from upande_webstore.api import cart

		with self.assertRaises(frappe.ValidationError):
			cart.add_item(TEMPLATE, 1)

	def test_variant_ships_in_its_templates_box(self):
		from upande_webstore.services.packing import get_product_box_type
		from upande_webstore.services.catalog import product_for_item

		frappe.set_user("Administrator")
		self.assertEqual(product_for_item(f"{TEMPLATE}-S"), frappe.db.get_value("Webstore Product", {"item": TEMPLATE}))
		# with no box anywhere both fall back the same way
		self.assertEqual(get_product_box_type(f"{TEMPLATE}-S"), get_product_box_type(TEMPLATE))
