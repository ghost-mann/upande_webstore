"""Stock allocation: how many stems of each variety+length the webstore may sell.

Staff set an allocation per variant on Webstore Settings. Webstore quotations
and sales orders (order_type "Shopping Cart") use it up. What each document
holds is kept in `Webstore Allocation Entry`, one row per (document, item),
and that log is the only source of truth for Taken: the `taken` column on the
settings row is a display copy. The Single is cached and a desk form can be
saved from a stale copy, so nothing here ever reads Taken from it.

Every read that decides whether stems are free is a locking read. Checkout
does many plain reads before it gets here, and under InnoDB's repeatable read
a plain SELECT would answer from that earlier snapshot and miss an order
committed by a concurrent checkout in between.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

SETTINGS = "Webstore Settings"
ROW = "Webstore Stock Allocation"
ENTRY = "Webstore Allocation Entry"
WEBSTORE_ORDER_TYPE = "Shopping Cart"
TRACKED_DOCTYPES = ("Quotation", "Sales Order")


def enabled():
	return bool(frappe.db.get_single_value(SETTINGS, "enable_stock_allocation"))


def _global_lock():
	"""One lock in front of every allocation writer.

	Per-row and gap locks taken in different orders by concurrent checkouts,
	order syncs and settings saves can deadlock; queueing them all on the
	Single's switch row cannot. Held until the transaction commits."""
	frappe.db.sql(
		"select value from `tabSingles` where doctype=%s and field='enable_stock_allocation' for update",
		SETTINGS,
	)


def _row_filters(item_code):
	return {"parent": SETTINGS, "parenttype": SETTINGS, "parentfield": "stock_allocations", "item_code": item_code}


def row_for(item_code, for_update=False):
	"""The allocation row for a variant, read fresh from the database."""
	return frappe.db.get_value(
		ROW, _row_filters(item_code), ["name", "allocated"], as_dict=True, for_update=for_update
	)


def tracked_items():
	return set(
		frappe.get_all(
			ROW,
			filters={"parent": SETTINGS, "parenttype": SETTINGS, "parentfield": "stock_allocations"},
			pluck="item_code",
		)
	) - {None, ""}


def taken(item_code, for_update=False):
	sql = f"select coalesce(sum(qty), 0) from `tab{ENTRY}` where item_code = %s"
	if for_update:
		sql += " for update"
	return flt(frappe.db.sql(sql, (item_code,))[0][0])


def remaining(item_code, for_update=False):
	"""Allocated minus taken; None when the item has no allocation row."""
	row = row_for(item_code, for_update=for_update)
	if not row:
		return None
	return flt(row.allocated) - taken(item_code, for_update=for_update)


def refresh_display(item_codes=None):
	"""Copy Taken/Remaining onto the settings rows so staff can see them."""
	rows = frappe.get_all(
		ROW,
		filters={"parent": SETTINGS, "parenttype": SETTINGS, "parentfield": "stock_allocations"},
		fields=["name", "item_code", "allocated"],
	)
	for row in rows:
		if item_codes is not None and row.item_code not in item_codes:
			continue
		used = taken(row.item_code)
		frappe.db.set_value(
			ROW, row.name, {"taken": used, "remaining": flt(row.allocated) - used}, update_modified=False
		)


# --- checkout ---------------------------------------------------------------


def lock_and_check(lines):
	"""Refuse a customer checkout that would go past what remains.

	`lines` is an iterable of (item_code, qty). Locks each allocation row until
	the request's transaction commits, so two buyers can't both take the same
	last stems: the second waits here, then sees the first one's order.
	"""
	if not enabled():
		return
	_global_lock()
	wanted = {}
	for item_code, qty in lines:
		wanted[item_code] = wanted.get(item_code, 0) + flt(qty)
	for item_code in sorted(wanted):  # one lock order everywhere: no deadlocks
		left = remaining(item_code, for_update=True)
		if left is None:
			continue  # not an allocated length; the stock check already refused it
		if wanted[item_code] > left:
			name = frappe.db.get_value("Item", item_code, "item_name") or item_code
			if _may_show(left):
				message = _("Only {0} left of {1}. Please adjust your cart.").format(int(max(left, 0)), name)
			else:
				message = _("{0} is not available in the requested quantity.").format(name)
			frappe.throw(message, frappe.ValidationError)


def _may_show(qty):
	"""A number goes to the buyer only where the display mode would show it."""
	from upande_webstore.services.settings import get_settings

	settings = get_settings()
	if settings.stock_display == "Exact Quantity":
		return True
	return settings.stock_display == "Low Stock Warning" and qty <= (settings.get("low_stock_threshold") or 0)


# --- keeping entries in step with documents ----------------------------------


def is_webstore_document(doc):
	return doc.doctype in TRACKED_DOCTYPES and doc.get("order_type") == WEBSTORE_ORDER_TYPE


def _line_totals(doc):
	totals = {}
	for row in doc.get("items") or []:
		if row.item_code:
			totals[row.item_code] = totals.get(row.item_code, 0) + flt(row.stock_qty or row.qty)
	return totals


