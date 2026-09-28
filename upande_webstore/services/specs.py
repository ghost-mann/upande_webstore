"""Customer specifications: the packing recipes a farm has agreed per customer.

They live in another app's doctype (upande_packhouse's `Specifications`), so
this module is the only place that reads them, it never writes, and every read
guards on the doctype and the fields it needs actually existing. With the
Customer Specifications module off, nothing here is called at all.

Two things about the live data decide the shape (see the 2026-09-28 spec):

- A spec is ordered either **by the box** — it resolves to one variety at one
  pack rate, so "3 boxes" is a stem quantity — or **by variety**, where the
  buyer enters stems for each primary variety. Box rows are commonly repeated
  once per approved variety, so "one pack rate" means every row agrees, not
  that there is one row.
- Mixed boxes do not state a reliable per-box capacity, so their fill is not
  checked; the colour range and approved varieties are.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

DEFAULT_DOCTYPE = "Specifications"
BOX_ITEM_DOCTYPE = "Spec Box Item"
VARIETY_DOCTYPE = "Spec Approved Variety"

BY_BOX = "box"
BY_VARIETY = "variety"

# how a spec's lines are checked for box fill
WHOLE_BOXES = "whole_boxes"  # every line is whole boxes at one rate
UNCHECKED = "unchecked"  # mixed, or mono with disagreeing rates

MIXED_BOX = "Mixed Box"
MONO_BOX = "Mono Box"

HEADER_FIELDS = (
	"name",
	"spec_name",
	"customer",
	"status",
	"valid_from",
	"expiry_date",
	"box_type",
	"box_assortment",
	"min_colours_per_box",
	"max_colours_per_box",
)
BOX_ITEM_FIELDS = ("parent", "length", "stems_per_bunch", "bunches_per_box", "pack_rate")
VARIETY_FIELDS = ("parent", "idx", "bunch_id", "colour", "variety", "is_primary")


def spec_doctype():
	# a Single's new Data field reads blank until the form is saved once, so
	# the shipped default has to be applied here as well as on the DocType
	from upande_webstore.services.settings import get_settings

	return (get_settings().get("spec_doctype") or "").strip() or DEFAULT_DOCTYPE


def availability():
	"""(ok, reason). ok means the configured doctype can be read as a spec."""
	doctype = spec_doctype()
	if not frappe.db.exists("DocType", doctype):
		return False, _("DocType {0} does not exist on this site.").format(doctype)
	meta = frappe.get_meta(doctype)
	missing = [field for field in HEADER_FIELDS[1:] if not meta.get_field(field)]
	for table, child in (("box_items", BOX_ITEM_DOCTYPE), ("approved_varieties", VARIETY_DOCTYPE)):
		field = meta.get_field(table)
		if not field or field.options != child:
			missing.append(table)
	if missing:
		return False, _("{0} is missing fields the webstore reads: {1}.").format(
			doctype, ", ".join(missing)
		)
	return True, None


def module_on():
	"""The module switch is on and there is something it can read."""
	from upande_webstore.theme.features import enabled

	return bool(enabled()["customer_specs"]) and availability()[0]


def visible_names(customer):
	"""Names of this customer's active, in-date specs."""
	if not customer or not module_on():
		return []
	doctype = spec_doctype()
	today = getdate(nowdate())
	rows = frappe.get_all(
		doctype,
		filters={"customer": customer, "status": "Active"},
		fields=["name", "valid_from", "expiry_date"],
		order_by="name asc",
	)
	in_date = [
		row.name
		for row in rows
		if (not row.valid_from or getdate(row.valid_from) <= today)
		and (not row.expiry_date or getdate(row.expiry_date) >= today)
	]
	if not in_date:
		return []
	# a spec with no primary variety has nothing to order, so it is not shown
	# (and not counted on the store's switch)
	with_primary = set(
		frappe.get_all(
			VARIETY_DOCTYPE,
			filters={"parent": ["in", in_date], "parenttype": doctype, "is_primary": 1},
			pluck="parent",
			distinct=True,
		)
	)
	return [name for name in in_date if name in with_primary]


def _children(doctype, fields, parents):
	if not parents:
		return {}
	out = {}
	for row in frappe.get_all(
		doctype,
		filters={"parent": ["in", list(parents)], "parenttype": spec_doctype()},
		fields=list(fields),
		order_by="idx asc",
	):
		out.setdefault(row.parent, []).append(row)
	return out


def _item_names(item_codes):
	if not item_codes:
		return {}
	return {
		row.name: row.item_name
		for row in frappe.get_all(
			"Item", filters={"name": ["in", list(item_codes)]}, fields=["name", "item_name"]
		)
	}


