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
	# Packing config is not in the FEATURES registry, so the feature-flag loop
	# below does not cover it. Reset explicitly or a module that enables box
	# packing breaks whichever module runs next.
	settings.enable_box_packing = 0
	settings.default_box_type = ""
	settings.minimum_order_stems = 0
	settings.default_lead_days = 7
	# Blank is "Buyer chooses"; reset explicitly or a module that narrows
	# checkout to one mode leaks into whichever module runs next.
	settings.checkout_mode = ""
	for field in (
		"brand_logo",
		"hero_image",
		"favicon",
		"flowers_category_image",
		"coffee_category_image",
		"produce_category_image",
		"primary_color",
	):
		settings.set(field, "")

	# Reset every theme seed, branding string and feature flag, so a test that
	# customises one of them cannot leak into whichever test runs next.
	from upande_webstore.theme.branding import DEFAULTS
	from upande_webstore.theme.features import FEATURES
	from upande_webstore.theme.tokens import THEME_FIELDS

	for field in THEME_FIELDS:
		settings.set(field, 0 if field == "accent_drives_primary" else "")
	for field in DEFAULTS:
		settings.set(field, "")
	for feature in FEATURES:
		settings.set(feature.fieldname, 1)
	# occasion state is deliberately outside THEME_FIELDS, so it needs its own
	# reset or a campaign set by one test module leaks into the next
	for field in (
		"occasion",
		"occasion_banner_text",
		"occasion_banner_cta_label",
		"occasion_banner_cta_url",
	):
		settings.set(field, "")
	settings.set("occasion_runs_until", None)
	for table in ("hero_stats", "category_cards", "process_steps", "footer_links"):
		settings.set(table, [])
	settings.set("warehouses", [])
	settings.append("warehouses", {"warehouse": get_default_warehouse()})

	# The Roles section reconciles real Custom DocPerms on save — leaving a
	# grant from one test module set would leak permissions into whichever
	# module runs next, same story as every other field reset above.
	for table in ("catalogue_manager_roles", "order_manager_roles", "portal_manager_roles"):
		settings.set(table, [])

	settings.save(ignore_permissions=True)
	reset_portal_settings()
	from upande_webstore.services.packing import clear_box_source_cache

	clear_box_source_cache()
	frappe.clear_cache()
	return settings


PORTAL_SETTING_DEFAULTS = {
	"landing_page": "Dashboard",
	"welcome_note": "",
	"support_note": "",
	"spend_months": 0,
	"recent_orders_count": 0,
	"top_items_count": 0,
	"statement_default_days": 0,
	"max_attachment_mb": 0,
	# 0 means unset, so get_int falls back to the shipped 14-day window
	"claim_window_days": 0,
	"quotation_accept_requires_po": 0,
	"allow_invoice_pdf": 1,
	"require_claim_document": 0,
	"allow_claim_attachments": 1,
	"allow_profile_edit": 1,
	"allow_address_edit": 1,
}


def reset_portal_settings():
	"""Webstore Portal Settings is a second Single, so it leaks across test
	modules exactly like Webstore Settings does — require_claim_document set by
	one module used to break claim tests in another.

	Written column-by-column rather than through a full doc save: this runs in
	every setUp, and repeated Single saves contend for the same tabSingles row.
	"""
	if not frappe.db.exists("DocType", "Webstore Portal Settings"):
		return
	for fieldname, value in PORTAL_SETTING_DEFAULTS.items():
		frappe.db.set_single_value("Webstore Portal Settings", fieldname, value)
	frappe.db.delete(
		"Webstore Claim Type",
		{"parent": "Webstore Portal Settings", "parentfield": "claim_types"},
	)
	frappe.clear_cache(doctype="Webstore Portal Settings")


def get_default_warehouse():
	company = frappe.defaults.get_global_default("company")
	return frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "warehouse_name": "Stores"}, "name"
	) or frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")


BOX_TYPE_DOCTYPE = "Box Type"


def _fixture_owns_box_type():
	"""True only for the Custom DocType this fixture itself created.

	A real `Box Type` on a live or restored site (Karen Roses) is custom=0 or
	lives in a different module, so this returns False for it — the fixture
	must never touch a doctype it did not create.
	"""
	row = frappe.db.get_value("DocType", BOX_TYPE_DOCTYPE, ["custom", "module"], as_dict=True)
	return bool(row) and int(row.custom or 0) == 1 and row.module == "Upande Webstore"


