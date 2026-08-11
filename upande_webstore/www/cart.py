import frappe

from upande_webstore.services.portal_data import get_customer_addresses
from upande_webstore.services.pricing import get_customer


def get_context(context):
	from upande_webstore.theme.features import require

	require("cart")
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/cart"
		raise frappe.Redirect
	from upande_webstore.api.cart import (
		_get_open_cart,
		_recompute_boxes,
		_reprice,
		serialize_cart,
	)

	context.no_cache = 1
	cart = _get_open_cart()
	if cart:
		_reprice(cart)
		# also resolves each line's box from its product, so a cart that predates
		# the packing feature shows boxes on the next page load
		_recompute_boxes(cart)
		cart.save(ignore_permissions=True)
	context.cart = serialize_cart(cart)
	customer = get_customer()
	context.addresses = get_customer_addresses(customer) if customer else []

	from upande_webstore.services import dropoff

	context.delivery_points_available = dropoff.delivery_points_available()
	context.delivery_points = dropoff.get_delivery_points()
	return context
