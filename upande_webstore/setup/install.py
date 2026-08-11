import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DEFAULT_PRESET = "mona_flowers"

WEBSTORE_CUSTOM_FIELDS = {
	"Quotation": [
		{
			"fieldname": "webstore_section",
			"fieldtype": "Section Break",
			"label": "Webstore",
			"insert_after": "order_type",
			"collapsible": 1,
		},
		{
			"fieldname": "customer_po_reference",
			"fieldtype": "Data",
			"label": "Customer PO Reference",
			"insert_after": "webstore_section",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_notes",
			"fieldtype": "Small Text",
			"label": "Webstore Notes",
			"insert_after": "customer_po_reference",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_shipping_date",
			"fieldtype": "Date",
			"label": "Requested Shipping Date",
			"insert_after": "webstore_notes",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_dropoff_points",
			"fieldtype": "Small Text",
			"label": "Dropoff Points",
			"insert_after": "webstore_shipping_date",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_portal_status",
			"fieldtype": "Select",
			"label": "Portal Status",
			"options": "\nAccepted\nDeclined",
			"insert_after": "webstore_notes",
			"read_only": 1,
		},
	],
	# Direct webstore orders carry the customer's notes too. The PO reference
	# uses Sales Order's own standard po_no field rather than a custom one.
	"Sales Order": [
		{
			"fieldname": "webstore_section",
			"fieldtype": "Section Break",
			"label": "Webstore",
			"insert_after": "order_type",
			"collapsible": 1,
		},
		{
			"fieldname": "webstore_notes",
			"fieldtype": "Small Text",
			"label": "Webstore Notes",
			"insert_after": "webstore_section",
			"read_only": 1,
		},
		{
			"fieldname": "webstore_dropoff_points",
			"fieldtype": "Small Text",
			"label": "Dropoff Points",
			"insert_after": "webstore_notes",
			"read_only": 1,
		},
		{
			"fieldname": "custom_has_mixed_boxes",
			"fieldtype": "Check",
			"label": "Mixed Box Grading",
			"insert_after": "webstore_dropoff_points",
			"default": "0",
		},
	],
	# Line-level box detail, on both the quotation and the order. `custom_`
	# rather than `webstore_` because these are the names ops already reads on
	# live; matching them is the point of sourcing box types from Items.
	"Quotation Item": [
		{
			"fieldname": "custom_box_type",
			"fieldtype": "Link",
			"label": "Box Type",
			"options": "Item",
			"insert_after": "qty",
			"read_only": 1,
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_box_type",
			"read_only": 1,
		},
		{
			"fieldname": "custom_number_of_boxes",
			"fieldtype": "Int",
			"label": "Number of Boxes",
			"insert_after": "custom_pack_rate",
			"read_only": 1,
		},
	],
	"Sales Order Item": [
		{
			"fieldname": "custom_box_type",
			"fieldtype": "Link",
			"label": "Box Type",
			"options": "Item",
			"insert_after": "qty",
			"read_only": 1,
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_box_type",
			"read_only": 1,
		},
		{
			"fieldname": "custom_number_of_boxes",
			"fieldtype": "Int",
			"label": "Number of Boxes",
			"insert_after": "custom_pack_rate",
			"read_only": 1,
		},
	],
	# Box types are Items, so the storefront and the packing floor share one
	# source. These two are `custom_`-prefixed rather than `webstore_` on
	# purpose: they are the field names ops already reads on live, where
	# upande_harvest created them. create_custom_fields skips fields that
	# already exist, so ensuring them is a no-op there and makes the feature
	# usable on a farm that has no harvest app to create them.
	"Item": [
		{
			"fieldname": "custom_is_box",
			"fieldtype": "Check",
			"label": "Is Box",
			"insert_after": "stock_uom",
			"default": "0",
		},
		{
			"fieldname": "custom_pack_rate",
			"fieldtype": "Float",
			"label": "Pack Rate",
			"insert_after": "custom_is_box",
			"description": "Stems this box holds. Leave at 0 and the storefront will not box-validate orders using it.",
		},
	],
}


def create_webstore_custom_fields():
	create_custom_fields(WEBSTORE_CUSTOM_FIELDS, ignore_validate=True)


def seed_default_theme():
	"""Fresh installs get the default preset.

	A site whose theme is already configured is never touched, so deploying to
	an existing site cannot restyle it. Deliberately not called from
	after_migrate for that reason.
	"""
	if frappe.db.get_single_value("Webstore Settings", "accent"):
		return
	if frappe.get_all("Webstore Category Card", limit=1):
		return
	from upande_webstore.theme.transfer import apply_preset

	apply_preset(DEFAULT_PRESET)


def after_install():
	create_webstore_custom_fields()
	seed_default_theme()


def normalise_settings_docstatus():
	"""Force Webstore Settings' docstatus back to 0.

	The doctype is not submittable, but a stray docstatus of 2 in tabSingles
	makes the desk treat the record as a cancelled document and offer Amend
	instead of a plain Save. Something in the migrate path keeps re-setting it,
	so this runs on every migrate rather than as a one-time patch.
	"""
	if not frappe.db.exists("DocType", "Webstore Settings"):
		return
	current = frappe.db.sql(
		"select value from tabSingles where doctype = %s and field = 'docstatus'",
		"Webstore Settings",
	)
	if not current or str(current[0][0]) == "0":
		return
	frappe.db.sql(
		"update tabSingles set value = '0' where doctype = %s and field = 'docstatus'",
		"Webstore Settings",
	)
	frappe.clear_cache(doctype="Webstore Settings")


def after_migrate():
	create_webstore_custom_fields()
	normalise_settings_docstatus()
