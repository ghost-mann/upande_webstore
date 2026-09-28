"""Ordering against the customer's own specifications.

Every endpoint re-derives the customer from the session and re-checks that the
spec is theirs and still in date; nothing about which spec a buyer may order is
taken from the client.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from upande_webstore.api.cart import (
	_find_row,
	_get_open_cart,
	_recompute_boxes,
	_reprice,
	_require_login,
	_validate_stock,
	serialize_cart,
)
from upande_webstore.services import specs
from upande_webstore.services.access import require_permission
from upande_webstore.theme.features import guard


def _require_module():
	# the feature guard answers "is the switch on"; this answers "is there
	# anything to read", which a switch flipped on a site without the
	# packhouse app would otherwise turn into a server error
	if not specs.availability()[0]:
		frappe.throw(_("This feature is not enabled."), frappe.PermissionError)


def _spec_or_throw(specification):
	spec = specs.get_for_customer(specification)
	if not spec:
		frappe.throw(specs.not_available(), frappe.ValidationError)
	return spec


@frappe.whitelist()
@guard("cart", "customer_specs")
def get_my_specs():
	_require_login()
	_require_module()
	return specs.my_specs()


@frappe.whitelist(methods=["POST"])
@guard("cart", "customer_specs")
def add_spec(specification, boxes=None, lines=None):
	"""Add a spec to the cart.

	By the box: `boxes` whole boxes of the spec's one variety.
	By variety: `lines` = [{"item_code", "qty"}] in stems, one per primary variety.
	Quantities add to what the cart already holds under this spec.
	"""
	_require_login()
	_require_module()
	spec = _spec_or_throw(specification)

	if spec.mode == specs.BY_BOX:
		count = cint(boxes)
		if count <= 0:
			frappe.throw(_("Enter at least one box."), frappe.ValidationError)
		wanted = [{"item_code": spec.item_codes[0], "qty": count * spec.pack_rate}]
	else:
		if isinstance(lines, str):
			lines = json.loads(lines or "[]")
		wanted = [
			{"item_code": line.get("item_code"), "qty": flt(line.get("qty"))}
			for line in (lines or [])
			if flt(line.get("qty")) > 0
		]
		if not wanted:
			frappe.throw(_("Enter a quantity for at least one variety."), frappe.ValidationError)

	allowed = set(spec.item_codes)
	for line in wanted:
		if line["item_code"] not in allowed:
			frappe.throw(
				_("{0}: {1} is not an approved variety of this specification.").format(
					spec.spec_name, line["item_code"]
				),
				frappe.ValidationError,
			)

	cart = _get_open_cart(create=True)
	for line in wanted:
		existing = _find_row(cart, line["item_code"], spec.name)
		qty = (flt(existing.qty) if existing else 0) + line["qty"]
		_validate_stock(line["item_code"], qty)
		if existing:
			existing.qty = qty
		else:
			cart.append(
				"items",
				{"item_code": line["item_code"], "qty": qty, "specification": spec.name},
			)
	_reprice(cart)
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return serialize_cart(cart)


@frappe.whitelist()
def describe_source():
	"""The Webstore Settings panel under the module switch."""
	require_permission("Webstore Settings")
	return specs.source_summary()
