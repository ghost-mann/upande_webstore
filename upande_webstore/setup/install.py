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


def after_migrate():
	create_webstore_custom_fields()
