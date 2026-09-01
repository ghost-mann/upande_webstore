frappe.ui.form.on("Webstore Product", {
	refresh(frm) {
		// Box types come from whichever source this site runs, so the list is
		// fetched rather than declared as link options on the field.
		frappe.call("upande_webstore.api.boxes.list_box_types").then((r) => {
			const options = r.message || [];
			frm.set_df_property("box_type", "options", options);
			frm.fields_dict.box_type?.set_data(options);
		});
	},
});
