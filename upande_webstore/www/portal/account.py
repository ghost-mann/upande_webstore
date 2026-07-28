import frappe

from upande_webstore.services.portal import portal_page_context
from upande_webstore.services.portal_data import get_customer_addresses


def get_context(context):
	customer = portal_page_context(context, "/portal/account", "account")

	from upande_webstore.api.account import _address_types

	context.address_types = _address_types()
	context.default_country = (
		frappe.db.get_value("Company", frappe.defaults.get_global_default("company"), "country")
		or "Kenya"
	)
	context.user_doc = frappe.get_doc("User", frappe.session.user)
	context.customer = customer
	context.addresses = get_customer_addresses(customer)
	return context
