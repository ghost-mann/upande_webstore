import frappe
from frappe.utils import add_months, formatdate, get_first_day, nowdate

from upande_webstore.services.portal import get_current_customer

QUOTATION_MIX_BUCKETS = (
	("Open", ("Open", "Replied")),
	("Accepted", ("Ordered", "Partially Ordered")),
	("Declined", ("Lost", "Cancelled")),
	("Expired", ("Expired",)),
)

ORDER_DONE_STATUSES = ("Completed", "Closed", "Cancelled")


def get_monthly_spend(months=12):
	"""Per-month invoiced vs paid totals for the session customer,
	oldest first: [{"key": "2026-07", "label": "Jul", "invoiced": x, "paid": y}]."""
	customer = get_current_customer()
	start = get_first_day(add_months(nowdate(), -(months - 1)))
	buckets = {}
	series = []
	for i in range(months):
		month_start = add_months(start, i)
		key = formatdate(month_start, "yyyy-MM")
		bucket = {"key": key, "label": formatdate(month_start, "MMM"), "invoiced": 0.0, "paid": 0.0}
		buckets[key] = bucket
		series.append(bucket)
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, "posting_date": [">=", start]},
		fields=["posting_date", "grand_total", "outstanding_amount"],
		limit_page_length=0,
	)
	for row in rows:
		bucket = buckets.get(formatdate(row.posting_date, "yyyy-MM"))
		if bucket:
			bucket["invoiced"] += float(row.grand_total or 0)
			bucket["paid"] += float(row.grand_total or 0) - float(row.outstanding_amount or 0)
	return series


def get_spend_totals(months=12):
	"""Invoiced total of the last `months` months vs the `months` before them."""
	customer = get_current_customer()
	current_start = get_first_day(add_months(nowdate(), -(months - 1)))
	previous_start = add_months(current_start, -months)
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, "posting_date": [">=", previous_start]},
		fields=["posting_date", "grand_total"],
		limit_page_length=0,
	)
	current = previous = 0.0
	for row in rows:
		if str(row.posting_date) >= str(current_start):
			current += float(row.grand_total or 0)
		else:
			previous += float(row.grand_total or 0)
	pct_change = round((current - previous) / previous * 100, 1) if previous else None
	return {"current": current, "previous": previous, "pct_change": pct_change}


def get_quotation_mix():
	"""Submitted quotation counts bucketed for the status donut."""
	customer = get_current_customer()
	rows = frappe.get_all(
		"Quotation",
		filters={"party_name": customer, "quotation_to": "Customer", "docstatus": 1},
		fields=["status"],
		limit_page_length=0,
	)
	counts = {label: 0 for label, _statuses in QUOTATION_MIX_BUCKETS}
	for row in rows:
		for label, statuses in QUOTATION_MIX_BUCKETS:
			if row.status in statuses:
				counts[label] += 1
				break
	return counts


def get_orders_in_progress_count():
	customer = get_current_customer()
	return frappe.db.count(
		"Sales Order",
		{"customer": customer, "docstatus": 1, "status": ["not in", list(ORDER_DONE_STATUSES)]},
	)


def get_top_items(limit=5):
	"""Most-ordered items (by qty) across the customer's submitted orders,
	with the webstore route when the item is published."""
	customer = get_current_customer()
	rows = frappe.db.sql(
		"""
		select soi.item_code, soi.item_name,
			sum(soi.qty) as qty, sum(soi.amount) as amount,
			count(distinct so.name) as orders
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		where so.customer = %(customer)s and so.docstatus = 1
		group by soi.item_code, soi.item_name
		order by qty desc
		limit %(limit)s
		""",
		{"customer": customer, "limit": int(limit)},
		as_dict=True,
	)
	if rows:
		routes = dict(
			frappe.get_all(
				"Webstore Product",
				filters={"item": ["in", [row.item_code for row in rows]], "published": 1},
				fields=["item", "route"],
				as_list=True,
			)
		)
		for row in rows:
			row.route = routes.get(row.item_code)
	return rows


def get_sidebar_counts():
	"""Cheap badge counts for the portal sidebar."""
	customer = get_current_customer()
	return {
		"open_quotations": frappe.db.count(
			"Quotation",
			{
				"party_name": customer,
				"quotation_to": "Customer",
				"docstatus": 1,
				"status": ["not in", ["Lost", "Ordered", "Expired", "Cancelled"]],
			},
		),
		"unpaid_invoices": frappe.db.count(
			"Sales Invoice",
			{"customer": customer, "docstatus": 1, "outstanding_amount": [">", 0]},
		),
		"orders_in_progress": get_orders_in_progress_count(),
	}


def get_customer_addresses(customer):
	address_names = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"},
		pluck="parent",
	)
	if not address_names:
		return []
	return frappe.get_all(
		"Address",
		filters={"name": ["in", address_names]},
		fields=["name", "address_title", "address_line1", "address_line2", "city", "country", "phone"],
		order_by="modified desc",
	)
