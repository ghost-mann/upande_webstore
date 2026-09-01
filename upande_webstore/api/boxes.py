"""Desk-side box type reads.

Separate from `api/cart.py` because those endpoints are wrapped in
`@guard("cart")` — a farm with the cart feature switched off must still be able
to open Webstore Settings and see how its boxes are configured.
"""

import frappe

from upande_webstore.services import packing


@frappe.whitelist()
def list_box_types():
	"""Usable box type names, for desk autocompletes."""
	frappe.only_for("System Manager")
	return [box["box_type"] for box in packing.get_box_types()]


@frappe.whitelist()
def describe_source():
	"""Everything the Webstore Settings box panel renders."""
	frappe.only_for("System Manager")
	source = packing.get_box_source()
	return {
		"doctype": source.doctype if source else None,
		"label": packing.source_label(),
		"usable": packing.get_box_types(),
		"unusable": packing.get_unusable_box_types(),
		"default_box_type": packing.get_default_box_type(),
	}
