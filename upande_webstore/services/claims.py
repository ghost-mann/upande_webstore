"""Customer-scoped claim document references.

Every document a claim points at must belong to the claim's own customer. The
portal used to accept the reference as free text, which meant a customer could
name another customer's invoice; validation now happens on the document itself
so it holds however the claim is created.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

# claimable doctype -> (customer field, date field used for the claim window).
# Invoices only: a claim is about what was billed, and offering orders as well
# let customers claim against a document that may never have shipped.
CLAIMABLE_DOCTYPES = {
	"Sales Invoice": "customer",
}
CLAIM_DATE_FIELD = {"Sales Invoice": "posting_date"}

# The shipped list lives in portal_settings so it is defined once; Portal
# Settings may override it per site.
from upande_webstore.services.portal_settings import SHIPPED_CLAIM_TYPES as CLAIM_TYPES


def assert_belongs_to(customer, doctype, name):
	"""Throw unless `name` is a submitted `doctype` owned by `customer`."""
	if not doctype or not name:
		return
	if doctype not in CLAIMABLE_DOCTYPES:
		frappe.throw(_("You cannot file a claim against {0}.").format(doctype), frappe.ValidationError)
	party_field = CLAIMABLE_DOCTYPES[doctype]
	owner = frappe.db.get_value(doctype, name, party_field)
	if not owner:
		frappe.throw(_("{0} {1} does not exist.").format(_(doctype), name), frappe.ValidationError)
	if owner != customer:
		# deliberately the same message as a missing document: never confirm that
		# another customer's document exists
		frappe.throw(_("{0} {1} does not exist.").format(_(doctype), name), frappe.ValidationError)
	if not within_claim_window(doctype, name):
		frappe.throw(
			_("{0} is older than the {1}-day claim window.").format(name, get_claim_window_days()),
			frappe.ValidationError,
		)


def get_claim_window_days():
	from upande_webstore.services.portal_settings import get_int

	return get_int("claim_window_days")


def claim_cutoff_date():
	"""The oldest document date still inside the claim window."""
	return getdate(add_days(nowdate(), -get_claim_window_days()))


def is_within_window(posted):
	"""A missing date is never held against the customer."""
	return not posted or getdate(posted) >= claim_cutoff_date()


def within_claim_window(doctype, name):
	"""False once a document is older than the claim window."""
	date_field = CLAIM_DATE_FIELD.get(doctype)
	if not date_field:
		return True
	return is_within_window(frappe.db.get_value(doctype, name, date_field))


def get_claimable_documents(customer, limit=40):
	"""{doctype: [{name, date, claimable}]} of the customer's own documents.

	A document past the claim window is still listed, flagged `claimable=False`,
	rather than hidden: dropping it left the customer unable to tell an expired
	invoice from one that had gone missing. The flag is presentation only —
	`assert_belongs_to` re-checks the window on submission, so a client that
	ignores it is refused all the same.
	"""
	out = {}
	for doctype, party_field in CLAIMABLE_DOCTYPES.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		date_field = CLAIM_DATE_FIELD.get(doctype)
		rows = frappe.get_all(
			doctype,
			filters={party_field: customer, "docstatus": 1},
			fields=["name"] + ([f"{date_field} as posted"] if date_field else []),
			order_by="creation desc",
			limit_page_length=limit,
			ignore_permissions=True,
		)
		out[doctype] = [
			{
				"name": row.name,
				"date": row.get("posted"),
				# a doctype with no date field has no window to fall out of
				"claimable": is_within_window(row.get("posted")) if date_field else True,
			}
			for row in rows
		]
	return out


def assert_credit_note(customer, name):
	"""A credit note must be a return invoice belonging to the same customer."""
	if not name:
		return
	row = frappe.db.get_value("Sales Invoice", name, ["customer", "is_return"], as_dict=True)
	if not row:
		frappe.throw(_("Sales Invoice {0} does not exist.").format(name), frappe.ValidationError)
	if not row.is_return:
		frappe.throw(
			_("{0} is not a credit note. Raise one from the invoice with Create → Return / Credit Note.").format(name),
			frappe.ValidationError,
		)
	if row.customer != customer:
		frappe.throw(
			_("Credit note {0} belongs to a different customer.").format(name), frappe.ValidationError
		)
