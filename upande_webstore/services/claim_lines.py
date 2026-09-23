"""Invoice-line snapshot and the arithmetic over it.

Kept apart from the controller so the sums can be tested without building a
document, the way services/packing.py separates box arithmetic from carts.
"""

import frappe
from frappe import _
from frappe.utils import flt

#: Copied onto a claim line. Standard Sales Invoice Item fields only — a farm's
#: own customs (Kaitet has custom_length and custom_box_type) are guarded
#: separately, because this app must work on a site that has neither.
SNAPSHOT_FIELDS = ("item_code", "item_name", "uom", "qty", "rate", "amount")


def snapshot_rows(invoice):
	"""The rows a claim would store for `invoice`, as plain dicts.

	Read once and copied: an invoice can be amended or cancelled afterwards,
	and the basis of an agreed settlement must not move underneath it.
	"""
	if not invoice:
		return []
	rows = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": invoice, "parenttype": "Sales Invoice"},
		fields=list(SNAPSHOT_FIELDS),
		order_by="idx asc",
	)
	return [
		{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"uom": row.uom,
			"invoiced_qty": flt(row.qty),
			"rate": flt(row.rate),
			"invoiced_amount": flt(row.amount),
			"is_claimed": 0,
			"claimed_qty": 0,
			"proposed_value": 0,
		}
		for row in rows
	]


def claimed_total(rows):
	"""Sum of proposed_value over ticked rows. An unticked row contributes
	nothing, however it was filled in."""
	total = 0.0
	for row in rows or []:
		get = row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)
		if get("is_claimed"):
			total += flt(get("proposed_value"))
	return total


def assert_claimable_quantities(rows):
	"""Refuse a line claiming more than was invoiced, naming the line."""
	for idx, row in enumerate(rows or [], start=1):
		get = row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)
		if not get("is_claimed"):
			continue
		claimed = flt(get("claimed_qty"))
		invoiced = flt(get("invoiced_qty"))
		if claimed > invoiced:
			frappe.throw(
				_("Line {0} ({1}): claimed {2} of {3} invoiced.").format(
					idx, get("item_code"), claimed, invoiced
				),
				frappe.ValidationError,
			)