def held_by_orders(quotation_name, exclude_order=None):
	"""Stems that sales orders made from this quotation now hold themselves.

	`exclude_order` is a sales order being deleted: its rows are still in the
	database while its on_trash runs, but it no longer holds anything."""
	filters = {"prevdoc_docname": quotation_name, "docstatus": ["<", 2]}
	if exclude_order:
		filters["parent"] = ["!=", exclude_order]
	held = {}
	for row in frappe.get_all(
		"Sales Order Item",
		filters=filters,
		fields=["item_code", "qty", "stock_qty"],
	):
		held[row.item_code] = held.get(row.item_code, 0) + flt(row.stock_qty or row.qty)
	return held


def wanted(doc, deleted=False, exclude_order=None):
	"""What this document holds right now, per item_code."""
	if deleted or doc.docstatus == 2:
		return {}
	if doc.doctype == "Sales Order":
		if doc.get("status") == "Closed":
			return {}
		return _line_totals(doc)
	if doc.get("status") in ("Lost", "Expired"):
		return {}
	if (
		doc.docstatus == 1
		and doc.get("valid_till")
		and getdate(doc.valid_till) < getdate(nowdate())
		and doc.get("status") not in ("Ordered", "Partially Ordered")
	):
		return {}  # ERPNext's own expiry rule; its daily job may not have run yet
	totals = _line_totals(doc)
	for item_code, qty in held_by_orders(doc.name, exclude_order).items():
		if item_code in totals:
			totals[item_code] = max(0, totals[item_code] - qty)
	return totals


def sync(doc, deleted=False, exclude_order=None):
	"""Make this document's Entries match what it holds. Never refuses:
	staff on the desk may go past an allocation."""
	if not enabled() or not is_webstore_document(doc):
		return
	tracked = tracked_items()
	want = {k: v for k, v in wanted(doc, deleted=deleted, exclude_order=exclude_order).items() if k in tracked and v > 0}
	have = {
		e.item_code: e
		for e in frappe.get_all(
			ENTRY,
			filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
			fields=["name", "item_code", "qty"],
		)
	}
	changed = set()
	for item_code in sorted(set(want) | set(have)):
		new_qty = want.get(item_code, 0)
		entry = have.get(item_code)
		if entry and flt(entry.qty) == new_qty:
			continue
		if not changed:
			_global_lock()
		if entry and new_qty:
			frappe.db.set_value(ENTRY, entry.name, "qty", new_qty)
		elif entry:
			frappe.db.delete(ENTRY, {"name": entry.name})
		else:
			frappe.get_doc(
				{
					"doctype": ENTRY,
					"reference_doctype": doc.doctype,
					"reference_name": doc.name,
					"item_code": item_code,
					"qty": new_qty,
				}
			).insert(ignore_permissions=True)
		changed.add(item_code)
	if changed:
		refresh_display(changed)

	if doc.doctype == "Sales Order":
		# the quotation's hold moves to (or back from) this order - including a
		# quotation whose line staff just removed from it
		before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
		lines = list(doc.get("items") or []) + list((before.get("items") or []) if before else [])
		for quotation in sorted({r.prevdoc_docname for r in lines if r.get("prevdoc_docname")}):
			if frappe.db.exists("Quotation", quotation):
				sync(frappe.get_doc("Quotation", quotation), exclude_order=doc.name if deleted else None)


def on_change(doc, method=None):
	# frappe's delete_doc runs on_change straight after on_trash, with in_delete set
	sync(doc, deleted=bool(doc.flags.in_delete))


def on_trash(doc, method=None):
	sync(doc, deleted=True)


# --- staff tools ---------------------------------------------------------------


def _open_webstore_documents():
	docs = []
	for doctype, closed in (("Quotation", ["Lost", "Expired"]), ("Sales Order", ["Closed"])):
		docs += [
			(doctype, name)
			for name in frappe.get_all(
				doctype,
				filters={
					"order_type": WEBSTORE_ORDER_TYPE,
					"docstatus": ["<", 2],
					"status": ["not in", closed],
				},
				pluck="name",
			)
		]
	return docs


def _resync(pairs):
	for doctype, name in pairs:
		if frappe.db.exists(doctype, name):
			sync(frappe.get_doc(doctype, name))
		else:
			frappe.db.delete(ENTRY, {"reference_doctype": doctype, "reference_name": name})


def _documents_with_entries():
	return {
		(e.reference_doctype, e.reference_name)
		for e in frappe.get_all(ENTRY, fields=["reference_doctype", "reference_name"])
	}


def recount():
	"""Rebuild every Entry from the open webstore documents."""
	if not enabled():
		return
	_global_lock()
	_resync(sorted(_documents_with_entries() | set(_open_webstore_documents())))
	tracked = tracked_items()
	frappe.db.delete(ENTRY, {"item_code": ["not in", list(tracked) or [""]]})
	refresh_display()


def reset():
	"""Start a new allocation period: nothing counts as taken."""
	_global_lock()
	frappe.db.delete(ENTRY)
	refresh_display()


def daily():
	"""ERPNext expires quotations with a bare SQL update, which fires no hook;
	a full recount also repairs anything a missed hook left behind."""
	recount()


@frappe.whitelist(methods=["POST"])
def recount_allocations():
	frappe.only_for("System Manager")
	recount()
	return True


@frappe.whitelist(methods=["POST"])
def reset_allocations():
	frappe.only_for("System Manager")
	reset()
	return True
