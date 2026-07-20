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


def make_test_item(item_code, **kwargs):
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code)
	item = frappe.get_doc({
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": kwargs.pop("item_group", "Products"),
		"stock_uom": "Nos",
		"is_stock_item": kwargs.pop("is_stock_item", 1),
		**kwargs,
	})
	item.insert(ignore_permissions=True)
	return item


def make_test_product(item_code, **kwargs):
	item = make_test_item(item_code, **{k: v for k, v in kwargs.items() if k in ("has_variants", "attributes", "item_group", "is_stock_item")})
	existing = frappe.db.get_value("Webstore Product", {"item": item.name})
	if existing:
		return frappe.get_doc("Webstore Product", existing)
	product = frappe.get_doc({
		"doctype": "Webstore Product",
		"item": item.name,
		"web_title": kwargs.get("web_title", item_code),
		"published": kwargs.get("published", 1),
		"featured": kwargs.get("featured", 0),
		"category": item.item_group,
		"short_description": kwargs.get("short_description", f"Short blurb for {item_code}"),
	})
	product.insert(ignore_permissions=True)
	return product
