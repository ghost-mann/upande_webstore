"""Portal claims.

Every document a claim references is validated against the session user's own
customer, both here and again in the Webstore Claim controller.
"""

import frappe
from frappe import _

from upande_webstore.api.cart import _require_login
from upande_webstore.services.claims import get_claimable_documents
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


@frappe.whitelist()
@guard("portal", "claims")
def get_claim(name):
	"""One claim, only if it belongs to the session user's customer."""
	_require_login()
	customer = get_current_customer()
	claim = frappe.get_doc("Webstore Claim", name)
	if claim.customer != customer:
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return claim


def get_claim_options():
	"""Claim types plus the documents this customer may claim against."""
	customer = get_current_customer()
	return {
		"types": list(get_claim_types()),
		"documents": get_claimable_documents(customer),
		"require_document": is_on("require_claim_document"),
		"allow_attachments": is_on("allow_claim_attachments"),
		"max_attachment_mb": get("max_attachment_mb"),
		"support_note": get("support_note"),
	}
