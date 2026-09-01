from frappe import _
from frappe.utils import formatdate

from upande_webstore.api.claims import get_claim_options, get_claims
from upande_webstore.services.portal import portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/claims", "claims")
	context.claims = get_claims()
	options = get_claim_options()
	context.claim_types = options["types"]
	context.claim_window_days = options["claim_window_days"]
	# only this customer's documents are offered, and the server re-validates
	context.claim_documents = _labelled(options["documents"], context.claim_window_days)
	return context


def _labelled(documents, window_days):
	"""Add the label the picker renders, built here rather than in the browser so
	dates follow the site's date format."""
	return {
		doctype: [dict(row, label=_document_label(row, window_days)) for row in rows]
		for doctype, rows in documents.items()
	}


def _document_label(row, window_days):
	label = row["name"]
	if row.get("date"):
		label += " · " + formatdate(row["date"])
	if not row.get("claimable"):
		label += " — " + _("outside the {0}-day claim window").format(window_days)
	return label
