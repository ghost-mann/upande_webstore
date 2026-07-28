import frappe
from frappe import _
from frappe.utils import get_url_to_form

from upande_webstore.services.portal import assert_customer_doc
from upande_webstore.services.settings import get_settings
from upande_webstore.theme.features import guard


def _act_on_quotation(name, status):
	quotation = assert_customer_doc("Quotation", name, "party_name")
	if quotation.docstatus != 1:
		frappe.throw(_("This quotation is not open."), frappe.ValidationError)
	if quotation.webstore_portal_status:
		frappe.throw(
			_("You have already responded to this quotation."), frappe.ValidationError
		)
	quotation.db_set("webstore_portal_status", status)
	quotation.add_comment(
		"Comment", _("Customer {0} this quotation via the webstore portal.").format(status.lower())
	)
	_notify(quotation, status)
	return {"status": status}


def _notify(quotation, status):
	settings = get_settings()
	recipients = [e.strip() for e in (settings.notification_emails or "").split(",") if e.strip()]
	if not recipients:
		return
	frappe.sendmail(
		recipients=recipients,
		subject=_("Quotation {0} {1} by customer").format(quotation.name, status.lower()),
		message=_("Quotation {0} was {1} by {2} on the portal.<br>{3}").format(
			quotation.name, status.lower(), quotation.party_name,
			get_url_to_form("Quotation", quotation.name),
		),
	)


@frappe.whitelist(methods=["POST"])
@guard("portal", "quotations")
def accept_quotation(name):
	return _act_on_quotation(name, "Accepted")


@frappe.whitelist(methods=["POST"])
@guard("portal", "quotations")
def decline_quotation(name):
	return _act_on_quotation(name, "Declined")


@frappe.whitelist()
@guard("portal", "invoices")
def download_invoice_pdf(name):
	invoice = assert_customer_doc("Sales Invoice", name, "customer")
	# Ownership verified above; render under elevated context because
	# printview re-checks desk permissions website users lack.
	session_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		pdf = frappe.get_print("Sales Invoice", name, doc=invoice, as_pdf=True)
	finally:
		frappe.set_user(session_user)
	frappe.local.response.filename = f"{name}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"
