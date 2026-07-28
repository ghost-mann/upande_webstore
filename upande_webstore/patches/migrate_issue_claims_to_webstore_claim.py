"""Move Issue-based claims onto the Webstore Claim doctype.

Claims used to be Issues with issue_type "Claim" and the referenced document
stored as free text inside the description — unvalidated, so it could name any
document. Each one becomes a Webstore Claim; the old reference is only promoted
to a real link when it resolves to a document the same customer owns, and is
otherwise left in the description rather than silently dropped.

The source Issue is kept and recorded in `legacy_issue`, which also makes this
patch idempotent.
"""

import frappe

from upande_webstore.services.claims import CLAIMABLE_DOCTYPES, CLAIM_TYPES

LEGACY_ISSUE_TYPE = "Claim"

STATUS_MAP = {
	"Open": "Open",
	"Replied": "Under Review",
	"Paused": "Under Review",
	"Resolved": "Resolved",
	"Closed": "Resolved",
}


def _claim_type(subject):
	"""Old subjects looked like "Damaged goods — SAL-ORD-0001"."""
	head = (subject or "").split("—")[0].strip()
	return head if head in CLAIM_TYPES else "Other"


def _resolve_reference(customer, subject):
	"""(doctype, name) if the old free-text reference really is this customer's."""
	parts = (subject or "").split("—", 1)
	if len(parts) < 2:
		return None, None
	candidate = parts[1].strip()
	if not candidate:
		return None, None
	for doctype, party_field in CLAIMABLE_DOCTYPES.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		owner = frappe.db.get_value(doctype, candidate, party_field)
		if owner and owner == customer:
			return doctype, candidate
	return None, None


def execute():
	for required in ("Webstore Claim", "Issue"):
		if not frappe.db.exists("DocType", required):
			return

	issues = frappe.get_all(
		"Issue",
		filters={"issue_type": LEGACY_ISSUE_TYPE},
		fields=["name", "subject", "description", "status", "customer", "raised_by", "creation"],
	)
	migrated = 0
	for issue in issues:
		if not issue.customer:
			# nothing to scope it to; leave the Issue alone for manual handling
			continue
		if frappe.db.exists("Webstore Claim", {"legacy_issue": issue.name}):
			continue

		doctype, name = _resolve_reference(issue.customer, issue.subject)
		claim = frappe.get_doc(
			{
				"doctype": "Webstore Claim",
				"customer": issue.customer,
				"claim_type": _claim_type(issue.subject),
				"status": STATUS_MAP.get(issue.status, "Open"),
				"description": issue.description or issue.subject or "",
				"against_doctype": doctype,
				"against_document": name,
				"raised_by": issue.raised_by,
				"posting_date": issue.creation,
				"legacy_issue": issue.name,
			}
		)
		claim.flags.ignore_permissions = True
		claim.insert()
		migrated += 1

	if migrated:
		frappe.db.commit()
		print(f"migrated {migrated} Issue-based claims to Webstore Claim")
