"""Box arithmetic for stem orders.

Pure maths plus a few thin reads. Deliberately knows nothing about carts or
documents, so the arithmetic can be tested without building either.

Box types are Items flagged `custom_is_box` carrying `custom_pack_rate` — the
same records `Pack Box.box_type` links to — rather than a doctype of our own.
Those are another app's custom fields, so every read guards on the field
actually existing: this app must work on a farm that has neither
upande_harvest nor upande_webshop installed.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_webstore.services.settings import get_settings

BOX_FLAG = "custom_is_box"
BOX_RATE = "custom_pack_rate"


def packing_enabled():
	return bool(int(flt(get_settings().get("enable_box_packing"))))


def get_default_box_type():
	return get_settings().get("default_box_type") or None


def get_minimum_order_stems():
	return int(flt(get_settings().get("minimum_order_stems")))


def _item_has_box_fields():
	meta = frappe.get_meta("Item")
	return bool(meta.get_field(BOX_FLAG)) and bool(meta.get_field(BOX_RATE))


def get_box_types():
	"""Boxes the farm can actually pack into: flagged, enabled, rate above zero."""
	if not _item_has_box_fields():
		return []
	rows = frappe.get_all(
		"Item",
		filters={BOX_FLAG: 1, "disabled": 0},
		fields=["name as item_code", "item_name", f"{BOX_RATE} as pack_rate"],
		order_by="item_name asc",
	)
	return [
		{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"pack_rate": int(flt(row.pack_rate)),
		}
		for row in rows
		if flt(row.pack_rate) > 0
	]


def get_pack_rate(box_item):
	"""Stems per box, or 0 when the box is missing, disabled, no longer a box, or
	has no rate entered. 0 always means 'do not validate'."""
	if not box_item or not _item_has_box_fields():
		return 0
	row = frappe.db.get_value(
		"Item", box_item, [BOX_FLAG, BOX_RATE, "disabled"], as_dict=True
	)
	if not row or not int(flt(row.get(BOX_FLAG))) or int(flt(row.get("disabled"))):
		return 0
	rate = flt(row.get(BOX_RATE))
	return int(rate) if rate > 0 else 0


def get_product_box_type(item_code):
	"""The box a product ships in, falling back to the farm default.

	Box type belongs to the product, not the order: a 120cm stem physically will
	not fit a 100x33x20 box, so the buyer never chooses it. Mirrors
	`Website Item.custom_box_type`, which is how Mona already models this.
	"""
	box = frappe.db.get_value("Webstore Product", {"item": item_code}, "box_type")
	if box and is_usable_box(box):
		return box
	default = get_default_box_type()
	return default if default and is_usable_box(default) else None


def is_usable_box(box_item):
	return get_pack_rate(box_item) > 0


def box_label(box_item):
	if not box_item:
		return _("no box type")
	return frappe.db.get_value("Item", box_item, "item_name") or box_item


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
