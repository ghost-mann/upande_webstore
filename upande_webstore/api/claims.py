"""Portal claims.

Every document a claim references is validated against the session user's own
customer, both here and again in the Webstore Claim controller.
"""

import frappe
from frappe import _

from upande_webstore.api.cart import _require_login
from upande_webstore.services.claims import (
	get_claim_window_days,
	get_claimable_documents,
	is_within_window,
)
from upande_webstore.services.portal_settings import get, get_claim_types, is_on
from upande_webstore.services.portal import get_current_customer
from upande_webstore.theme.features import guard

CLAIM_FIELDS = (
	"name",
	"claim_type",
	"status",
	"posting_date",
	"against_doctype",
	"against_document",
	# The outcome and the agreed figure, but never the proposed one: a customer
	# should see what was decided, not commerce's opening position.
	"action",
	"approved_total",
	"credit_note",
	"resolution",
	"description",
)


@frappe.whitelist(methods=["POST"])
@guard("portal", "claims")
def create_claim(claim_type, description, against_doctype=None, against_document=None):
	"""File a claim for the session user's customer."""
	_require_login()
	customer = get_current_customer()

	claim_type = (claim_type or "").strip()
	if claim_type not in get_claim_types():
		frappe.throw(_("Please select what the claim is about."), frappe.ValidationError)
	if not (description or "").strip():
		frappe.throw(_("Please describe the claim."), frappe.ValidationError)
	if is_on("require_claim_document") and not (against_document or "").strip():
		frappe.throw(
			_("Please pick the order, invoice or delivery note this claim is about."),
			frappe.ValidationError,
		)

	claim = frappe.get_doc(
		{
			"doctype": "Webstore Claim",
			"customer": customer,
			"claim_type": claim_type,
			"status": "Open",
			"description": description,
			"against_doctype": (against_doctype or "").strip() or None,
			"against_document": (against_document or "").strip() or None,
			"raised_by": frappe.session.user,
		}
	)
	# the controller re-checks that the referenced document belongs to `customer`
	claim.flags.ignore_permissions = True
	claim.insert()
	return {"name": claim.name}


@frappe.whitelist()
@guard("portal", "claims")
def get_claims(limit=50):
	_require_login()
	customer = get_current_customer()
	return frappe.get_all(
		"Webstore Claim",
		filters={"customer": customer},
		fields=list(CLAIM_FIELDS),
		order_by="creation desc",
		limit_page_length=limit,
		ignore_permissions=True,
	)


#: The child rows the claim page renders, and the only two columns of them it
#: is given. Projected explicitly for the same reason as CLAIM_FIELDS.
CLAIM_RELATED_FIELDS = ("reference_doctype", "reference_name")


@frappe.whitelist()
@guard("portal", "claims")
def get_claim(name):
	"""One claim, only if it belongs to the session user's customer.

	Returns a projection, never the Document. Frappe's own field-level read
	filtering (`Document.apply_fieldlevel_read_permissions`) runs for
	`frappe.client` and `run_doc_method`, not for a custom whitelisted method
	like this one, so returning the doc would hand a logged-in buyer every
	field on it — including `approval_note`, which is internal finance
	commentary at permlevel 1. Building the payload from CLAIM_FIELDS makes the
	buyer-visible set an explicit whitelist: a field added to the doctype later
	cannot leak here by default, it has to be named.
	"""
	_require_login()
	customer = get_current_customer()
	claim = frappe.get_doc("Webstore Claim", name)
	if claim.customer != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	out = frappe._dict({field: claim.get(field) for field in CLAIM_FIELDS})
	# The one child table the claim page renders, projected column by column.
	out.related_documents = [
		frappe._dict({column: row.get(column) for column in CLAIM_RELATED_FIELDS})
		for row in (claim.related_documents or [])
	]
	return out


def get_claim_options():
	"""Claim types plus the documents this customer may claim against."""
	customer = get_current_customer()
	return {
		"types": list(get_claim_types()),
		"documents": get_claimable_documents(customer),
		# the page names the number in the reason it shows against an old invoice
		"claim_window_days": get_claim_window_days(),
		"require_document": is_on("require_claim_document"),
		"allow_attachments": is_on("allow_claim_attachments"),
		"max_attachment_mb": get("max_attachment_mb"),
		"support_note": get("support_note"),
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def claimable_invoice_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query behind a claim's Sales Invoice fields, in the desk.

	`assert_belongs_to` has always refused another customer's invoice, but that
	is a check on save. The Link field itself carried no query, so the desk
	offered every invoice on the site and a sales user learned their mistake
	only after filling the form in. Bound to `against_document` and to the
	child grid's `reference_name`, this narrows the picker to the claim's own
	customer up front.

	Reads through `frappe.get_all` rather than ignoring permissions: a user who
	cannot see a Sales Invoice should not be offered it here either.

	Documents outside the claim window are returned and flagged rather than
	hidden, matching `get_claimable_documents` — hiding them leaves an expired
	invoice indistinguishable from one that has gone missing. The server still
	refuses them on save; this is a label, not a permission.
	"""
	customer = (filters or {}).get("customer")
	if not customer:
		# never fall back to every invoice on the site
		return []

	rows = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": customer,
			"docstatus": 1,
			"name": ["like", f"%{txt or ''}%"],
		},
		fields=["name", "posting_date", "grand_total", "currency"],
		order_by="posting_date desc",
		limit_start=start or 0,
		limit_page_length=page_len or 20,
	)

	window = get_claim_window_days()
	out = []
	for row in rows:
		parts = [frappe.utils.formatdate(row.posting_date)]
		if row.grand_total:
			parts.append(frappe.utils.fmt_money(row.grand_total, currency=row.currency))
		if not is_within_window(row.posting_date):
			parts.append(_("outside the {0}-day claim window").format(window))
		out.append((row.name, " · ".join(parts)))
	return out


@frappe.whitelist(methods=["POST"])
def fetch_invoice_lines(claim):
	"""Copy the referenced invoice's lines onto the claim, replacing any there.

	Deliberately a button rather than automatic: it is an act with a
	consequence, and re-running it discards whatever was filled in.
	"""
	doc = frappe.get_doc("Webstore Claim", claim)
	doc.check_permission("write")

	if not doc.against_document:
		frappe.throw(
			_("Pick the invoice this claim is about before fetching its lines."),
			frappe.ValidationError,
		)

	if doc.approved_total:
		frappe.throw(
			_("This claim has an approved value. Withdraw the approval before "
			  "changing the lines it was given for."),
			frappe.ValidationError,
		)

	from upande_webstore.services.claim_lines import snapshot_rows

	doc.set("lines", [])
	for row in snapshot_rows(doc.against_document):
		doc.append("lines", row)
	doc.save()
	return {"lines": len(doc.lines)}
