"""Connections: a Webstore Claim count on the documents a claim points at.

Wired through `override_doctype_dashboards`, which hands each function the
dashboard ERPNext (and any other app) already built, to be extended rather than
replaced.
"""

from frappe import _

CLAIM_DOCTYPE = "Webstore Claim"


def _add_claims(data, fieldname):
	data.setdefault("non_standard_fieldnames", {})
	data.setdefault("transactions", [])
	# always explicit: the dashboard's own `fieldname` belongs to its other
	# links, and Contact's is not set at all
	data["non_standard_fieldnames"][CLAIM_DOCTYPE] = fieldname
	for group in data["transactions"]:
		if CLAIM_DOCTYPE in group.get("items", []):
			return data
	data["transactions"].append({"label": _("Claims"), "items": [CLAIM_DOCTYPE]})
	return data


def customer(data):
	return _add_claims(data, "customer")


def _against(data, doctype):
	"""against_document is a Dynamic Link: count only the claims whose
	against_doctype is this dashboard's doctype, not any claim that happens to
	name a document of the same name."""
	data = _add_claims(data, "against_document")
	data.setdefault("dynamic_links", {})["against_document"] = [doctype, "against_doctype"]
	return data


def sales_invoice(data):
	return _against(data, "Sales Invoice")


def delivery_note(data):
	return _against(data, "Delivery Note")


def contact(data):
	return _add_claims(data, "contact_person")
