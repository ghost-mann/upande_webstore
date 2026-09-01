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


class TestCheckoutBoxes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CB-ITEM")
		make_item_price("WS-CB-ITEM", "Standard Selling", 10)
		make_portal_user("cb.buyer@example.com", "CB Buyer")
		cls.zim = make_box_item("WS-CB-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "cb.buyer@example.com"})
		set_stock("WS-CB-ITEM", 20000)
		# column writes only — see the note in test_cart_boxes.setUp
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 1000)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_partial_group_is_blocked(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 1750)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		self.assertIn("1500", str(caught.exception))
		self.assertIn("1800", str(caught.exception))

	def test_below_minimum_is_blocked(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 600)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		self.assertIn("1000", str(caught.exception))

	def test_both_problems_reported_together(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 550)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order()
		message = str(caught.exception)
		self.assertIn("whole boxes", message)
		self.assertIn("Minimum order", message)
		# singular/plural box counts read properly
		self.assertNotIn("(1 boxes)", message)

	def test_whole_boxes_above_minimum_passes(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-CB-ITEM", 1200)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])

	def test_inert_when_packing_disabled(self):
		from upande_webstore.api import cart, checkout

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")
		cart.add_item("WS-CB-ITEM", 1750)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])

	def test_inert_when_pack_rate_is_zero(self):
		"""Mona live's state today: seven box Items, every rate 0."""
		from upande_webstore.api import cart, checkout

		frappe.set_user("Administrator")
		unrated = make_box_item("WS-CB-NORATE", 0)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", unrated)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 0)
		frappe.clear_cache()
		frappe.set_user("cb.buyer@example.com")
		cart.add_item("WS-CB-ITEM", 1750)
		result = checkout.place_order()
		self.assertTrue(result["quotation"])


class TestBoxFieldMapping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-MAP-A")
		make_test_product("WS-MAP-B")
		make_item_price("WS-MAP-A", "Standard Selling", 10)
		make_item_price("WS-MAP-B", "Standard Selling", 10)
		make_portal_user("map.buyer@example.com", "Map Buyer")
		cls.zim = make_box_item("WS-MAP-ZIM", 300)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "map.buyer@example.com"})
		set_stock("WS-MAP-A", 20000)
		set_stock("WS-MAP-B", 20000)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 1)
		frappe.db.set_single_value("Webstore Settings", "default_box_type", self.zim)
		frappe.db.set_single_value("Webstore Settings", "minimum_order_stems", 0)
		frappe.clear_cache()
		# product boxes persist across tests in this framework; reset them
		from upande_webstore.tests.test_cart_boxes import set_product_box

		set_product_box("WS-MAP-A", None)
		set_product_box("WS-MAP-B", None)
		frappe.set_user("map.buyer@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_quotation_item_carries_box_fields(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 600)
		result = checkout.place_order()
		row = frappe.get_doc("Quotation", result["quotation"]).items[0]
		self.assertEqual(row.custom_box_type, self.zim)
		self.assertEqual(int(row.custom_pack_rate), 300)
		self.assertEqual(row.custom_number_of_boxes, 2)

	def test_partial_line_records_zero_boxes(self):
		"""A line inside a mixed box has no whole-box count of its own."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 50)
		cart.add_item("WS-MAP-B", 250)
		result = checkout.place_order()
		rows = frappe.get_doc("Quotation", result["quotation"]).items
		self.assertEqual([r.custom_number_of_boxes for r in rows], [0, 0])

	def test_sales_order_flags_mixed_boxes(self):
		"""50 + 250 share one ZIM box, so the desk needs to know."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 50)
		cart.add_item("WS-MAP-B", 250)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes), 1)

	def test_single_line_is_not_mixed(self):
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 300)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes or 0), 0)

	def test_product_box_lands_on_the_document(self):
		from upande_webstore.api import cart, checkout
		from upande_webstore.tests.test_cart_boxes import make_box_item, set_product_box

		frappe.set_user("Administrator")
		jumbo = make_box_item("WS-MAP-JUMBO", 500)
		set_product_box("WS-MAP-A", jumbo)
		frappe.set_user("map.buyer@example.com")
		cart.add_item("WS-MAP-A", 1000)
		result = checkout.place_order()
		row = frappe.get_doc("Quotation", result["quotation"]).items[0]
		self.assertEqual(row.custom_box_type, jumbo)
		self.assertEqual(int(row.custom_pack_rate), 500)
		self.assertEqual(row.custom_number_of_boxes, 2)

	def test_two_whole_box_lines_are_not_mixed(self):
		"""600 and 600 at 300/box each pack alone; nothing shares."""
		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 600)
		cart.add_item("WS-MAP-B", 600)
		result = checkout.place_order(mode="order")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(int(order.custom_has_mixed_boxes or 0), 0)

	def test_no_derived_box_detail_lands_without_the_box_type_itself(self):
		"""The order still places, but the line carries nothing at all.

		A pack rate and a box count with no box type name a box nobody can read
		back: ops sees "400 stems per box, 3 boxes" of *what*, and the quotation
		to sales order mapper carries the emptiness onward. On a Box Type farm
		this is the default path — `custom_box_type` links to `Box Type`, our
		definition says `Item`, so the box type is the one field that is skipped.
		"""
		from frappe.utils import flt

		from upande_webstore.api import cart, checkout

		field = frappe.db.get_value(
			"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_box_type"}, "name"
		)
		original = frappe.db.get_value("Custom Field", field, "options")
		frappe.db.set_value("Custom Field", field, "options", "Item Group")
		frappe.clear_cache(doctype="Quotation Item")
		try:
			cart.add_item("WS-MAP-A", 600)
			result = checkout.place_order(mode="quotation")
			row = frappe.get_doc("Quotation", result["quotation"]).items[0]
			self.assertFalse(row.get("custom_box_type"))
			self.assertFalse(flt(row.get("custom_pack_rate")), "a pack rate for an unnamed box")
			self.assertFalse(row.get("custom_number_of_boxes"), "a box count for an unnamed box")
		finally:
			frappe.db.set_value("Custom Field", field, "options", original)
			frappe.clear_cache(doctype="Quotation Item")
			frappe.db.commit()

	def test_a_derived_field_the_site_models_differently_is_not_written(self):
		"""The installer never touches a field the site already has, so a farm
		that models the box count as a Float keeps that shape — and we must not
		write an Int's worth of meaning into it. The box type still lands; only
		the count is skipped."""
		from frappe.utils import flt

		from upande_webstore.api import cart, checkout

		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Quotation Item", "fieldname": "custom_number_of_boxes"},
			"name",
		)
		original = frappe.db.get_value("Custom Field", field, "fieldtype")
		frappe.db.set_value("Custom Field", field, "fieldtype", "Float")
		frappe.clear_cache(doctype="Quotation Item")
		try:
			cart.add_item("WS-MAP-A", 600)
			result = checkout.place_order(mode="quotation")
			row = frappe.get_doc("Quotation", result["quotation"]).items[0]
			self.assertEqual(row.get("custom_box_type"), self.zim)
			self.assertTrue(flt(row.get("custom_pack_rate")) > 0)
			self.assertFalse(row.get("custom_number_of_boxes"))
		finally:
			frappe.db.set_value("Custom Field", field, "fieldtype", original)
			frappe.clear_cache(doctype="Quotation Item")
			frappe.db.commit()

	def test_a_box_that_stopped_resolving_before_checkout_is_not_written(self):
		"""Box types are master data another app hand-maintains — 12 rows on
		Karen Roses. One renamed or deleted between add-to-cart and checkout
		would otherwise be written verbatim into a Link and raise a raw
		LinkValidationError at the customer."""
		from frappe.utils import flt

		from upande_webstore.api import cart, checkout

		cart.add_item("WS-MAP-A", 600)
		frappe.set_user("Administrator")
		frappe.db.set_value("Item", self.zim, "custom_is_box", 0)
		frappe.clear_cache()
		frappe.set_user("map.buyer@example.com")
		try:
			result = checkout.place_order(mode="quotation")
			row = frappe.get_doc("Quotation", result["quotation"]).items[0]
			self.assertFalse(row.get("custom_box_type"), "a box that no longer resolves was written")
			self.assertFalse(flt(row.get("custom_pack_rate")))
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Item", self.zim, "custom_is_box", 1)
			frappe.clear_cache()
			frappe.db.commit()



