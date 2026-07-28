import frappe
from frappe import _

from upande_webstore.api.cart import _require_login
from upande_webstore.services.portal import get_current_customer
from upande_webstore.theme.features import guard


@frappe.whitelist(methods=["POST"])
@guard("portal", "support")
def create_issue(subject, description):
	_require_login()
	customer = get_current_customer()
	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required."), frappe.ValidationError)
	issue = frappe.get_doc({
		"doctype": "Issue",
		"subject": subject,
		"description": description,
		"raised_by": frappe.session.user,
		"customer": customer,
	})
	issue.flags.ignore_permissions = True
	issue.insert()
	return {"name": issue.name}


def get_issues(limit=50):
	_require_login()
	customer = get_current_customer()
	rows = frappe.get_all(
		"Issue",
		or_filters=[["customer", "=", customer], ["raised_by", "=", frappe.session.user]],
		fields=["name", "subject", "status", "creation", "issue_type"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return [r for r in rows if (r.issue_type or "") != CLAIM_TYPE]


def get_issue_or_throw(name):
	_require_login()
	customer = get_current_customer()
	issue = frappe.get_doc("Issue", name)
	if issue.customer != customer and issue.raised_by != frappe.session.user:
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return issue


def get_replies(issue_name):
	return frappe.get_all(
		"Communication",
		filters={"reference_doctype": "Issue", "reference_name": issue_name},
		fields=["sender", "content", "communication_date", "sent_or_received"],
		order_by="communication_date asc",
	)


CLAIM_TYPE = "Claim"


def _ensure_claim_issue_type():
	if not frappe.db.exists("Issue Type", CLAIM_TYPE):
		frappe.get_doc({"doctype": "Issue Type", "name": CLAIM_TYPE, "description": "Customer claim filed via the webstore portal"}).insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
@guard("portal", "claims")
def create_claim(claim_type, reference, description):
	"""File a claim (damaged goods, short delivery, quality) as a typed Issue."""
	_require_login()
	customer = get_current_customer()
	claim_type = (claim_type or "").strip()
	reference = (reference or "").strip()
	if not claim_type:
		frappe.throw(_("Please select what the claim is about."), frappe.ValidationError)
	if not (description or "").strip():
		frappe.throw(_("Please describe the claim."), frappe.ValidationError)
	_ensure_claim_issue_type()
	body = description
	if reference:
		body = f"<p><b>{_('Reference document')}:</b> {frappe.utils.escape_html(reference)}</p>{description}"
	issue = frappe.get_doc({
		"doctype": "Issue",
		"subject": f"{claim_type}{' — ' + reference if reference else ''}",
		"description": body,
		"issue_type": CLAIM_TYPE,
		"raised_by": frappe.session.user,
		"customer": customer,
	})
	issue.flags.ignore_permissions = True
	issue.insert()
	return {"name": issue.name}


def get_claims(limit=50):
	_require_login()
	customer = get_current_customer()
	rows = frappe.get_all(
		"Issue",
		or_filters=[["customer", "=", customer], ["raised_by", "=", frappe.session.user]],
		fields=["name", "subject", "status", "creation", "issue_type"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return [r for r in rows if (r.issue_type or "") == CLAIM_TYPE]
