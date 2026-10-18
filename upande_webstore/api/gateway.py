"""Endpoints for the customer gateway and the Shop Address settings."""

import secrets

import frappe
from frappe.utils.password import set_encrypted_password

from upande_webstore.services import shop


@frappe.whitelist(allow_guest=True, methods=["GET"])
def config():
	"""The gateway's rules. Answers only a caller holding the gateway secret;
	to anyone else it does not exist."""
	if not shop.is_shop_request():
		raise frappe.PageDoesNotExistError
	return shop.gateway_config()


@frappe.whitelist(methods=["POST"])
def check_shop_address():
	frappe.only_for("System Manager")
	return shop.check_shop_address()


@frappe.whitelist(methods=["POST"])
def generate_gateway_secret():
	"""A new secret, returned once so it can be copied into the gateway.
	The previous one stops working immediately."""
	frappe.only_for("System Manager")
	secret = secrets.token_urlsafe(32)
	set_encrypted_password("Webstore Settings", "Webstore Settings", secret, "gateway_secret")
	# the placeholder a saved Password field holds: without it the next save of
	# the settings form sees an empty field and frappe deletes the secret
	frappe.db.set_single_value("Webstore Settings", "gateway_secret", "*" * len(secret))
	frappe.clear_document_cache("Webstore Settings", "Webstore Settings")
	return {"secret": secret}
