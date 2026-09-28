"""Customer Specifications module.

The rule tests run anywhere. The integration tests need a specifications
doctype (upande_packhouse) and skip on a site without one — the module is
built to be inert there, which TestModuleInert covers.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_item,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


def _row(**kwargs):
	return frappe._dict(kwargs)


def _header(assortment="Mono Box", low=0, high=0):
	return _row(
		name="SPEC",
		spec_name="SPEC",
		box_type="Standard",
		box_assortment=assortment,
		min_colours_per_box=low,
		max_colours_per_box=high,
	)


class TestOrderingMode(IntegrationTestCase):
	"""describe() is the rule that decides how a spec is ordered."""

	def _describe(self, header, rates, varieties, price=None):
		from upande_webstore.services import specs

		box_items = [_row(length="52cm", pack_rate=rate) for rate in rates]
		rows = [
			_row(variety=variety, colour=colour, is_primary=primary, bunch_id="1")
			for variety, colour, primary in varieties
		]
		return specs.describe(header, box_items, rows, price)

	def test_one_variety_at_one_rate_is_ordered_by_the_box(self):
		spec = self._describe(_header(), [400], [("V1", "Red", 1)])
		self.assertEqual((spec.mode, spec.fill, spec.pack_rate), ("box", "whole_boxes", 400))

	def test_box_rows_repeated_per_variety_still_count_as_one_rate(self):
		# the live data repeats the box row once per approved variety
		spec = self._describe(_header(), [720, 720], [("V1", "Lilac", 1), ("V2", "Lilac", 0)])
		self.assertEqual(spec.mode, "box")
		self.assertEqual(spec.item_codes, ["V1"], "substitutes are the packhouse's call")

	def test_mono_with_several_primaries_is_whole_boxes_per_variety(self):
		spec = self._describe(_header(), [585, 585], [("V1", "Lilac", 1), ("V2", "Pink", 1)])
		self.assertEqual((spec.mode, spec.fill, spec.pack_rate), ("variety", "whole_boxes", 585))

	def test_mono_with_disagreeing_rates_is_not_fill_checked(self):
		spec = self._describe(_header(), [450, 500], [("V1", "Cerise", 1), ("V2", "Cerise", 0)])
		self.assertEqual((spec.mode, spec.fill, spec.pack_rate), ("variety", "unchecked", 0))

	def test_a_mixed_box_is_ordered_by_variety_and_not_fill_checked(self):
		spec = self._describe(
			_header("Mixed Box", 2, 3), [64, 80, 64], [("V1", "Red", 1), ("V2", "Orange", 1), ("V3", "Yellow", 1)]
		)
		self.assertEqual((spec.mode, spec.fill), ("variety", "unchecked"))
		self.assertEqual((spec.min_colours, spec.max_colours), (2, 3))

	def test_an_unpriced_variety_is_not_offered(self):
		prices = {"V1": {"rate": 1.5, "currency": "KES"}, "V2": {"rate": 0}}
		spec = self._describe(
			_header("Mixed Box", 1, 2),
			[64],
			[("V1", "Red", 1), ("V2", "Orange", 1)],
			lambda code, length: prices[code],
		)
		self.assertEqual(spec.item_codes, ["V1"])

	def test_line_checks(self):
		from upande_webstore.services import specs

		whole = self._describe(_header(), [585], [("V1", "Lilac", 1), ("V2", "Pink", 1)])
		self.assertEqual(specs.check_lines(whole, [{"item_code": "V1", "qty": 1170}]), [])
		self.assertTrue(specs.check_lines(whole, [{"item_code": "V1", "qty": 600}]))
		self.assertTrue(specs.check_lines(whole, [{"item_code": "NOPE", "qty": 585}]))
		self.assertEqual(specs.boxes_in(whole, 1170), 2)

		mixed = self._describe(
			_header("Mixed Box", 2, 2), [64], [("V1", "Red", 1), ("V2", "Orange", 1), ("V3", "Yellow", 1)]
		)
		self.assertTrue(specs.check_lines(mixed, [{"item_code": "V1", "qty": 50}]), "one colour of two")
		self.assertEqual(
			specs.check_lines(mixed, [{"item_code": "V1", "qty": 50}, {"item_code": "V2", "qty": 7}]), []
		)
		self.assertTrue(
			specs.check_lines(
				mixed,
				[{"item_code": code, "qty": 10} for code in ("V1", "V2", "V3")],
			),
			"three colours of two",
		)


class TestModuleInert(IntegrationTestCase):
	def setUp(self):
		setup_webstore_settings()

	def test_the_module_ships_off(self):
		from upande_webstore.services import specs

		self.assertFalse(specs.module_on())

	def test_a_missing_doctype_keeps_it_inert_even_when_switched_on(self):
		from upande_webstore.services import specs

		settings = frappe.get_doc("Webstore Settings")
		settings.enable_customer_specs = 1
		settings.spec_doctype = "No Such Spec Doctype"
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		ok, reason = specs.availability()
		self.assertFalse(ok)
		self.assertIn("No Such Spec Doctype", reason)
		self.assertFalse(specs.module_on())
		self.assertEqual(specs.visible_names("Anyone"), [])


BUYER = "spec.buyer@example.com"
OTHER = "spec.other@example.com"
HAS_SPECS = lambda: bool(frappe.db.exists("DocType", "Specifications"))  # noqa: E731


def _make_spec(name, customer, box_items, varieties, assortment="Mono Box", low=0, high=0, **extra):
	if frappe.db.exists("Specifications", name):
		frappe.delete_doc("Specifications", name, force=True, ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Specifications",
			"spec_name": name,
			"customer": customer,
			"ftnft": "FT",
			"spec_type": extra.pop("spec_type", "Permanent"),
			"box_type": "WS Spec Box",
			"cut_stage": "WS Stage",
			"defoliation_length": "15",
			"box_assortment": assortment,
			"min_colours_per_box": low,
			"max_colours_per_box": high,
			"box_items": [
				{"length": "52cm", "stems_per_bunch": spb, "bunches_per_box": bpb} for spb, bpb in box_items
			],
			"approved_varieties": [
				{"variety": variety, "colour": colour, "is_primary": primary, "bunch_id": "1"}
				for variety, colour, primary in varieties
			],
			**extra,
		}
	)
	# test fixtures only: the packhouse's Box Type, Cut Stage, Stem Length and
	# Colors masters are not what this suite is about
	doc.flags.ignore_links = True
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


@unittest.skipUnless(HAS_SPECS(), "needs a Specifications doctype (upande_packhouse)")
class TestCustomerSpecs(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		for code in ("WS-SP-RED", "WS-SP-ORANGE", "WS-SP-YELLOW", "WS-SP-PINK"):
			make_test_item(code, is_stock_item=0)
			make_item_price(code, "Standard Selling", 2)
		# a published product too, so a plain line of the same variety can coexist
		make_test_product("WS-SP-PLAIN")
		make_item_price("WS-SP-PLAIN", "Standard Selling", 3)
		cls.customer = make_portal_user(BUYER, "Spec Buyer Ltd", price_list="Standard Selling")[1]
		cls.other = make_portal_user(OTHER, "Spec Other Ltd", price_list="Standard Selling")[1]
		if not frappe.db.exists("Box Type", "WS Spec Box"):
			box = frappe.new_doc("Box Type")
			box.update({"box_name": "WS Spec Box"})
			box.name = "WS Spec Box"
			box.flags.ignore_mandatory = True
			box.insert(ignore_permissions=True, set_name="WS Spec Box")
		cls.by_box = _make_spec("WS-SPEC-MONO 52", cls.customer, [(10, 40), (10, 40)], [("WS-SP-RED", "Red", 1), ("WS-SP-PINK", "Red", 0)])
		cls.mixed = _make_spec(
			"WS-SPEC-MIX 52",
			cls.customer,
			[(5, 16), (4, 16), (5, 16)],
			[("WS-SP-RED", "Red", 1), ("WS-SP-ORANGE", "Orange", 1), ("WS-SP-YELLOW", "Yellow", 1)],
			assortment="Mixed Box",
			low=2,
			high=2,
		)
		cls.theirs = _make_spec("WS-SPEC-THEIRS 52", cls.other, [(10, 40)], [("WS-SP-RED", "Red", 1)])
		cls.inactive = _make_spec("WS-SPEC-OFF 52", cls.customer, [(10, 40)], [("WS-SP-RED", "Red", 1)])
		frappe.db.set_value("Specifications", cls.inactive, "status", "Inactive")
		cls.expired = _make_spec(
			"WS-SPEC-OLD 52",
			cls.customer,
			[(10, 40)],
			[("WS-SP-RED", "Red", 1)],
			spec_type="Temporary",
			valid_from=add_days(nowdate(), -30),
			expiry_date=add_days(nowdate(), -1),
		)

	def setUp(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()
		settings = frappe.get_doc("Webstore Settings")
		settings.enable_customer_specs = 1
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		frappe.db.delete("Webstore Cart", {"user": BUYER})
		set_stock("WS-SP-PLAIN", 1000)
		# Kaitet's setting: one variety on several lines, one per spec
		frappe.db.set_single_value("Selling Settings", "allow_multiple_items", 1)
		frappe.set_user(BUYER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_module_switch_gates_the_api(self):
		from upande_webstore.api import specs as api

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Webstore Settings", "enable_customer_specs", 0)
		frappe.clear_cache()
		frappe.set_user(BUYER)
		with self.assertRaises(frappe.PermissionError):
			api.get_my_specs()

	def test_a_customer_sees_only_their_active_in_date_specs(self):
		from upande_webstore.api import specs as api

		names = [spec.name for spec in api.get_my_specs()]
		self.assertIn(self.by_box, names)
		self.assertIn(self.mixed, names)
		for hidden in (self.theirs, self.inactive, self.expired):
			self.assertNotIn(hidden, names)

	def test_another_customers_spec_cannot_be_added(self):
		from upande_webstore.api import specs as api

		for hidden in (self.theirs, self.inactive, self.expired, "NO SUCH SPEC"):
			with self.assertRaises(frappe.ValidationError) as caught:
				api.add_spec(hidden, boxes=1)
			self.assertIn("not available", str(caught.exception))

	def test_by_the_box(self):
		from upande_webstore.api import specs as api

		cart = api.add_spec(self.by_box, boxes=2)
		line = next(row for row in cart["items"] if row["specification"] == self.by_box)
		self.assertEqual(line["item_code"], "WS-SP-RED")
		self.assertEqual(line["qty"], 800)
		self.assertEqual(line["box_type"], "WS Spec Box")
		self.assertTrue(line["box_fixed"])
		self.assertEqual(line["number_of_boxes"], 2)
		with self.assertRaises(frappe.ValidationError):
			api.add_spec(self.by_box, boxes=0)

	def test_a_spec_line_box_cannot_be_changed(self):
		from upande_webstore.api import cart, specs as api

		api.add_spec(self.by_box, boxes=1)
		with self.assertRaises(frappe.ValidationError):
			cart.set_box_type("WS-SP-RED", "anything", specification=self.by_box)

	def test_a_variety_outside_the_spec_is_refused(self):
		from upande_webstore.api import specs as api

		with self.assertRaises(frappe.ValidationError) as caught:
			api.add_spec(self.mixed, lines=[{"item_code": "WS-SP-PINK", "qty": 20}])
		self.assertIn("not an approved variety", str(caught.exception))

	def test_the_same_variety_plain_and_under_a_spec_are_two_lines(self):
		from upande_webstore.api import cart, specs as api

		api.add_spec(self.mixed, lines=[{"item_code": "WS-SP-RED", "qty": 20}, {"item_code": "WS-SP-ORANGE", "qty": 20}])
		result = cart.add_item("WS-SP-PLAIN", 5)
		self.assertEqual(len(result["items"]), 3)
		result = cart.update_qty("WS-SP-RED", 30, specification=self.mixed)
		red = next(row for row in result["items"] if row["item_code"] == "WS-SP-RED")
		self.assertEqual(red["qty"], 30)

	def test_a_mixed_spec_needs_its_colour_count_before_checkout(self):
		from upande_webstore.api import checkout, specs as api

		api.add_spec(self.mixed, lines=[{"item_code": "WS-SP-RED", "qty": 40}])
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order(mode="order")
		self.assertIn("colours", str(caught.exception))

	def test_a_spec_order_reaches_the_sales_order_tagged_with_its_spec(self):
		from upande_webstore.api import checkout, specs as api

		api.add_spec(self.by_box, boxes=1)
		api.add_spec(
			self.mixed,
			lines=[{"item_code": "WS-SP-RED", "qty": 40}, {"item_code": "WS-SP-YELLOW", "qty": 24}],
		)
		result = checkout.place_order(mode="order")
		frappe.set_user("Administrator")
		order = frappe.get_doc("Sales Order", result["sales_order"])
		by_spec = {(row.item_code, row.get("custom_line")): row for row in order.items}
		self.assertEqual(set(by_spec), {
			("WS-SP-RED", self.by_box),
			("WS-SP-RED", self.mixed),
			("WS-SP-YELLOW", self.mixed),
		})
		mono = by_spec[("WS-SP-RED", self.by_box)]
		self.assertEqual(mono.qty, 400)
		self.assertEqual(mono.rate, 2)
		if frappe.get_meta("Sales Order Item").get_field("custom_box_type"):
			self.assertEqual(mono.custom_box_type, "WS Spec Box")
		if frappe.get_meta("Sales Order Item").get_field("custom_number_of_boxes"):
			self.assertEqual(mono.custom_number_of_boxes, 1)
		# a mixed spec's box count is the packhouse's to set, so none is written
		# (the column keeps whatever default the site gives it)
		if frappe.get_meta("Sales Order").get_field("custom_has_mixed_boxes"):
			self.assertEqual(order.custom_has_mixed_boxes, 1)

	def test_a_repeated_variety_gets_a_basket_message_where_the_site_forbids_it(self):
		from upande_webstore.api import checkout, specs as api

		frappe.db.set_single_value("Selling Settings", "allow_multiple_items", 0)
		api.add_spec(self.by_box, boxes=1)
		api.add_spec(
			self.mixed,
			lines=[{"item_code": "WS-SP-RED", "qty": 40}, {"item_code": "WS-SP-YELLOW", "qty": 24}],
		)
		with self.assertRaises(frappe.ValidationError) as caught:
			checkout.place_order(mode="order")
		self.assertIn("more than once", str(caught.exception))

	def test_a_length_priced_site_prices_a_spec_at_its_length(self):
		"""On a packhouse site Item Price carries a stem length, and a spec's
		lines must price at the spec's length, not any length's rate."""
		from upande_webstore.api import specs as api

		if not frappe.get_meta("Item Price").get_field("custom_length"):
			self.skipTest("this site does not price by stem length")
		frappe.set_user("Administrator")
		for length, rate in (("52cm", 7), ("62cm", 9)):
			if not frappe.db.exists("Stem Length", length):
				stem = frappe.new_doc("Stem Length")
				stem.flags.ignore_mandatory = True
				stem.insert(ignore_permissions=True, set_name=length)
			price = frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": "WS-SP-ORANGE",
					"price_list": "Standard Selling",
					"price_list_rate": rate,
					"custom_length": length,
					"uom": frappe.db.get_value("Item", "WS-SP-ORANGE", "stock_uom"),
				}
			)
			price.flags.ignore_links = True
			price.insert(ignore_permissions=True)
		frappe.set_user(BUYER)
		mixed = next(spec for spec in api.get_my_specs() if spec.name == self.mixed)
		orange = next(line for line in mixed.lines if line["item_code"] == "WS-SP-ORANGE")
		self.assertEqual(orange["rate"], 7)
		cart = api.add_spec(self.mixed, lines=[{"item_code": "WS-SP-ORANGE", "qty": 10}])
		self.assertEqual(cart["items"][0]["rate"], 7)
