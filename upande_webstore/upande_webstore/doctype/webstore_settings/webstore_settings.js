frappe.ui.form.on("Webstore Settings", {
	refresh(frm) {
		frappe.call("upande_webstore.theme.transfer.list_presets").then((r) => {
			frm.set_df_property("preset", "options", [""].concat(r.message || []).join("\n"));
		});

		frappe.call("upande_webstore.theme.occasion.list_occasions").then((r) => {
			frm.set_df_property("occasion", "options", r.message || []);
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
