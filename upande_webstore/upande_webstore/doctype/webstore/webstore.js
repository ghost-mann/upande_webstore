// The same Theme tools Webstore Settings has, aimed at one storefront.
//
// Without these the only way to give a second shop its own look is to fill in
// ~60 fields by hand, and the Apply Preset button on the Single would repaint
// every shop at once. The preset and theme file are asked for in a dialog
// rather than stored on the record: they are an action's input, not a
// property of the store.

frappe.ui.form.on("Webstore", {
	refresh(frm) {
		// An Autocomplete reads df.options only in make_input(), which has
		// already run by the time these resolve — so set_data as well, the
		// same as webstore_settings.js does.
		frappe.call("upande_webstore.api.boxes.list_box_types").then((r) => {
			const options = r.message || [];
			frm.set_df_property("default_box_type", "options", options);
			frm.fields_dict.default_box_type?.set_data(options);
		});

		frappe.call("upande_webstore.theme.occasion.list_occasions").then((r) => {
			const options = r.message || [];
			frm.set_df_property("occasion", "options", options);
			frm.fields_dict.occasion?.set_data(options);
		});
		frm.__ws_last_occasion = frm.doc.occasion;

		if (frm.is_new()) return;

		frm.add_custom_button(__("Apply Preset"), () => applyPreset(frm), __("Theme"));
		frm.add_custom_button(__("Export Theme"), () => exportTheme(frm), __("Theme"));
		frm.add_custom_button(__("Import Theme"), () => importTheme(frm), __("Theme"));

		if (frm.doc.slug) {
			frm.add_custom_button(__("Open Storefront"), () => {
				// the default store keeps the bare /store — see services/store.py
				const path = frm.doc.slug === "store" ? "/store" : `/${frm.doc.slug}/store`;
				window.open(path, "_blank");
			});
		}
	},

	occasion(frm) {
		// Clear the previous campaign's wording and cutoff — otherwise last
		// year's "book by 20 January" rides along into the next occasion.
		if (frm.doc.occasion === frm.__ws_last_occasion) return;
		frm.__ws_last_occasion = frm.doc.occasion;
		[
			"occasion_banner_text",
			"occasion_banner_cta_label",
			"occasion_banner_cta_url",
			"occasion_runs_until",
		].forEach((field) => frm.set_value(field, ""));
	},
});

function applyPreset(frm) {
	frappe.call("upande_webstore.theme.transfer.list_presets").then((r) => {
		const presets = r.message || [];
		if (!presets.length) {
			frappe.msgprint(__("No shipped presets on this site."));
			return;
		}
		const dialog = new frappe.ui.Dialog({
			title: __("Apply Preset to {0}", [frm.doc.title || frm.doc.slug]),
			fields: [
				{
					fieldname: "preset",
					fieldtype: "Select",
					label: __("Preset"),
					options: presets.join("\n"),
					reqd: 1,
				},
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"This overwrites every Theme, Branding and Features value on this storefront. Anything the preset does not set goes back to inheriting Webstore Settings. Other storefronts are untouched."
					)}</p>`,
				},
			],
			primary_action_label: __("Apply"),
			primary_action(values) {
				dialog.hide();
				frappe
					.call("upande_webstore.theme.transfer.apply_preset", {
						name: values.preset,
						webstore: frm.doc.name,
					})
					.then((res) => report(frm, res.message));
			},
		});
		dialog.show();
	});
}

function exportTheme(frm) {
	frappe
		.call("upande_webstore.theme.transfer.export_theme", { webstore: frm.doc.name })
		.then((r) => {
			const blob = new Blob([JSON.stringify(r.message, null, 2)], {
				type: "application/json",
			});
			const url = URL.createObjectURL(blob);
			const link = document.createElement("a");
			link.href = url;
			link.download = `${frm.doc.slug || "webstore"}-theme.json`;
			link.click();
			URL.revokeObjectURL(url);
		});
}

function importTheme(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Import Theme into {0}", [frm.doc.title || frm.doc.slug]),
		fields: [
			{ fieldname: "theme_file", fieldtype: "Attach", label: __("Theme JSON"), reqd: 1 },
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"This overwrites every Theme, Branding and Features value on this storefront. Other storefronts are untouched."
				)}</p>`,
			},
		],
		primary_action_label: __("Import"),
		primary_action(values) {
			dialog.hide();
			fetch(values.theme_file)
				.then((res) => res.json())
				.then((payload) =>
					frappe.call("upande_webstore.theme.transfer.import_theme", {
						payload: payload,
						webstore: frm.doc.name,
					})
				)
				.then((res) => report(frm, res.message))
				.catch((e) =>
					frappe.msgprint({
						title: __("Import Failed"),
						message: e.message || String(e),
						indicator: "red",
					})
				);
		},
	});
	dialog.show();
}

function report(frm, result) {
	if (!result) return;
	frm.reload_doc();
	const missing = result.missing_images || [];
	frappe.msgprint({
		title: __("Theme Applied"),
		indicator: missing.length ? "orange" : "green",
		message: missing.length
			? __("{0} values applied. These images are not on this site: {1}", [
					result.applied,
					missing.join(", "),
			  ])
			: __("{0} values applied to this storefront.", [result.applied]),
	});
}
