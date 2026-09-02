"""Desk-side box type reads.

Separate from `api/cart.py` because those endpoints are wrapped in
`@guard("cart")` — a farm with the cart feature switched off must still be able
to open Webstore Settings and see how its boxes are configured.
"""

import frappe
from frappe import _

from upande_webstore.services import packing
from upande_webstore.services.access import require_permission


@frappe.whitelist()
def list_box_types():
	"""Usable box type names, for desk autocompletes."""
	if frappe.session.user == "Guest":
		# @frappe.whitelist() (no allow_guest) already blocks Guest; this is
		# belt-and-braces for the no-source branch below, which has no doctype
		# to check permission against and would otherwise wave a Guest through.
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	source = packing.get_box_source()
	if not source:
		# nothing to read, so there is no permission question to ask
		return []
	require_permission(source.doctype)
	return [box["box_type"] for box in packing.get_box_types()]


@frappe.whitelist()
def describe_source():
	"""Everything the Webstore Settings box panel renders."""
	require_permission("Webstore Settings")
	from upande_webstore.setup.install import box_type_field_mismatches

	source = packing.get_box_source()
	return {
		"doctype": source.doctype if source else None,
		"label": packing.source_label(),
		"usable": packing.get_box_types(),
		"unusable": packing.get_unusable_box_types(),
		"default_box_type": packing.get_default_box_type(),
		# Not every mismatch is one the installer can fix on its own — a
		# populated field or a standard DocField needs a human — so this is
		# the only place an operator learns checkout has stopped writing box
		# detail to that doctype.
		"field_mismatches": [
			{
				"doctype": m.doctype,
				"targets": m.targets,
				"source": m.source,
				"rows": m.rows,
			}
			for m in box_type_field_mismatches()
		],
	}
