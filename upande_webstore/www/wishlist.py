import frappe


def get_context(context):
	from upande_webstore.theme.features import require

	require("wishlist")
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/wishlist"
		raise frappe.Redirect
	from upande_webstore.api.wishlist import get_wishlist

	context.no_cache = 1
	context.wishlist = get_wishlist()
	return context
