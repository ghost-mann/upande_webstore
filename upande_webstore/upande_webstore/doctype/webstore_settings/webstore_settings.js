frappe.ui.form.on("Webstore Settings", {
	refresh(frm) {
		frappe.call("upande_webstore.theme.transfer.list_presets").then((r) => {
			frm.set_df_property("preset", "options", [""].concat(r.message || []).join("\n"));
		});

		frappe.call("upande_webstore.api.boxes.list_box_types").then((r) => {
			const options = r.message || [];
			// set_data as well as the property: an Autocomplete reads df.options
			// only in make_input(), which has already run by the time this
			// resolves — the same reason the occasion field below does it.
			frm.set_df_property("default_box_type", "options", options);
			frm.fields_dict.default_box_type?.set_data(options);
		});

		frappe.call("upande_webstore.api.boxes.describe_source").then((r) => {
			frm.get_field("box_source_summary").$wrapper.html(boxSummary(r.message));
		});

		frappe.call("upande_webstore.theme.occasion.list_occasions").then((r) => {
			const options = r.message || [];
			// set_data, not set_df_property: an Autocomplete reads df.options only
			// in make_input(), which has already run by the time this resolves, so
			// setting the property alone leaves the control empty and it renders as
			// a plain text box. set_data fills awesomplete directly — the same call
			// frappe's own async-loaded autocompletes use. df.options is set too so
			// the list survives if the control is ever rebuilt.
			frm.set_df_property("occasion", "options", options);
			frm.fields_dict.occasion?.set_data(options);
		});
		frm.__ws_last_occasion = frm.doc.occasion;

		frm.add_custom_button(
			__("Export Theme"),
			() => {
				frappe.call("upande_webstore.theme.transfer.export_theme").then((r) => {
					const blob = new Blob([JSON.stringify(r.message, null, 2)], {
						type: "application/json",
					});
					const url = URL.createObjectURL(blob);
					const link = document.createElement("a");
					link.href = url;
					link.download = "webstore-theme.json";
					link.click();
					URL.revokeObjectURL(url);
				});
			},
			__("Theme")
		);

		frm.add_custom_button(
			__("Import Theme"),
			() => {
				if (!frm.doc.theme_file) {
					frappe.msgprint(__("Attach a theme JSON first."));
					return;
				}
				frappe.confirm(
					__(
						"This overwrites every Theme, Branding and Features value. Continue?"
					),
					() => {
						fetch(frm.doc.theme_file)
							.then((res) => res.json())
							.then((payload) =>
								frappe.call("upande_webstore.theme.transfer.import_theme", {
									payload: payload,
								})
							)
							.then((r) => report(frm, r.message))
							.catch((e) =>
								frappe.msgprint({
									title: __("Import Failed"),
									message: e.message || String(e),
									indicator: "red",
								})
							);
					}
				);
			},
			__("Theme")
		);

		frm.add_custom_button(
			__("Apply Preset"),
			() => {
				if (!frm.doc.preset) {
					frappe.msgprint(__("Pick a preset first."));
					return;
				}
				frappe.confirm(
					__(
						"Apply preset {0}? This overwrites every Theme, Branding and Features value.",
						[frm.doc.preset]
					),
					() => {
						frappe
							.call("upande_webstore.theme.transfer.apply_preset", {
								name: frm.doc.preset,
							})
							.then((r) => report(frm, r.message));
					}
				);
			},
			__("Theme")
		);
	},

	occasion(frm) {
		// Clear the previous campaign's wording and cutoff date — otherwise last
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

function report(frm, result) {
	if (!result) return;
	frm.reload_doc();
	let message = __("Applied {0} settings.", [result.applied]);
	if (result.missing_images && result.missing_images.length) {
		message +=
			"<br><br>" +
			__("These images do not exist on this site and need re-uploading:") +
			"<ul><li>" +
			result.missing_images.join("</li><li>") +
			"</li></ul>";
	}
	frappe.msgprint({ title: __("Theme Applied"), message: message, indicator: "green" });
}

function boxSummary(data) {
	if (!data) return "";
	if (!data.doctype) {
		return `<div class="text-muted">${__(
			"This site has no box type source. Box packing stays inert until one exists — either Box Type records with a stem capacity, or Items with Is Box ticked and a pack rate."
		)}</div>`;
	}
	const rows = (data.usable || [])
		.map(
			(box) =>
				`<tr><td>${frappe.utils.escape_html(box.box_name)}</td>` +
				`<td class="text-right">${box.pack_rate}</td>` +
				`<td>${box.box_type === data.default_box_type ? __("default") : ""}</td></tr>`
		)
		.join("");
	const problems = (data.unusable || [])
		.map(
			(box) =>
				`<tr><td>${frappe.utils.escape_html(box.box_name)}</td>` +
				`<td colspan="2" class="text-muted">${box.reasons.join(", ")}</td></tr>`
		)
		.join("");
	return `
		<div class="text-muted" style="margin-bottom:.5rem">
			${__("Box types come from")} <b>${frappe.utils.escape_html(data.label)}</b>
		</div>
		<table class="table table-bordered table-sm">
			<thead><tr><th>${__("Box")}</th><th class="text-right">${__("Stems")}</th><th></th></tr></thead>
			<tbody>${rows || `<tr><td colspan="3" class="text-muted">${__("None usable yet.")}</td></tr>`}</tbody>
			${problems ? `<tbody><tr><th colspan="3">${__("Hidden from the storefront")}</th></tr>${problems}</tbody>` : ""}
		</table>`;
}
