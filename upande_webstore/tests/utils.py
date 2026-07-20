import frappe


def setup_webstore_settings():
	"""Point Webstore Settings at standard test-site records; return the doc."""
	settings = frappe.get_doc("Webstore Settings")
	settings.company = frappe.defaults.get_global_default("company")
	settings.guest_price_list = "Standard Selling"
	settings.default_customer_group = "Individual"
	settings.default_territory = "All Territories"
	settings.quotation_validity_days = 14
	settings.stock_display = "In/Out Badge"
	settings.set("warehouses", [])
	settings.append("warehouses", {"warehouse": get_default_warehouse()})
	settings.save(ignore_permissions=True)
	frappe.clear_cache()
	return settings


def get_default_warehouse():
	company = frappe.defaults.get_global_default("company")
	return frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "warehouse_name": "Stores"}, "name"
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
