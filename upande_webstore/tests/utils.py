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


def make_portal_user(email, customer_name=None, price_list=None):
	customer_name = customer_name or email.split("@")[0].replace(".", " ").title()
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": customer_name,
			"send_welcome_email": 0,
			"user_type": "Website User",
		})
		user.flags.ignore_permissions = True
		user.insert()
		user.add_roles("Customer")
	if not frappe.db.exists("Customer", customer_name):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_type": "Individual",
			"customer_group": "Individual",
			"territory": "All Territories",
			"default_price_list": price_list,
		})
		customer.insert(ignore_permissions=True)
	elif price_list:
		frappe.db.set_value("Customer", customer_name, "default_price_list", price_list)
	contact_name = frappe.db.get_value("Contact", {"user": email})
	if not contact_name:
		contact = frappe.get_doc({
			"doctype": "Contact",
			"first_name": customer_name,
			"user": email,
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": customer_name}],
		})
		contact.insert(ignore_permissions=True)
	elif not frappe.db.exists(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer", "link_name": customer_name},
	):
		# frappe auto-creates a bare Contact for new users; attach the Customer link
		contact = frappe.get_doc("Contact", contact_name)
		contact.append("links", {"link_doctype": "Customer", "link_name": customer_name})
		contact.save(ignore_permissions=True)
	return email, customer_name


def make_item_price(item_code, price_list, rate):
	existing = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
	if existing:
		frappe.db.set_value("Item Price", existing, "price_list_rate", rate)
		return
	frappe.get_doc({
		"doctype": "Item Price",
		"item_code": item_code,
		"price_list": price_list,
		"price_list_rate": rate,
	}).insert(ignore_permissions=True)


def make_price_list(name):
	if not frappe.db.exists("Price List", name):
		frappe.get_doc({
			"doctype": "Price List",
			"price_list_name": name,
			"selling": 1,
			"currency": frappe.get_cached_value("Company", frappe.defaults.get_global_default("company"), "default_currency"),
		}).insert(ignore_permissions=True)
	return name


def set_stock(item_code, qty, warehouse=None):
	"""Set absolute stock via Stock Entry receipts/issues (idempotent)."""
	from erpnext.stock.utils import get_stock_balance

	warehouse = warehouse or get_default_warehouse()
	current = get_stock_balance(item_code, warehouse)
	diff = qty - current
	if diff == 0:
		return
	receiving = diff > 0
	entry = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": "Material Receipt" if receiving else "Material Issue",
		"company": frappe.defaults.get_global_default("company"),
		"items": [{
			"item_code": item_code,
			"qty": abs(diff),
			"t_warehouse": warehouse if receiving else None,
			"s_warehouse": None if receiving else warehouse,
			"basic_rate": 10,
			"allow_zero_valuation_rate": 1,
		}],
	})
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
