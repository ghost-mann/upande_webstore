import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from upande_webstore.tests.utils import (
	get_default_warehouse,
	make_item_price,
	make_portal_user,
	make_test_product,
	set_stock,
	setup_webstore_settings,
)


def convert(name):
	"""Map a quotation to a sales order the way the desk does.

	The mapper leaves item warehouses blank, since a quotation has none, so the
	desk asks the user for one. Supply it here or insert() cannot succeed.
	"""
	from erpnext.selling.doctype.quotation.quotation import make_sales_order

	order = make_sales_order(name)
	for row in order.items:
		row.warehouse = get_default_warehouse()
	order.insert(ignore_permissions=True)
	return order


class TestQuotationConversion(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_webstore_settings()
		make_test_product("WS-CONV-ITEM")
		make_item_price("WS-CONV-ITEM", "Standard Selling", 10)
		make_portal_user("conv.buyer@example.com", "Conv Buyer")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Webstore Cart", {"user": "conv.buyer@example.com"})
		set_stock("WS-CONV-ITEM", 500)
		frappe.db.set_single_value("Webstore Settings", "enable_box_packing", 0)
		frappe.db.set_single_value("Webstore Settings", "default_lead_days", 7)
		frappe.clear_cache()

	def _quotation_with(self, when, dropoff):
		from upande_webstore.api import cart, checkout

		frappe.set_user("conv.buyer@example.com")
		cart.add_item("WS-CONV-ITEM", 2)
		result = checkout.place_order(shipping_date=when, dropoff_points=dropoff)
		frappe.set_user("Administrator")
		return result["quotation"]

	def test_conversion_carries_date_and_dropoff(self):
		"""The whole point: ERPNext's mapper drops custom fields, so without the
		hook the buyer's requested date silently vanishes."""
		when = add_days(nowdate(), 10)
		name = self._quotation_with(when, "Gate 3\nDepot B")
		order = convert(name)
		self.assertEqual(str(order.delivery_date), when)
		self.assertEqual(str(order.items[0].delivery_date), when)
		self.assertIn("Gate 3", order.webstore_dropoff_points)

	def test_conversion_without_webstore_fields_invents_nothing(self):
		"""ERPNext's mapper leaves delivery_date blank when the quotation has no
		date, and the hook must not fabricate one to fill the gap."""
		name = self._quotation_with(None, None)
		order = convert(name)
		self.assertFalse(order.webstore_dropoff_points)
		self.assertIsNone(order.delivery_date)

	def test_plain_sales_order_is_untouched(self):
		"""No prevdoc_docname means nothing to carry; the hook must no-op."""
		order = frappe.get_doc({
			"doctype": "Sales Order",
			"customer": "Conv Buyer",
			"company": frappe.defaults.get_global_default("company"),
			"selling_price_list": "Standard Selling",
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 4),
			"items": [{
				"item_code": "WS-CONV-ITEM",
				"qty": 1,
				"rate": 10,
				"delivery_date": add_days(nowdate(), 4),
				"warehouse": get_default_warehouse(),
			}],
		})
		order.insert(ignore_permissions=True)
		self.assertEqual(str(order.delivery_date), add_days(nowdate(), 4))
