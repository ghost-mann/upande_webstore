"""Box arithmetic for stem orders.

Pure maths plus a few thin reads. Deliberately knows nothing about carts or
documents, so the arithmetic can be tested without building either.

Where box types live differs per farm, so one resolver answers it once per
request and every read goes through it. Karen Roses runs a populated `Box Type`
doctype whose `custom_stem_capacity` is the pack rate; Mona flags Items with
`custom_is_box` and `custom_pack_rate`. Both are other apps' schema, so every
read guards on the doctype and the field actually existing: this app must work
on a farm that has neither.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_webstore.services.settings import get_settings

BOX_FLAG = "custom_is_box"
BOX_RATE = "custom_pack_rate"
BOX_TYPE_DOCTYPE = "Box Type"
BOX_TYPE_CAPACITY = "custom_stem_capacity"

_UNSET = object()


def packing_enabled():
	return bool(int(flt(get_settings().get("enable_box_packing"))))


def get_default_box_type():
	return get_settings().get("default_box_type") or None


def get_minimum_order_stems():
	return int(flt(get_settings().get("minimum_order_stems")))


def get_box_source():
	"""Which doctype this site's box types live in, or None.

	Resolved once per request: it is a property of the site's schema, not of the
	cart being priced.
	"""
	if getattr(frappe.local, "webstore_box_source", _UNSET) is _UNSET:
		frappe.local.webstore_box_source = _resolve_box_source()
	return frappe.local.webstore_box_source


def clear_box_source_cache():
	"""Tests flip the source within one request; production never does."""
	frappe.local.webstore_box_source = _UNSET


def _resolve_box_source():
	# `filters` and `candidate_filters` must map a fieldname to a plain scalar.
	# They are passed straight to frappe.get_all, which would also accept the
	# operator form (`{"qty": [">", 0]}`), but get_pack_rate and
	# get_unusable_box_types compare each value with int(flt(...)) row by row —
	# a list there raises TypeError rather than filtering. Widening this needs
	# those two comparisons taught the operator form first.
	if _box_type_doctype_populated():
		return frappe._dict(
			doctype=BOX_TYPE_DOCTYPE,
			rate_field=BOX_TYPE_CAPACITY,
			label_field="box_type" if frappe.get_meta(BOX_TYPE_DOCTYPE).get_field("box_type") else "name",
			filters={},
			candidate_filters={},
		)
	if _item_has_box_fields():
		return frappe._dict(
			doctype="Item",
			rate_field=BOX_RATE,
			label_field="item_name",
			filters={BOX_FLAG: 1, "disabled": 0},
			candidate_filters={BOX_FLAG: 1},
		)
	return None


def _box_type_doctype_populated():
	"""A `Box Type` that exists but holds no usable capacity falls through.

	Mona has an empty one; treating that as the source would silently disable
	packing on a farm whose real rates are on Items.
	"""
	if not frappe.db.exists("DocType", BOX_TYPE_DOCTYPE):
		return False
	if not frappe.get_meta(BOX_TYPE_DOCTYPE).get_field(BOX_TYPE_CAPACITY):
		return False
	return bool(
		frappe.get_all(BOX_TYPE_DOCTYPE, filters={BOX_TYPE_CAPACITY: [">", 0]}, limit=1)
	)


def _item_has_box_fields():
	meta = frappe.get_meta("Item")
	return bool(meta.get_field(BOX_FLAG)) and bool(meta.get_field(BOX_RATE))


def source_label():
	"""Plain words naming the source, for the desk panel's header."""
	source = get_box_source()
	if not source:
		return _("no box type source on this site")
	if source.doctype == BOX_TYPE_DOCTYPE:
		return _("Box Type records with a stem capacity above zero")
	return _("Items flagged Is Box with a pack rate above zero")


def box_source_hint():
	"""A whole sentence for validation messages, not a noun phrase.

	`source_label` names a source that exists; appending it to "Box types come
	from ..." reads as nonsense when there is no source at all ("come from no box
	type source on this site") and names no next action. An operator who mistypes
	a box on a site with no source needs to be told what to create, so the
	no-source case gets its own sentence rather than a label.
	"""
	source = get_box_source()
	if not source:
		return _(
			"This site has no box type source yet: either Box Type records with a "
			"stem capacity, or Items with Is Box ticked and a pack rate."
		)
	return _("Box types come from {0}.").format(source_label())


def _source_fields(source):
	return [
		"name",
		f"{source.label_field} as box_name",
		f"{source.rate_field} as pack_rate",
	]


def get_box_types():
	"""Boxes the farm can actually pack into: usable, rate above zero."""
	source = get_box_source()
	if not source:
		return []
	rows = frappe.get_all(
		source.doctype,
		filters=source.filters,
		fields=_source_fields(source),
		order_by=f"{source.label_field} asc",
	)
	return [
		{
			"box_type": row.name,
			"box_name": row.box_name or row.name,
			"pack_rate": int(flt(row.pack_rate)),
		}
		for row in rows
		if flt(row.pack_rate) > 0
	]


