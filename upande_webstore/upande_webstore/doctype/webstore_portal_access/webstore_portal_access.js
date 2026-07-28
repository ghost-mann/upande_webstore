frappe.ui.form.on("Webstore Portal Access", {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		if (frm.doc.status !== "Active") {
			frm.add_custom_button(__("Grant Access"), () => {
				frappe.confirm(
					__("Give {0} portal and storefront access as {1}?", [
						frm.doc.full_name,
						frm.doc.customer,
					]),
					() => {
						frm.call({ doc: frm.doc, method: "grant", freeze: true }).then((r) => {
							if (!r || r.exc) return;
							frm.reload_doc();
							frappe.msgprint({
								title: __("Access Granted"),
								message: __(
									"{0} can now sign in at /login and order from the store. A welcome email was sent so they can set their own password.",
									[frm.doc.email]
								),
								indicator: "green",
							});
						});
					}
				);
			}).addClass("btn-primary");
		}

		if (frm.doc.status === "Active") {
			frm.add_custom_button(__("Revoke"), () => {
				frappe.confirm(
					__("Disable the login for {0}? Their history and customer link are kept.", [
						frm.doc.email,
					]),
					() => {
						frm.call({ doc: frm.doc, method: "revoke", freeze: true }).then((r) => {
							if (!r || r.exc) return;
							frm.reload_doc();
						});
					}
				);
			});
		}
	},
});
