import frappe
from frappe import _
from frappe.model.document import Document


class WebstoreWishlist(Document):
	def validate(self):
		self.validate_one_per_store()

	def validate_one_per_store(self):
		"""`user` alone used to be the unique column; Task 2 needs one wishlist
		per user per store instead, so the rule moves off the column and in
		here - checked only at creation, exactly as the column constraint it
		replaces only ever fired on insert."""
		if not self.is_new():
			return
		if frappe.db.exists("Webstore Wishlist", {"user": self.user, "webstore": self.webstore}):
			frappe.throw(
				_("{0} already has a wishlist for this store.").format(self.user),
				frappe.ValidationError,
			)
