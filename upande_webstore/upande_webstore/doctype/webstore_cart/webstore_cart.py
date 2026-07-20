from frappe.model.document import Document


class WebstoreCart(Document):
	def validate(self):
		self.total = sum(row.amount or 0 for row in self.items)
