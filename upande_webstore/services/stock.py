import frappe

from upande_webstore.services.settings import get_settings, get_warehouses


def get_stock_qty(item_code):
	# Item is not readable by Guest on newer frappe; the storefront must not
	# require exposing it, so read only the field this needs.
	item = frappe.db.get_value("Item", item_code, ["has_variants"], as_dict=True)
	if item.has_variants:
		variants = frappe.get_all("Item", filters={"variant_of": item_code}, pluck="name")
		return max((_bin_qty(v) for v in variants), default=0.0)
	return _bin_qty(item_code)


def _bin_qty(item_code):
	warehouses = get_warehouses()
	if not warehouses:
		return 0.0
	rows = frappe.get_all(
		"Bin",
		filters={"item_code": item_code, "warehouse": ["in", warehouses]},
		fields=["actual_qty"],
	)
	return float(sum(row.actual_qty or 0 for row in rows))


def get_source_warehouse(item_code):
	"""The configured webstore warehouse to fulfil an item from.

	Availability is summed across every configured warehouse, so a direct Sales
	Order has to name one. Picks the warehouse actually holding the most of this
	item, falling back to the first configured one so a non-stock or zero-stock
	item still gets a valid warehouse.
	"""
	warehouses = get_warehouses()
	if not warehouses:
		return None
	rows = frappe.get_all(
		"Bin",
		filters={"item_code": item_code, "warehouse": ["in", warehouses]},
		fields=["warehouse", "actual_qty"],
		order_by="actual_qty desc",
		limit=1,
	)
	if rows and (rows[0].actual_qty or 0) > 0:
		return rows[0].warehouse
	return warehouses[0]


def get_stock_info(item_code):
	# Item is not readable by Guest on newer frappe; the storefront must not
	# require exposing it, so read only the field this needs.
	item = frappe.db.get_value("Item", item_code, ["is_stock_item"], as_dict=True)
	settings = get_settings()
	show_qty = settings.stock_display == "Exact Quantity"
	if not item.is_stock_item:
		return {"in_stock": True, "qty": None, "show_qty": False}
	qty = get_stock_qty(item_code)
	return {
		"in_stock": qty > 0,
		"qty": qty if show_qty else None,
		"show_qty": show_qty,
	}
