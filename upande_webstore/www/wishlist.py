import frappe


def get_context(context):
	from upande_webstore.services.store import current_store_or_404, storefront_path
	from upande_webstore.theme.features import require

	# An explicit /<slug>/wishlist must 404 for an unknown or unpublished
	# slug rather than silently showing the default store's wishlist.
	current_store_or_404()
	require("wishlist")
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={storefront_path('wishlist')}"
		raise frappe.Redirect
	from upande_webstore.api.wishlist import get_wishlist

	context.no_cache = 1
	context.wishlist = get_wishlist()
	return context
