// The server already refuses an invoice belonging to someone else
// (services/claims.assert_belongs_to), but that fires on save. Without a query
// on the field the desk offered every invoice on the site, so a sales user
// filled the whole form in before finding out. These bind the same customer
// scope to the picker itself.
const INVOICE_QUERY = "upande_webstore.api.claims.claimable_invoice_query";

function invoice_query(frm) {
	return {
		query: INVOICE_QUERY,
		filters: { customer: frm.doc.customer || "" },
	};
}

frappe.ui.form.on("Webstore Claim", {
	setup(frm) {
		frm.set_query("against_document", () => invoice_query(frm));
		// the child grid is the same door: filtering only the parent leaves it open
		frm.set_query("reference_name", "related_documents", () => invoice_query(frm));
	},

	customer(frm) {
		// A reference picked under the previous customer is now invalid, and
		// the server would refuse it on save with a message about a document
		// that "does not exist" — deliberately vague, so it reads as a bug
		// rather than a stale pick. Clear it here and say why.
		const stale = [];

		if (frm.doc.against_document) {
			stale.push(frm.doc.against_document);
			frm.set_value("against_document", null);
		}
		(frm.doc.related_documents || []).forEach((row) => {
			if (row.reference_name) {
				stale.push(row.reference_name);
				frappe.model.set_value(row.doctype, row.name, "reference_name", null);
			}
		});

		if (stale.length) {
			frappe.show_alert({
				message: __("Cleared {0} document reference(s) — they belonged to the previous customer.", [
					stale.length,
				]),
				indicator: "orange",
			});
		}
	},
});
