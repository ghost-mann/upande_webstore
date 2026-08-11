import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_item,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


def make_box_item(item_code, pack_rate):
	item = make_test_item(item_code, item_group="Products", is_stock_item=0)
	frappe.db.set_value(
		"Item", item.name, {"custom_is_box": 1, "custom_pack_rate": pack_rate}
	)
	frappe.clear_cache(doctype="Item")
	return item.name


def set_product_box(item_code, box_item):
	"""Point a product at the box it ships in."""
	name = frappe.db.get_value("Webstore Product", {"item": item_code})
	frappe.db.set_value("Webstore Product", name, "box_type", box_item)
	frappe.clear_cache(doctype="Webstore Product")


def enable_packing(default_box, minimum=0):
	"""Pin the packing config, column-by-column.

	Other modules — test_occasion in particular — save Webstore Settings as a
	whole document, which rewrites every column including these. Any test that
	clears caches or crosses a save boundary has to re-pin rather than assume
	setUp's values survived.
	"""
	frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
	frappe.db.set_single_value("Webstore Settings", "default_box_type", default_box)
	frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", minimum)
	frappe.clear_cache()


class TestCartBoxes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-BOX-ITEM")
		make_item_price("WS-BOX-ITEM", "Standard Selling", 10)
		make_portal_user("box.buyer@example.com", "Box Buyer")
		cls.zim = make_box_item("WS-BOX-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "box.buyer@example.com"})
		set_stock("WS-BOX-ITEM", 5000)
		enable_packing(self.zim)
		# Frappe does not roll these back between tests, so a product box set by
		# one test would otherwise decide the next one's arithmetic.
		set_product_box("WS-BOX-ITEM", None)
		if frappe.db.exists("Webstore Product", {"item": "WS-BOX-ITEM-2"}):
			set_product_box("WS-BOX-ITEM-2", None)
		frappe.set_user("box.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_line_takes_the_box_from_its_product(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		jumbo = make_box_item("WS-BOX-JUMBO2", 500)
		set_product_box("WS-BOX-ITEM", jumbo)
		frappe.set_user("box.buyer@example.com")
		result = cart.add_item("WS-BOX-ITEM", 1000)
		self.assertEqual(result["items"][0]["box_type"], jumbo)
		self.assertEqual(result["items"][0]["number_of_boxes"], 2)
		self.assertEqual(result["boxes"]["groups"][0]["pack_rate"], 500)

	def test_line_falls_back_to_the_farm_default(self):
		"""A product with no box of its own uses the farm default."""
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		set_product_box("WS-BOX-ITEM", None)
		frappe.set_user("box.buyer@example.com")
		result = cart.add_item("WS-BOX-ITEM", 600)
		self.assertEqual(result["items"][0]["box_type"], self.zim)
		self.assertEqual(result["items"][0]["number_of_boxes"], 2)

	def test_partial_line_reports_zero_boxes(self):
		"""A 50-stem line shares a box, so it has no whole-box count of its own;
		the cart total is what gets validated."""
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		set_product_box("WS-BOX-ITEM", None)
		frappe.set_user("box.buyer@example.com")
		result = cart.add_item("WS-BOX-ITEM", 50)
		self.assertEqual(result["items"][0]["number_of_boxes"], 0)
		self.assertFalse(result["boxes"]["packable"])

	def test_two_lines_together_fill_whole_boxes(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		make_test_product("WS-BOX-ITEM-2")
		make_item_price("WS-BOX-ITEM-2", "Standard Selling", 10)
		set_stock("WS-BOX-ITEM-2", 5000)
		set_product_box("WS-BOX-ITEM", None)
		frappe.set_user("box.buyer@example.com")
		cart.add_item("WS-BOX-ITEM", 50)
		result = cart.add_item("WS-BOX-ITEM-2", 250)
		self.assertEqual(result["boxes"]["total_stems"], 300)
		self.assertTrue(result["boxes"]["packable"])

	def test_packing_off_leaves_cart_untouched(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("box.buyer@example.com")
		result = cart.add_item("WS-BOX-ITEM", 1750)
		self.assertIsNone(result["boxes"])

	def test_zero_pack_rate_does_not_block(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		unrated = make_box_item("WS-BOX-NORATE", 0)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", unrated)
		frappe.clear_cache()
		set_product_box("WS-BOX-ITEM", unrated)
		frappe.set_user("box.buyer@example.com")
		result = cart.add_item("WS-BOX-ITEM", 1750)
		self.assertTrue(result["boxes"]["packable"])

	def test_disabled_product_box_falls_back_to_the_default(self):
		"""Disabling a box Item must not brick carts holding products that point
		at it."""
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		retired = make_box_item("WS-BOX-RETIRED", 400)
		set_product_box("WS-BOX-ITEM", retired)
		frappe.set_user("box.buyer@example.com")
		cart.add_item("WS-BOX-ITEM", 600)
		frappe.set_user("Administrator")
		frappe.db.set_value("Item", retired, "disabled", 1)
		frappe.clear_cache(doctype="Item")
		enable_packing(self.zim)
		frappe.set_user("box.buyer@example.com")
		result = cart.get_cart()
		self.assertEqual(result["items"][0]["box_type"], self.zim)
		self.assertEqual(result["items"][0]["number_of_boxes"], 2)

	def test_buyer_can_override_the_product_box(self):
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		jumbo = make_box_item("WS-BOX-OVERRIDE", 500)
		set_product_box("WS-BOX-ITEM", self.zim)
		frappe.set_user("box.buyer@example.com")
		cart.add_item("WS-BOX-ITEM", 1000)
		result = cart.set_box_type("WS-BOX-ITEM", jumbo)
		self.assertEqual(result["items"][0]["box_type"], jumbo)
		self.assertEqual(result["items"][0]["number_of_boxes"], 2)

	def test_override_survives_a_quantity_change(self):
		"""Recompute must not stamp the product's box back over the buyer's."""
		from upande_webstore.api import cart

		frappe.set_user("Administrator")
		jumbo = make_box_item("WS-BOX-KEEP", 500)
		set_product_box("WS-BOX-ITEM", self.zim)
		frappe.set_user("box.buyer@example.com")
		cart.add_item("WS-BOX-ITEM", 500)
		cart.set_box_type("WS-BOX-ITEM", jumbo)
		result = cart.update_qty("WS-BOX-ITEM", 1500)
		self.assertEqual(result["items"][0]["box_type"], jumbo)
		self.assertEqual(result["items"][0]["number_of_boxes"], 3)

	def test_product_rejects_an_item_that_is_not_a_box(self):
		"""Silently falling back to the default looks like the setting being
		ignored, so a bad pick is refused on save."""
		frappe.set_user("Administrator")
		name = frappe.db.get_value("Webstore Product", {"item": "WS-BOX-ITEM"})
		product = frappe.get_doc("Webstore Product", name)
		product.box_type = "WS-BOX-ITEM"  # a rose, not a box
		self.assertRaises(frappe.ValidationError, product.save)

	def test_get_box_types_excludes_unrated_boxes(self):
		from upande_webstore.services.packing import get_box_types

		frappe.set_user("Administrator")
		make_box_item("WS-BOX-HIDDEN", 0)
		codes = [row["item_code"] for row in get_box_types()]
		self.assertIn(self.zim, codes)
		self.assertNotIn("WS-BOX-HIDDEN", codes)
