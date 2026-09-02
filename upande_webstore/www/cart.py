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

	from upande_webstore.services.settings import get_checkout_mode

	context.no_cache = 1
	# Presentation only — place_order re-checks this server-side, since the
	# button a farm has hidden is not a security boundary on its own.
	context.checkout_mode = get_checkout_mode()
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
	from upande_webstore.services.packing import get_box_types, packing_enabled

	context.box_types = get_box_types() if packing_enabled() else []
	context.delivery_points_available = dropoff.delivery_points_available()
	context.delivery_points = dropoff.get_delivery_points()
	return context
