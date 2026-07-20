import frappe

from upande_webstore.services.portal import get_current_customer


def get_statement(from_date, to_date):
	customer = get_current_customer()
	base_filters = {
		"party_type": "Customer",
		"party": customer,
		"is_cancelled": 0,
	}
	opening_rows = frappe.get_all(
		"GL Entry",
		filters={**base_filters, "posting_date": ["<", from_date]},
		fields=["debit", "credit"],
		limit_page_length=0,
	)
	opening = float(sum(row.debit - row.credit for row in opening_rows))
	entries = frappe.get_all(
		"GL Entry",
		filters={**base_filters, "posting_date": ["between", [from_date, to_date]]},
		fields=["posting_date", "voucher_type", "voucher_no", "debit", "credit"],
		order_by="posting_date asc, creation asc",
		limit_page_length=0,
	)
	balance = opening
	rows = []
	for entry in entries:
		balance += float(entry.debit) - float(entry.credit)
		rows.append({
			"posting_date": entry.posting_date,
			"voucher_type": entry.voucher_type,
			"voucher_no": entry.voucher_no,
			"debit": float(entry.debit),
			"credit": float(entry.credit),
			"balance": balance,
		})
	return {"opening": opening, "closing": balance, "rows": rows}