def describe(header, box_items, varieties, price=None):
	"""One spec as the storefront needs it. Pure apart from `price`.

	price: callable(item_code, length) -> {"rate", "currency"}; None skips pricing.
	"""
	lengths = sorted({row.length for row in box_items if row.length})
	# one length is what a length-priced site can price; a spec spanning
	# several has no single answer, so its lines fall back to the plain price
	price_length = lengths[0] if len(lengths) == 1 else None
	rates = {cint(row.pack_rate) for row in box_items if cint(row.pack_rate) > 0}
	one_rate = rates.pop() if len(rates) == 1 else 0

	# one row per primary variety; the same variety filling two slots is still
	# one thing to order, so its colours are joined rather than listed twice
	primaries = {}
	for row in varieties:
		if not cint(row.is_primary) or not row.variety:
			continue
		entry = primaries.setdefault(row.variety, {"item_code": row.variety, "colours": []})
		if row.colour and row.colour not in entry["colours"]:
			entry["colours"].append(row.colour)

	if len(primaries) == 1 and one_rate:
		mode, fill = BY_BOX, WHOLE_BOXES
	elif header.box_assortment == MONO_BOX and one_rate:
		mode, fill = BY_VARIETY, WHOLE_BOXES
	else:
		mode, fill = BY_VARIETY, UNCHECKED

	lines = []
	names = _item_names(primaries)
	for entry in primaries.values():
		line = dict(
			entry,
			item_name=names.get(entry["item_code"]) or entry["item_code"],
			colour=", ".join(entry["colours"]),
		)
		if price:
			quoted = price(entry["item_code"], price_length)
			if flt(quoted.get("rate")) <= 0:
				# no price for this customer: not offered, rather than ordered at 0
				continue
			line["rate"] = flt(quoted["rate"])
			line["currency"] = quoted.get("currency")
		lines.append(line)

	return frappe._dict(
		name=header.name,
		spec_name=header.spec_name or header.name,
		box_type=header.box_type,
		box_assortment=header.box_assortment,
		length=", ".join(lengths),
		price_length=price_length,
		mode=mode,
		fill=fill,
		pack_rate=one_rate if fill == WHOLE_BOXES else 0,
		min_colours=cint(header.min_colours_per_box),
		max_colours=cint(header.max_colours_per_box),
		lines=lines,
		item_codes=[line["item_code"] for line in lines],
	)


def _load(names, priced):
	if not names:
		return []
	from upande_webstore.services.pricing import get_item_price

	headers = frappe.get_all(
		spec_doctype(), filters={"name": ["in", names]}, fields=list(HEADER_FIELDS), order_by="name asc"
	)
	box_items = _children(BOX_ITEM_DOCTYPE, BOX_ITEM_FIELDS, names)
	varieties = _children(VARIETY_DOCTYPE, VARIETY_FIELDS, names)
	cache = {}

	def price(item_code, length):
		if (item_code, length) not in cache:
			cache[(item_code, length)] = get_item_price(item_code, length=length)
		return cache[(item_code, length)]

	out = []
	for header in headers:
		spec = describe(
			header,
			box_items.get(header.name, []),
			varieties.get(header.name, []),
			price if priced else None,
		)
		if spec.lines:
			out.append(spec)
	return out


def my_specs(customer=None):
	"""The session customer's orderable specs, priced for them."""
	from upande_webstore.services.pricing import get_customer

	customer = customer or get_customer()
	return _load(visible_names(customer), priced=True)


def count_for(customer=None):
	from upande_webstore.services.pricing import get_customer

	return len(visible_names(customer or get_customer()))


def get_for_customer(name, customer=None):
	"""One spec if this customer may order it, else None.

	Same answer for "not yours", "expired" and "does not exist" on purpose:
	which specs another customer holds is not something to reveal.
	"""
	from upande_webstore.services.pricing import get_customer

	customer = customer or get_customer()
	if not name or name not in visible_names(customer):
		return None
	specs = _load([name], priced=True)
	return specs[0] if specs else None


def not_available():
	return _("This specification is not available.")


def check_lines(spec, lines):
	"""Problems with the lines ordered under one spec. Empty means fine.

	lines: [{"item_code", "qty", "colour"?}] — qty in stems.
	"""
	problems = []
	allowed = {line["item_code"]: line for line in spec.lines}
	for line in lines:
		if line["item_code"] not in allowed:
			problems.append(
				_("{0}: {1} is not an approved variety of this specification.").format(
					spec.spec_name, line["item_code"]
				)
			)
			continue
		if spec.fill == WHOLE_BOXES and flt(line["qty"]) % spec.pack_rate:
			problems.append(
				_("{0}: {1} stems of {2} does not fill whole boxes ({3} per box).").format(
					spec.spec_name,
					int(flt(line["qty"])),
					allowed[line["item_code"]]["item_name"],
					spec.pack_rate,
				)
			)
	if spec.fill == UNCHECKED and (spec.min_colours or spec.max_colours):
		colours = set()
		for line in lines:
			entry = allowed.get(line["item_code"])
			if entry and flt(line["qty"]) > 0:
				colours.update(entry["colours"] or [line["item_code"]])
		low = spec.min_colours or 0
		high = spec.max_colours or 0
		if (low and len(colours) < low) or (high and len(colours) > high):
			problems.append(
				_("{0}: choose {1} colours; you have {2}.").format(
					spec.spec_name,
					str(low) if low == high else _("{0} to {1}").format(low or 1, high or "any"),
					len(colours),
				)
			)
	return problems


def boxes_in(spec, stems):
	"""Whole boxes in a stem quantity under this spec, or 0 when unknown."""
	if spec.fill != WHOLE_BOXES or not spec.pack_rate:
		return 0
	stems = flt(stems)
	return int(stems // spec.pack_rate) if stems % spec.pack_rate == 0 else 0


def source_summary():
	"""What the desk panel under the module switch shows."""
	ok, reason = availability()
	doctype = spec_doctype()
	if not ok:
		return {"doctype": doctype, "available": False, "reason": reason}
	return {
		"doctype": doctype,
		"available": True,
		"active": frappe.db.count(doctype, {"status": "Active"}),
		"customers": len(
			frappe.get_all(
				doctype,
				filters={"status": "Active", "customer": ["is", "set"]},
				pluck="customer",
				distinct=True,
			)
		),
	}
