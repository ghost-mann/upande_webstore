import frappe

from upande_webstore.services.portal_data import get_customer_addresses
from upande_webstore.services.pricing import get_customer


def get_context(context):
	from upande_webstore.theme.features import require

	require("cart")
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/cart"
		raise frappe.Redirect
	from upande_webstore.api.cart import _get_open_cart, _reprice, serialize_cart

	context.no_cache = 1
	cart = _get_open_cart()
	if cart:
		_reprice(cart)
		cart.save(ignore_permissions=True)
	context.cart = serialize_cart(cart)
	customer = get_customer()
	context.addresses = get_customer_addresses(customer) if customer else []
	return context
