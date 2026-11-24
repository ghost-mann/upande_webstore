"""Stems per bunch: a variety is sold in whole bunches.

The farm's own app decides the bunch through the `webstore_stems_per_bunch`
hook (upande_packhouse answers with the bunch its pick lists use), so the shop
never takes an order the packhouse would have to round. Without the hook, the
Item's own "Bunch (N)" unit counts when it really holds N stems; with neither,
a variety sells by the stem (1).
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt


def stems_per_bunch(item_code):
	cache = getattr(frappe.local, "webstore_stems_per_bunch", None)
	if cache is None:
		cache = frappe.local.webstore_stems_per_bunch = {}
	if item_code not in cache:
		cache[item_code] = _resolve(item_code)
	return cache[item_code]


def _resolve(item_code):
	if not item_code:
		return 1
	hooks = frappe.get_hooks("webstore_stems_per_bunch") or []
	if hooks:
		return max(1, cint(frappe.get_attr(hooks[-1])(item_code)))
	sales_uom = frappe.db.get_value("Item", item_code, "sales_uom")
	rows = frappe.get_all(
		"UOM Conversion Detail",
		filters={"parenttype": "Item", "parent": item_code},
		fields=["uom", "conversion_factor"],
		order_by="idx",
	)
	named = [r for r in rows if _named_bunch(r.uom, r.conversion_factor)]
	for r in sorted(named, key=lambda r: r.uom != sales_uom):
		return cint(r.conversion_factor)
	return 1


def _named_bunch(uom, factor):
	m = re.search(r"\((\d+)\)", uom or "")
	return bool("bunch" in (uom or "").lower() and m and flt(factor) > 1 and cint(m.group(1)) == flt(factor))


def assert_whole_bunches(item_code, qty, item_name=None):
	bunch = stems_per_bunch(item_code)
	if bunch > 1 and (cint(flt(qty)) != flt(qty) or cint(flt(qty)) % bunch):
		frappe.throw(
			_("{0} is sold in bunches of {1} stems: order {1}, {2}, {3}…").format(
				item_name or frappe.db.get_value("Item", item_code, "item_name") or item_code,
				bunch,
				bunch * 2,
				bunch * 3,
			),
			frappe.ValidationError,
		)
