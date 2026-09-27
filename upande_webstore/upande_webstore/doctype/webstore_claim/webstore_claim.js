// The server already refuses a document belonging to someone else
// (services/claims.assert_belongs_to), but that fires on save. Without a query
// on the field the desk offered every invoice on the site, so a sales user
// filled the whole form in before finding out. These bind the same customer
// scope to the picker itself. One query serves invoices and delivery notes:
// the Dynamic Link passes the chosen doctype through.
const DOCUMENT_QUERY = "upande_webstore.api.claims.claimable_document_query";

function document_query(frm) {
	return {
		query: DOCUMENT_QUERY,
		filters: { customer: frm.doc.customer || "" },
	};
}

// Only the customer's own contacts; the server checks the same on save.
function contact_query(frm) {
	return {
		query: "frappe.contacts.doctype.contact.contact.contact_query",
		filters: { link_doctype: "Customer", link_name: frm.doc.customer || "" },
	};
}

// Mirrors services/claim_lines.line_amount so the totals move as the user
// types. The server recomputes both on save and never believes these.
function line_amount(frm, row) {
	const qty = flt(row.claimed_qty);
	if (qty <= 0) return 0;
	const rate = flt(row.rate);
	return frm.doc.is_price_adjustment ? qty * (rate - flt(row.new_rate)) : qty * rate;
}

function recalculate(frm) {
	let total = 0;
	(frm.doc.lines || []).forEach((row) => {
		if (!frm.doc.is_price_adjustment && flt(row.new_rate)) {
			row.new_rate = 0;
		}
		row.claim_amount = line_amount(frm, row);
		total += row.claim_amount;
	});
	frm.doc.proposed_total = total;
	frm.refresh_field("lines");
	frm.refresh_field("proposed_total");
}

// Put a refused value back synchronously. A grid edit fires the field's
// change handler twice; resetting through frappe.model.set_value is async, so
// the second call still saw the refused value and warned a second time.
function clamp(frm, row, fieldname, value) {
	row[fieldname] = value;
	frm.dirty();
	frm.fields_dict.lines.grid.get_row(row.name)?.refresh_field(fieldname);
}

function set_fetch_label(frm) {
	const field = frm.get_field("fetch_lines");
	if (!field) return;
	const label = frm.doc.against_doctype
		? __("Fetch {0} Lines", [__(frm.doc.against_doctype)])
		: __("Fetch Lines");
	field.$input && field.$input.text(label);
}

function fetch_lines(frm) {
	if (!frm.doc.customer || !frm.doc.against_doctype || !frm.doc.against_document) {
		frappe.msgprint(__("Pick the customer and the document this claim is about first."));
		return;
	}
	if (frm.doc.approved_total) {
		frappe.msgprint(
			__("This claim has an approved value. Withdraw the approval before changing the lines it was given for.")
		);
		return;
	}

	const run = () =>
		frappe
			.call({
				method: "upande_webstore.api.claims.get_document_lines",
				args: {
					customer: frm.doc.customer,
					doctype: frm.doc.against_doctype,
					name: frm.doc.against_document,
				},
				freeze: true,
			})
			.then((r) => {
				frm.clear_table("lines");
				(r.message || []).forEach((row) => frm.add_child("lines", row));
				recalculate(frm);
				frm.dirty();
			});

	// Deliberately a button rather than automatic: re-running it discards
	// whatever was filled in, so ask when there is something to lose.
	if ((frm.doc.lines || []).length) {
		frappe.confirm(__("Replace the claimed lines with the document's current lines?"), run);
	} else {
		run();
	}
}

frappe.ui.form.on("Webstore Claim", {
	setup(frm) {
		frm.set_query("against_document", () => document_query(frm));
		// the child grid is the same door: filtering only the parent leaves it open
		frm.set_query("reference_name", "related_documents", () => document_query(frm));
		frm.set_query("contact_person", () => contact_query(frm));
	},

	refresh(frm) {
		set_fetch_label(frm);
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
		if (frm.doc.contact_person) {
			stale.push(frm.doc.contact_person);
			frm.set_value("contact_person", null);
		}
		(frm.doc.related_documents || []).forEach((row) => {
			if (row.reference_name) {
				stale.push(row.reference_name);
				frappe.model.set_value(row.doctype, row.name, "reference_name", null);
			}
		});

		if (stale.length) {
			frappe.show_alert({
				message: __("Cleared {0} reference(s) — they belonged to the previous customer.", [
					stale.length,
				]),
				indicator: "orange",
			});
		}
	},

	against_doctype(frm) {
		// a name picked under the other doctype would be looked up as this one
		if (frm.doc.against_document) {
			frm.set_value("against_document", null);
		}
		set_fetch_label(frm);
	},

	fetch_lines(frm) {
		fetch_lines(frm);
	},

	action(frm) {
		if (!frm.doc.action) {
			frm.set_value({ is_price_adjustment: 0, requires_credit_note: 0 });
		}
	},

	// set by fetch_from when the action changes; decides whether New Unit
	// Value is editable and how the lines are totalled
	is_price_adjustment(frm) {
		recalculate(frm);
	},
});

frappe.ui.form.on("Webstore Claim Line", {
	claimed_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (flt(row.claimed_qty) > flt(row.invoiced_qty)) {
			clamp(frm, row, "claimed_qty", row.invoiced_qty);
			frappe.msgprint(
				__("Row {0} ({1}): you cannot claim more than the {2} invoiced.", [
					row.idx,
					row.item_code,
					row.invoiced_qty,
				])
			);
		}
		recalculate(frm);
	},

	new_rate(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (flt(row.new_rate) > flt(row.rate)) {
			clamp(frm, row, "new_rate", row.rate);
			frappe.msgprint(
				__("Row {0} ({1}): the new unit value cannot be above the invoiced rate {2}.", [
					row.idx,
					row.item_code,
					format_currency(row.rate),
				])
			);
		}
		recalculate(frm);
	},

	lines_remove(frm) {
		recalculate(frm);
	},
});
