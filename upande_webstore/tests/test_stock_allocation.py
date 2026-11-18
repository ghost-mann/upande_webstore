"""Stock allocation: staff decide how much of each variety+length the webstore
sells, and webstore quotations and orders use it up."""

import frappe
from frappe.tests import IntegrationTestCase

from upande_webstore.services import allocation
from upande_webstore.services.stock import get_stock_info, get_stock_qty
from upande_webstore.tests.utils import (
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)

ATTRIBUTE = "WS SA Length"
VARIETY = "WS-SA-ROSE"
V60 = f"{VARIETY}-60cm"
V70 = f"{VARIETY}-70cm"
BUYER = "alloc.buyer@example.com"


def build_variety():
	if not frappe.db.exists("Item Attribute", ATTRIBUTE):
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": ATTRIBUTE,
				"item_attribute_values": [
					{"attribute_value": "60cm", "abbr": "60"},
					{"attribute_value": "70cm", "abbr": "70"},
				],
			}
		).insert(ignore_permissions=True)
	make_test_product(VARIETY, has_variants=1, attributes=[{"attribute": ATTRIBUTE}])
	from erpnext.controllers.item_variant import create_variant

	for value, code in (("60cm", V60), ("70cm", V70)):
		if not frappe.db.exists("Item", code):
			variant = create_variant(VARIETY, {ATTRIBUTE: value})
			variant.item_code = code
			variant.insert(ignore_permissions=True)
		make_item_price(code, "Standard Selling", 2)


def allocate(rows, on=True, **extra):
	settings = frappe.get_doc("Webstore Settings")
	settings.enable_stock_allocation = 1 if on else 0
	settings.set("stock_allocations", [])
	for length, qty in rows:
		settings.append("stock_allocations", {"variety": VARIETY, "length": length, "allocated": qty})
	for key, value in extra.items():
		settings.set(key, value)
	settings.save(ignore_permissions=True)
	return settings


def checkout(item_code, qty, mode="quotation"):
	from upande_webstore.api import cart, checkout as api

	frappe.set_user(BUYER)
	try:
		cart.add_item(item_code, qty)
		result = api.place_order(mode=mode)
	finally:
		frappe.set_user("Administrator")
	return frappe.get_doc(result["doctype"], result["name"])


