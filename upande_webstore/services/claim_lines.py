"""Source-document line snapshot and the arithmetic over it.

Kept apart from the controller so the sums can be tested without building a
document, the way services/packing.py separates box arithmetic from carts.
"""

import frappe
from frappe import _
from frappe.utils import flt

#: Copied onto a claim line. Standard item-table fields only, present on both
#: Sales Invoice Item and Delivery Note Item — a farm's own customs (Kaitet has
#: custom_length and custom_box_type) are guarded separately, because this app
#: must work on a site that has neither.
SNAPSHOT_FIELDS = ("item_code", "item_name", "uom", "qty", "rate", "amount")

#: claimable doctype -> its item table
ITEM_DOCTYPES = {
	"Sales Invoice": "Sales Invoice Item",
	"Delivery Note": "Delivery Note Item",
}


def snapshot_rows(name, doctype="Sales Invoice"):
	"""The rows a claim would store for `doctype` `name`, as plain dicts.

	Read once and copied: an invoice or delivery note can be amended or
	cancelled afterwards, and the basis of an agreed settlement must not move
	underneath it.
	"""
	if not name:
		return []
	item_doctype = ITEM_DOCTYPES.get(doctype)
	if not item_doctype:
		frappe.throw(_("Cannot fetch lines from {0}.").format(doctype), frappe.ValidationError)
	rows = frappe.get_all(
		item_doctype,
		filters={"parent": name, "parenttype": doctype},
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
			"claimed_qty": 0,
			"new_rate": 0,
			"claim_amount": 0,
		}
		for row in rows
	]


def _getter(row):
	return row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)


def line_amount(row, price_adjustment=False):
	"""What one line claims back.

	Quantity-based: Claimed Quantity × Rate. Price adjustment: Claimed Quantity
	× (Rate − New Unit Value), the difference the customer overpaid. A line
	with no claimed quantity is not part of the claim, whatever else is on it.
	"""
	get = _getter(row)
	qty = flt(get("claimed_qty"))
	if qty <= 0:
		return 0.0
	rate = flt(get("rate"))
	if price_adjustment:
		return qty * (rate - flt(get("new_rate")))
	return qty * rate


def claimed_total(rows, price_adjustment=False):
	"""Sum of line_amount over every row."""
	return sum(line_amount(row, price_adjustment) for row in rows or [])


def assert_claimable_quantities(rows, price_adjustment=False):
	"""Refuse a line claiming more than was invoiced, or a unit value the
	invoice rate does not leave room for, naming the line."""
	for idx, row in enumerate(rows or [], start=1):
		get = _getter(row)
		claimed = flt(get("claimed_qty"))
		invoiced = flt(get("invoiced_qty"))
		if claimed < 0:
			frappe.throw(
				_("Line {0} ({1}): the claimed quantity cannot be negative.").format(idx, get("item_code")),
				frappe.ValidationError,
			)
		if claimed > invoiced:
			frappe.throw(
				_("Line {0} ({1}): claimed {2} of {3} invoiced.").format(
					idx, get("item_code"), claimed, invoiced
				),
				frappe.ValidationError,
			)
		if not price_adjustment:
			continue
		new_rate = flt(get("new_rate"))
		if new_rate < 0:
			frappe.throw(
				_("Line {0} ({1}): the new unit value cannot be negative.").format(idx, get("item_code")),
				frappe.ValidationError,
			)
		if new_rate > flt(get("rate")):
			frappe.throw(
				_("Line {0} ({1}): the new unit value {2} is above the invoiced rate {3}.").format(
					idx, get("item_code"), new_rate, flt(get("rate"))
				),
				frappe.ValidationError,
			)
