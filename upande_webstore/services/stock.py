import frappe

from upande_webstore.services.settings import get_settings, get_warehouses


def get_stock_qty(item_code):
	item = frappe.get_cached_doc("Item", item_code)
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


def get_stock_info(item_code):
	item = frappe.get_cached_doc("Item", item_code)
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
