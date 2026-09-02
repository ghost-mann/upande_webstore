import frappe
from frappe import _

from upande_webstore.services.pricing import GUEST_PRICE_LIST_COOKIE, get_offered_price_lists


def _reprice_open_cart(cart):
	"""Re-resolve every line against whatever get_price_list() now returns,
	then drop what priced at nothing there.

	Reuses api.cart._reprice for the rate resolution itself — the same
	server-side re-pricing that already runs on every cart mutation — so a
	currency switch is not a second, divergent pricing path. What it adds is
	the drop: _reprice alone would leave a line at rate 0, and carrying that
	silently would look like a free item rather than what it is, a price the
	new list simply does not have.
	"""
	from upande_webstore.api.cart import _recompute_boxes, _reprice

	_reprice(cart)
	dropped = [row.item_name or row.item_code for row in cart.items if not row.rate]
	if dropped:
		cart.items = [row for row in cart.items if row.rate]
	_recompute_boxes(cart)
	cart.save(ignore_permissions=True)
	return dropped


@frappe.whitelist(allow_guest=True, methods=["POST"])
def set_price_list(price_list):
	"""Set the visitor's chosen guest price list. Reloads are the caller's
	job — every price on the page must come from one fresh resolution, not be
	patched client-side.

	The value is never trusted merely for being posted: it must name a row
	Webstore Settings currently offers, checked the same way (and by the same
	function) as every other resolution. A logged-in visitor with an open
	cart and no customer price list of their own — the one case a currency
	switch has real consequences — gets that cart re-priced in the same call.
	"""
	offered = {row.price_list for row in get_offered_price_lists()}
	if price_list not in offered:
		frappe.throw(_("That price list is not offered here."), frappe.ValidationError)

	frappe.local.cookie_manager.set_cookie(GUEST_PRICE_LIST_COOKIE, price_list)
	# see services.pricing._cookie_price_list: the cookie above only reaches
	# the *next* request, so this request's own reprice needs the override too
	frappe.local.webstore_guest_price_list_override = price_list

	dropped = []
	if frappe.session.user not in (None, "", "Guest"):
		from upande_webstore.api.cart import _get_open_cart

		cart = _get_open_cart()
		if cart and cart.items:
			dropped = _reprice_open_cart(cart)

	return {"price_list": price_list, "dropped": dropped}