def make_box_type_doctype():
	"""A stand-in for the `Box Type` doctype Karen Roses runs.

	Created as a Custom DocType so this app owns no file for it, exactly as on
	live where another app defines it. Tests that create it MUST drop it in
	tearDownClass: a lingering Box Type flips the source for every other module.

	Refuses to run against a site that already has a real `Box Type` — adopting
	one would let `drop_box_type_doctype` delete production master data.
	"""
	if frappe.db.exists("DocType", BOX_TYPE_DOCTYPE):
		if _fixture_owns_box_type():
			return BOX_TYPE_DOCTYPE
		frappe.throw(
			"This site already has a real `Box Type` doctype. TestBoxSource must "
			"not run against it: drop_box_type_doctype() would delete its "
			"production data. Run these tests on a site without one."
		)
	frappe.get_doc({
		"doctype": "DocType",
		"name": BOX_TYPE_DOCTYPE,
		"module": "Upande Webstore",
		"custom": 1,
		"autoname": "field:box_type",
		"fields": [
			{"fieldname": "box_type", "fieldtype": "Data", "label": "Box Type", "unique": 1, "reqd": 1},
			{"fieldname": "custom_stem_capacity", "fieldtype": "Int", "label": "Stem Capacity"},
		],
		"permissions": [
			{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
		],
	}).insert(ignore_permissions=True)
	frappe.clear_cache()
	return BOX_TYPE_DOCTYPE


def make_box_type(name, capacity):
	"""One Box Type record, e.g. make_box_type("Xpol", 350)."""
	from upande_webstore.services.packing import clear_box_source_cache

	make_box_type_doctype()
	if frappe.db.exists(BOX_TYPE_DOCTYPE, name):
		frappe.db.set_value(BOX_TYPE_DOCTYPE, name, "custom_stem_capacity", capacity)
	else:
		frappe.get_doc({
			"doctype": BOX_TYPE_DOCTYPE,
			"box_type": name,
			"custom_stem_capacity": capacity,
		}).insert(ignore_permissions=True)
	clear_box_source_cache()
	return name


def drop_box_type_doctype():
	"""Undo make_box_type_doctype — and only that.

	Guarded end to end on _fixture_owns_box_type: a real `Box Type` (Karen
	Roses, or a staging restore) must survive this unconditionally, table
	included. delete_doc(force=1) skips the link-integrity check that would
	otherwise refuse a doctype with data referencing it, and the DROP TABLE
	that follows is non-transactional DDL a test rollback cannot undo — so
	this must never fire against a doctype the fixture did not create.
	"""
	from upande_webstore.services.packing import clear_box_source_cache

	if not _fixture_owns_box_type():
		return
	frappe.delete_doc("DocType", BOX_TYPE_DOCTYPE, force=1, ignore_permissions=True)
	# delete_doc removes the DocType record but, same as frappe's own uninstall
	# routine (installer.py's _delete_doctypes), never drops the data table it
	# described. Left alone, rows from one test's records survive into the next
	# test's "freshly created" doctype and silently make it look populated.
	frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{BOX_TYPE_DOCTYPE}`")
	frappe.clear_cache()
	clear_box_source_cache()


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


def make_desk_user(email, roles, first_name=None):
	"""A System User carrying exactly `roles`, for desk-side permission tests.

	Recreated from scratch on every call rather than reused like
	make_portal_user — a test asserting a specific role's DocPerms must not
	inherit roles a previous, failed test left behind. Callers must clean up
	with frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	on every path, including when an assertion raises.
	"""
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	first_name = first_name or email.split("@")[0].replace(".", " ").title()
	user = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": first_name,
		"send_welcome_email": 0,
		"user_type": "System User",
	})
	user.flags.ignore_permissions = True
	user.insert()
	user.add_roles(*roles)
	return email


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


def make_variant_template(template_code):
	if not frappe.db.exists("Item Attribute", "WS Size"):
		frappe.get_doc({
			"doctype": "Item Attribute",
			"attribute_name": "WS Size",
			"item_attribute_values": [
				{"attribute_value": "S", "abbr": "S"},
				{"attribute_value": "M", "abbr": "M"},
				{"attribute_value": "L", "abbr": "L"},
			],
		}).insert(ignore_permissions=True)
	template = make_test_item(
		template_code, has_variants=1, attributes=[{"attribute": "WS Size"}]
	)
	from erpnext.controllers.item_variant import create_variant

	for size in ("S", "M"):
		variant_code = f"{template_code}-{size}"
		if not frappe.db.exists("Item", variant_code):
			variant = create_variant(template_code, {"WS Size": size})
			variant.item_code = variant_code
			variant.insert(ignore_permissions=True)
	return template
