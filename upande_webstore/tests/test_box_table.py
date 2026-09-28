"""The Boxes table on Webstore Settings: the portable way to list boxes.

When it has rows it is the only thing buyers pick from; when it is empty the
site's own box records are used exactly as before.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.test_cart_boxes import make_box_item
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)

BUYER = "boxtable.buyer@example.com"


def set_boxes(rows, default=None, packing=1, minimum=0):
	settings = frappe.get_doc("Webstore Settings")
	settings.set("boxes", rows)
	settings.enable_box_packing = packing
	settings.default_box_type = default
	settings.minimum_order_stems = minimum
	settings.save(ignore_permissions=True)
	frappe.clear_cache()


class TestBoxTable(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		# a site-side box record, so there is something for the table to shadow
		cls.site_box = make_box_item("WS-BT-SITEBOX", 300)
		make_test_product("WS-BT-ROSE")
		make_item_price("WS-BT-ROSE", "Standard Selling", 10)
		make_portal_user(BUYER, "Box Table Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		frappe.db.delete("Webstore Cart", {"user": BUYER})
		set_stock("WS-BT-ROSE", 20000)

	def tearDown(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()

	def test_an_empty_table_leaves_the_site_source_in_charge(self):
		from upande_webstore.services import packing

		set_boxes([])
		self.assertEqual(packing.get_box_source().kind, "records")
		self.assertIn(self.site_box, [box["box_type"] for box in packing.get_box_types()])

	def test_a_filled_table_is_the_only_list_buyers_see(self):
		from upande_webstore.services import packing

		set_boxes(
			[
				{"box_name": "Tall", "pack_rate": 400},
				{"box_name": "Half", "pack_rate": 200},
			]
		)
		boxes = packing.get_box_types()
		# table order, not alphabetical
		self.assertEqual([box["box_name"] for box in boxes], ["Tall", "Half"])
		self.assertNotIn(self.site_box, [box["box_type"] for box in boxes])
		self.assertEqual(packing.get_pack_rate("Tall"), 400)
		self.assertEqual(packing.box_label("Tall"), "Tall")

	def test_a_disabled_row_is_hidden_and_reported(self):
		from upande_webstore.services import packing

		set_boxes([{"box_name": "Tall", "pack_rate": 400}, {"box_name": "Old", "pack_rate": 250, "disabled": 1}])
		self.assertEqual([box["box_name"] for box in packing.get_box_types()], ["Tall"])
		self.assertEqual(packing.get_pack_rate("Old"), 0)
		self.assertEqual(
			[box["box_name"] for box in packing.get_unusable_box_types()], ["Old"]
		)

	def test_the_site_record_mapping_is_what_documents_get(self):
		from upande_webstore.services import packing

		set_boxes(
			[
				{"box_name": "Tall", "pack_rate": 300, "box_type": self.site_box},
				{"box_name": "Unmapped", "pack_rate": 200},
			]
		)
		self.assertEqual(packing.box_record("Tall"), self.site_box)
		self.assertIsNone(packing.box_record("Unmapped"))

	def test_a_box_listed_twice_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			set_boxes([{"box_name": "Tall", "pack_rate": 400}, {"box_name": "Tall", "pack_rate": 300}])

	def test_a_box_with_no_stems_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			set_boxes([{"box_name": "Tall", "pack_rate": 0}])

	def test_the_default_must_be_an_enabled_table_box_in_the_same_save(self):
		# adding the table and choosing its default in one save must work
		set_boxes([{"box_name": "Tall", "pack_rate": 400}], default="Tall")
		self.assertEqual(frappe.db.get_single_value("Webstore Settings", "default_box_type"), "Tall")
		with self.assertRaises(frappe.ValidationError):
			set_boxes([{"box_name": "Tall", "pack_rate": 400}], default="Nope")

	def test_packing_stays_inert_while_the_module_is_off(self):
		from upande_webstore.services import packing

		set_boxes([{"box_name": "Tall", "pack_rate": 400}], default="Tall", packing=0)
		self.assertFalse(packing.packing_enabled())

	def test_a_cart_line_takes_the_default_table_box_and_is_summarised(self):
		from upande_webstore.api import cart

		set_boxes(
			[{"box_name": "Tall", "pack_rate": 400}, {"box_name": "Half", "pack_rate": 200}],
			default="Tall",
		)
		frappe.set_user(BUYER)
		result = cart.add_item("WS-BT-ROSE", 800)
		self.assertEqual(result["items"][0]["box_type"], "Tall")
		self.assertEqual(result["items"][0]["number_of_boxes"], 2)
		group = result["boxes"]["groups"][0]
		self.assertEqual((group["box_name"], group["boxes"], group["is_full"]), ("Tall", 2, True))
		self.assertEqual(result["boxes"]["total_boxes"], 2)

		result = cart.set_box_type("WS-BT-ROSE", "Half")
		self.assertEqual(result["items"][0]["number_of_boxes"], 4)

	def test_checkout_writes_the_mapped_site_record_only(self):
		from upande_webstore.api import cart, checkout

		set_boxes(
			[
				{"box_name": "Tall", "pack_rate": 400, "box_type": self.site_box},
				{"box_name": "Unmapped", "pack_rate": 400},
			],
			default="Tall",
		)
		frappe.set_user(BUYER)
		cart.add_item("WS-BT-ROSE", 400)
		quotation = checkout.place_order()["quotation"]
		frappe.set_user("Administrator")
		line = frappe.get_doc("Quotation", quotation).items[0]
		if frappe.get_meta("Quotation Item").get_field("custom_box_type"):
			self.assertEqual(line.custom_box_type, self.site_box)

		frappe.set_user(BUYER)
		cart.add_item("WS-BT-ROSE", 400)
		cart.set_box_type("WS-BT-ROSE", "Unmapped")
		quotation = checkout.place_order()["quotation"]
		frappe.set_user("Administrator")
		line = frappe.get_doc("Quotation", quotation).items[0]
		# no site record to link, so no box detail rather than a broken Link
		self.assertFalse(line.get("custom_box_type"))
