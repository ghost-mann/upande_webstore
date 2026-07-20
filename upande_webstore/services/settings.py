import frappe


def get_settings():
	return frappe.get_cached_doc("Webstore Settings")


def get_warehouses():
	return [row.warehouse for row in get_settings().warehouses]
