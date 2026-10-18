"""Endpoints for the customer gateway and the Shop Address settings."""

import frappe

from upande_webstore.services import shop


@frappe.whitelist(allow_guest=True, methods=["GET"])
def config():
	"""The gateway's rules. Answers only a caller holding the gateway secret;
	to anyone else it does not exist."""
	if not shop.is_shop_request():
		raise frappe.PageDoesNotExistError
	return shop.gateway_config()
