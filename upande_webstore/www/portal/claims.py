from upande_webstore.api.claims import get_claim_options, get_claims
from upande_webstore.services.portal import portal_page_context


def get_context(context):
	portal_page_context(context, "/portal/claims", "claims")
	context.claims = get_claims()
	options = get_claim_options()
	context.claim_types = options["types"]
	# only this customer's documents are offered, and the server re-validates
	context.claim_documents = options["documents"]
	return context
