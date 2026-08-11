"""Dropoff points, detected rather than owned.

`Delivery Point` is a doctype another app ships — it exists on some sites and
not others, while Link fields pointing at it exist regardless. So this app never
defines it: when the doctype is present the storefront offers a picker and writes
the Link, and when it is absent the buyer types free text exactly as before.
"""

import frappe

DOCTYPE = "Delivery Point"


def delivery_points_available():
	return bool(frappe.db.exists("DocType", DOCTYPE))


def get_delivery_points():
	if not delivery_points_available():
		return []
	filters = {}
	if frappe.get_meta(DOCTYPE).get_field("disabled"):
		filters["disabled"] = 0
	return frappe.get_all(DOCTYPE, filters=filters, pluck="name", order_by="name asc")


def resolve(delivery_point):
	"""The value to store, or None when this site cannot store it."""
	if not delivery_point or not delivery_points_available():
		return None
	if not frappe.db.exists(DOCTYPE, delivery_point):
		return None
	return delivery_point
