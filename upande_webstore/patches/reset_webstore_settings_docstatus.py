"""Repair a Webstore Settings record left with docstatus 2 (Cancelled).

A Single doctype has no submit workflow — Webstore Settings is not submittable —
but a stray docstatus row in `tabSingles` makes the desk treat the record as a
cancelled document and offer Amend instead of a plain Save. Anything other than
0 is meaningless here, so normalise it.
"""

import frappe


def execute():
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
