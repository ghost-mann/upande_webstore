"""Customer-scoped claim document references.

Every document a claim points at must belong to the claim's own customer. The
portal used to accept the reference as free text, which meant a customer could
name another customer's invoice; validation now happens on the document itself
so it holds however the claim is created.
"""

import frappe
from frappe import _

# claimable doctype -> the field naming the customer on it
CLAIMABLE_DOCTYPES = {
	"Sales Invoice": "customer",
	"Sales Order": "customer",
	"Delivery Note": "customer",
}

CLAIM_TYPES = (
	"Damaged goods",
	"Short delivery",
	"Quality below grade",
	"Billing error",
	"Other",
)


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


def get_claimable_documents(customer, limit=40):
	"""{doctype: [names]} the customer may file a claim against."""
	out = {}
	for doctype, party_field in CLAIMABLE_DOCTYPES.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		out[doctype] = frappe.get_all(
			doctype,
			filters={party_field: customer, "docstatus": 1},
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