def get_unusable_box_types():
	"""Boxes the site defines that the storefront ignores, and why.

	Invisible otherwise: `get_box_types` simply returns a shorter list, which
	reads as a setting being ignored rather than a rate being missing.
	"""
	source = get_box_source()
	if not source:
		return []
	rows = frappe.get_all(
		source.doctype,
		filters=source.candidate_filters,
		fields=_source_fields(source) + list(source.filters),
	)
	out = []
	for row in rows:
		reasons = []
		if flt(row.pack_rate) <= 0:
			reasons.append(_("no pack rate entered"))
		for field, expected in source.filters.items():
			if int(flt(row.get(field))) != int(flt(expected)):
				reasons.append(_("disabled") if field == "disabled" else _("not flagged as a box"))
		if reasons:
			out.append(
				{
					"box_type": row.name,
					"box_name": row.box_name or row.name,
					"reasons": reasons,
				}
			)
	return out


def get_pack_rate(box):
	"""Stems per box, or 0 when the box is missing, unusable, or has no rate.
	0 always means 'do not validate'."""
	source = get_box_source()
	if not box or not source:
		return 0
	row = frappe.db.get_value(
		source.doctype, box, [source.rate_field] + list(source.filters), as_dict=True
	)
	if not row:
		return 0
	for field, expected in source.filters.items():
		if int(flt(row.get(field))) != int(flt(expected)):
			return 0
	rate = flt(row.get(source.rate_field))
	return int(rate) if rate > 0 else 0


def get_product_box_type(item_code):
	"""The box a product ships in, falling back to the farm default.

	The product supplies the default — it knows a 120cm stem will not fit a
	100x33x20 box — and the buyer may override it per basket line. Mirrors
	`Website Item.custom_box_type`, which is how Mona already models this.
	"""
	box = frappe.db.get_value("Webstore Product", {"item": item_code}, "box_type")
	if box and is_usable_box(box):
		return box
	default = get_default_box_type()
	return default if default and is_usable_box(default) else None


def is_usable_box(box):
	return get_pack_rate(box) > 0


def box_label(box):
	if not box:
		return _("no box type")
	source = get_box_source()
	if not source:
		return box
	return frappe.db.get_value(source.doctype, box, source.label_field) or box


def compute_boxes(qty, pack_rate):
	"""How a stem quantity divides into whole boxes.

	A pack_rate of 0 reports is_full=True on purpose: an unconfigured box must
	never block an order.
	"""
	qty = flt(qty)
	pack_rate = int(flt(pack_rate))
	if pack_rate <= 0:
		return {
			"pack_rate": 0,
			"boxes": 0,
			"remainder": 0,
			"is_full": True,
			"nearest_down": None,
			"nearest_up": None,
		}
	boxes = int(qty // pack_rate)
	remainder = qty - boxes * pack_rate
	return {
		"pack_rate": pack_rate,
		"boxes": boxes,
		"remainder": remainder,
		"is_full": remainder == 0,
		"nearest_down": boxes * pack_rate,
		"nearest_up": (boxes + 1) * pack_rate,
	}


def group_by_box_type(lines):
	"""Sum stems per box type.

	Boxes are mixed in practice — a 50-stem line shares a box with other
	varieties — so whole-box fill is a property of the group, not the line.

	lines: [{"item_code": str, "qty": float, "box_type": str | None}]
	"""
	groups = {}
	for line in lines:
		box_type = line.get("box_type") or None
		group = groups.setdefault(
			box_type, {"box_type": box_type, "stems": 0, "item_codes": []}
		)
		group["stems"] = flt(group["stems"]) + flt(line.get("qty"))
		group["item_codes"].append(line.get("item_code"))
	for group in groups.values():
		group.update(compute_boxes(group["stems"], get_pack_rate(group["box_type"])))
	return groups


def find_problems(groups, total_stems, minimum_stems):
	"""Human-readable reasons this cart cannot be ordered. Empty means it can.

	Both checks are collected rather than raised one at a time, so a buyer is
	never sent to fix the minimum only to be blocked again on box fill.
	"""
	problems = []
	for group in sorted(groups.values(), key=lambda g: (g["box_type"] or "")):
		if group["pack_rate"] <= 0 or group["is_full"]:
			continue
		label = box_label(group["box_type"])
		if group["boxes"] == 0:
			problems.append(
				_("{0}: {1} stems is less than one full box ({2} per box). Order at least {2}.").format(
					label, int(group["stems"]), group["pack_rate"]
				)
			)
		else:
			lines = len(group["item_codes"])
			where = (
				_("{0} stems across {1} lines").format(int(group["stems"]), lines)
				if lines > 1
				else _("{0} stems").format(int(group["stems"]))
			)
			problems.append(
				_("{0}: {1} does not fill whole boxes ({2} per box). Use {3} or {4}.").format(
					label,
					where,
					group["pack_rate"],
					_("{0} ({1} boxes)").format(int(group["nearest_down"]), group["boxes"])
					if group["boxes"] != 1
					else _("{0} (1 box)").format(int(group["nearest_down"])),
					_("{0} ({1} boxes)").format(int(group["nearest_up"]), group["boxes"] + 1)
					if group["boxes"] + 1 != 1
					else _("{0} (1 box)").format(int(group["nearest_up"])),
				)
			)
	if minimum_stems and flt(total_stems) < minimum_stems:
		problems.append(
			_("Minimum order is {0} stems; your cart has {1}.").format(
				minimum_stems, int(flt(total_stems))
			)
		)
	return problems
