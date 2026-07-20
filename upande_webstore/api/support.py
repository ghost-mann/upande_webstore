import frappe
from frappe import _

from upande_webstore.api.cart import _require_login
from upande_webstore.services.portal import get_current_customer


@frappe.whitelist(methods=["POST"])
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
	return frappe.get_all(
		"Issue",
		or_filters=[["customer", "=", customer], ["raised_by", "=", frappe.session.user]],
		fields=["name", "subject", "status", "creation"],
		order_by="creation desc",
		limit_page_length=limit,
	)


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
