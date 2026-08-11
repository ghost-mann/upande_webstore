"""Keep webstore fields alive across quotation -> sales order.

ERPNext's `make_sales_order` copies only the fields its table_maps declare, so a
custom field set by the storefront is silently dropped. That lost the buyer's
requested shipping date and their dropoff instructions on every conversion,
whether done from the portal or the desk.
"""

import frappe

CARRIED = ("webstore_shipping_date", "webstore_dropoff_points", "custom_delivery_point")


def _present(doctype, fieldname):
	return bool(frappe.get_meta(doctype).get_field(fieldname))


def _source_quotation(doc):
	for row in doc.get("items") or []:
		if row.get("prevdoc_docname"):
			return row.get("prevdoc_docname")
	return None


def carry_webstore_fields(doc, method=None):
	if doc.doctype != "Sales Order":
		return
	source = _source_quotation(doc)
	if not source or not frappe.db.exists("Quotation", source):
		return

	# custom_delivery_point comes from another app and may be absent on either
	# doctype; Delivery Point itself is missing on some sites, and writing a Link
	# whose target doctype does not exist fails validation.
	readable = [field for field in CARRIED if _present("Quotation", field)]
	if "custom_delivery_point" in readable and not frappe.db.exists(
		"DocType", "Delivery Point"
	):
		readable.remove("custom_delivery_point")
	if not readable:
		return

	values = frappe.db.get_value("Quotation", source, readable, as_dict=True) or {}

	requested = values.get("webstore_shipping_date")
	if requested:
		# the buyer's explicit request beats whatever the mapper derived
		doc.delivery_date = requested
		for row in doc.get("items") or []:
			row.delivery_date = requested

	for field in ("webstore_dropoff_points", "custom_delivery_point"):
		value = values.get(field)
		if value and _present("Sales Order", field) and not doc.get(field):
			doc.set(field, value)