class TestBoxFieldTargetMismatch(IntegrationTestCase):
	"""Karen Roses' `Sales Order Item.custom_box_type` links to its own `Box
	Type` doctype. Writing an Item code there would fail validation and corrupt
	a field ops reads, so we write nothing at all."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()

	def setUp(self):
		self.field = frappe.db.get_value(
			"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_box_type"}, "name"
		)
		self.original = frappe.db.get_value("Custom Field", self.field, "options")

	def tearDown(self):
		frappe.db.set_value("Custom Field", self.field, "options", self.original)
		frappe.clear_cache(doctype="Quotation Item")
		frappe.db.commit()

	def test_a_mismatched_target_is_skipped_not_written(self):
		from upande_webstore.api.checkout import _writable

		frappe.db.set_value("Custom Field", self.field, "options", "Item Group")
		frappe.clear_cache(doctype="Quotation Item")
		self.assertFalse(_writable("Quotation Item", "custom_box_type", "Item"))
		self.assertTrue(_writable("Quotation Item", "custom_pack_rate"))

	def test_a_matching_target_is_written(self):
		from upande_webstore.api.checkout import _writable

		self.assertTrue(_writable("Quotation Item", "custom_box_type", "Item"))

	def test_a_field_of_another_type_is_not_ours_to_write(self):
		"""The installer never touches a field the site already has, so this is
		the only check standing between us and someone else's schema. Comparing
		the name alone would write a float into whatever the site happens to
		model as `custom_pack_rate` — a Select of allowed box sizes, say."""
		from upande_webstore.api.checkout import _writable

		field = frappe.db.get_value(
			"Custom Field", {"dt": "Quotation Item", "fieldname": "custom_pack_rate"}, "name"
		)
		original = frappe.db.get_value("Custom Field", field, ["fieldtype", "options"], as_dict=True)
		frappe.db.set_value(
			"Custom Field", field, {"fieldtype": "Select", "options": "\n300\n400"}
		)
		frappe.clear_cache(doctype="Quotation Item")
		try:
			self.assertFalse(
				_writable("Quotation Item", "custom_pack_rate", expect_fieldtype="Float")
			)
			self.assertTrue(
				_writable("Quotation Item", "custom_pack_rate", expect_fieldtype="Select")
			)
		finally:
			frappe.db.set_value(
				"Custom Field",
				field,
				{"fieldtype": original.fieldtype, "options": original.options},
			)
			frappe.clear_cache(doctype="Quotation Item")
			frappe.db.commit()

	def test_an_absent_field_is_never_written(self):
		from upande_webstore.api.checkout import _writable

		self.assertFalse(_writable("Quotation Item", "custom_not_a_real_field"))
