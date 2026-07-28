"""Customer-scoped claim document references.

Every document a claim points at must belong to the claim's own customer. The
portal used to accept the reference as free text, which meant a customer could
name another customer's invoice; validation now happens on the document itself
so it holds however the claim is created.
"""

import frappe
from frappe import _

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


def within_claim_window(doctype, name):
	"""False once a document is older than the claim window."""
	from frappe.utils import add_days, getdate, nowdate

	date_field = CLAIM_DATE_FIELD.get(doctype)
	if not date_field:
		return True
	posted = frappe.db.get_value(doctype, name, date_field)
	if not posted:
		return True
	return getdate(posted) >= getdate(add_days(nowdate(), -get_claim_window_days()))


def get_claimable_documents(customer, limit=40):
	"""{doctype: [names]} the customer may file a claim against.

	Only documents inside the claim window are offered — an invoice older than
	that drops off the list, so customers cannot open a claim on ancient
	billing.
	"""
	from frappe.utils import add_days, nowdate

	cutoff = add_days(nowdate(), -get_claim_window_days())
	out = {}
	for doctype, party_field in CLAIMABLE_DOCTYPES.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		filters = {party_field: customer, "docstatus": 1}
		date_field = CLAIM_DATE_FIELD.get(doctype)
		if date_field:
			filters[date_field] = [">=", cutoff]
		out[doctype] = frappe.get_all(
			doctype,
			filters=filters,
			pluck="name",
			order_by="creation desc",
			limit_page_length=limit,
			ignore_permissions=True,
		)
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