class TestStockAllocation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		build_variety()
		make_portal_user(BUYER, "Allocation Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": BUYER})
		frappe.db.delete("Webstore Allocation Entry")
		# earlier tests' webstore documents would otherwise be counted by the
		# recount that runs whenever a test switches allocation on
		for doctype in ("Quotation", "Sales Order"):
			for parent in set(
				frappe.get_all(f"{doctype} Item", {"item_code": ["in", [V60, V70]]}, pluck="parent")
			):
				frappe.db.set_value(doctype, parent, "docstatus", 2, update_modified=False)
				frappe.db.sql(f"update `tab{doctype} Item` set docstatus=2 where parent=%s", parent)
		setup_webstore_settings()
		set_stock(V60, 500)
		set_stock(V70, 500)

	def tearDown(self):
		frappe.set_user("Administrator")
		setup_webstore_settings()

	# --- availability ---

	def test_switch_off_is_unchanged(self):
		allocate([("60cm", 10)], on=False)
		self.assertEqual(get_stock_qty(V60), 500)
		self.assertEqual(get_stock_qty(V70), 500)

	def test_length_without_row_is_not_sold(self):
		allocate([("60cm", 100)])
		self.assertEqual(get_stock_qty(V70), 0)
		self.assertFalse(get_stock_info(V70)["in_stock"])

	def test_available_is_min_of_remaining_and_warehouse(self):
		allocate([("60cm", 100)])
		self.assertEqual(get_stock_qty(V60), 100)
		set_stock(V60, 40)
		self.assertEqual(get_stock_qty(V60), 40)

	def test_template_not_sellable_when_on(self):
		allocate([("60cm", 100)])
		self.assertEqual(get_stock_qty(VARIETY), 0)

	def test_row_resolves_variant_and_refuses_unknown_length(self):
		settings = allocate([("60cm", 100)])
		self.assertEqual(settings.stock_allocations[0].item_code, V60)
		self.assertRaises(frappe.ValidationError, allocate, [("90cm", 100)])
		self.assertRaises(frappe.ValidationError, allocate, [("60cm", 1), ("60cm", 2)])

	# --- consumption ---

	def test_checkout_takes_and_refuses_past_remaining(self):
		allocate([("60cm", 30)])
		checkout(V60, 20)
		self.assertEqual(allocation.taken(V60), 20)
		self.assertEqual(get_stock_qty(V60), 10)
		row = frappe.get_all("Webstore Stock Allocation", {"item_code": V60}, ["taken", "remaining"])[0]
		self.assertEqual((row.taken, row.remaining), (20, 10))
		self.assertRaises(frappe.ValidationError, allocation.lock_and_check, [(V60, 15)])
		self.assertRaises(frappe.ValidationError, checkout, V60, 15)

	def test_staff_edit_resyncs_and_may_exceed(self):
		allocate([("60cm", 30)])
		order = checkout(V60, 20, mode="order")
		self.assertEqual(order.doctype, "Sales Order")
		order.items[0].qty = 5
		order.save(ignore_permissions=True)
		self.assertEqual(allocation.taken(V60), 5)
		order.items[0].qty = 45
		order.save(ignore_permissions=True)  # staff may go past
		self.assertEqual(allocation.remaining(V60), -15)
		self.assertEqual(get_stock_qty(V60), 0)

	def test_cancel_releases(self):
		allocate([("60cm", 30)])
		quotation = checkout(V60, 20)
		quotation.cancel()
		self.assertEqual(allocation.taken(V60), 0)

	def test_lost_quotation_releases(self):
		allocate([("60cm", 30)])
		quotation = checkout(V60, 20)
		quotation.db_set("status", "Lost")
		self.assertEqual(allocation.taken(V60), 0)

	def test_sales_order_from_quotation_moves_hold(self):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		allocate([("60cm", 30)])
		quotation = checkout(V60, 20)
		order = make_sales_order(quotation.name)
		order.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 7)
		for row in order.items:
			row.delivery_date = order.delivery_date
		order.flags.ignore_mandatory = True
		order.insert(ignore_permissions=True)
		self.assertEqual(order.order_type, "Shopping Cart")
		self.assertEqual(allocation.taken(V60), 20)
		held = {
			e.reference_doctype: e.qty
			for e in frappe.get_all("Webstore Allocation Entry", fields=["reference_doctype", "qty"])
		}
		self.assertEqual(held, {"Sales Order": 20})
		order.delete()
		self.assertEqual(allocation.taken(V60), 20)
		self.assertEqual(
			frappe.get_all("Webstore Allocation Entry", pluck="reference_doctype"), ["Quotation"]
		)

	def test_line_removed_from_order_returns_hold_to_quotation(self):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		allocate([("60cm", 30), ("70cm", 30)])
		quotation = checkout(V60, 20)
		order = make_sales_order(quotation.name)
		order.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 7)
		for row in order.items:
			row.delivery_date = order.delivery_date
		order.flags.ignore_mandatory = True
		order.insert(ignore_permissions=True)
		order = frappe.get_doc("Sales Order", order.name)
		delivery = order.items[0].delivery_date
		warehouse = order.items[0].warehouse
		order.set("items", [])
		order.append("items", {"item_code": V70, "qty": 1, "rate": 2, "delivery_date": delivery, "warehouse": warehouse})
		order.flags.ignore_mandatory = True
		order.save(ignore_permissions=True)
		self.assertEqual(allocation.taken(V60), 20, "the quotation holds its stems again")
		self.assertEqual(allocation.taken(V70), 1)

	def test_quotation_past_valid_till_holds_nothing(self):
		allocate([("60cm", 30)])
		quotation = checkout(V60, 20)
		frappe.db.set_value("Quotation", quotation.name, "valid_till", frappe.utils.add_days(frappe.utils.nowdate(), -1))
		allocation.recount()
		self.assertEqual(allocation.taken(V60), 0)

	def test_refusal_hides_number_in_badge_mode(self):
		allocate([("60cm", 30)])
		with self.assertRaises(frappe.ValidationError) as caught:
			allocation.lock_and_check([(V60, 40)])
		self.assertNotIn("30", str(caught.exception))

	def test_settings_save_does_not_reset_taken(self):
		allocate([("60cm", 30)])
		stale = frappe.get_doc("Webstore Settings")
		checkout(V60, 20)
		stale.save(ignore_permissions=True)
		self.assertEqual(allocation.taken(V60), 20)
		self.assertEqual(frappe.get_doc("Webstore Settings").stock_allocations[0].taken, 20)

	def test_switching_on_counts_open_orders(self):
		allocate([("60cm", 30)], on=False)
		checkout(V60, 20)
		self.assertEqual(allocation.taken(V60), 0)
		allocate([("60cm", 30)])
		self.assertEqual(allocation.taken(V60), 20)

	def test_reset_and_recount(self):
		allocate([("60cm", 30)])
		checkout(V60, 20)
		allocation.reset()
		self.assertEqual(allocation.taken(V60), 0)
		allocation.recount()
		self.assertEqual(allocation.taken(V60), 20)

	def test_expired_quotation_released_by_daily(self):
		allocate([("60cm", 30)])
		quotation = checkout(V60, 20)
		frappe.db.set_value("Quotation", quotation.name, "status", "Expired")  # as ERPNext's SQL does
		self.assertEqual(allocation.taken(V60), 20)
		allocation.daily()
		self.assertEqual(allocation.taken(V60), 0)

	# --- display ---

	def test_low_stock_warning(self):
		# a store may override the display mode; this one inherits
		for store in frappe.get_all("Webstore", pluck="name"):
			doc = frappe.get_doc("Webstore", store)
			doc.stock_display = ""
			doc.save(ignore_permissions=True)
		from upande_webstore.services.store import clear_store_cache

		clear_store_cache()
		allocate([("60cm", 40), ("70cm", 400)], low_stock_threshold=50, stock_display="Low Stock Warning")
		low = get_stock_info(V60)
		self.assertTrue(low["low"])
		self.assertEqual(low["qty"], 40)
		plenty = get_stock_info(V70)
		self.assertFalse(plenty["low"])
		self.assertIsNone(plenty["qty"])
		self.assertTrue(plenty["in_stock"])
