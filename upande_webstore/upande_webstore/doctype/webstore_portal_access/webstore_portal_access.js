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
			frm.add_custom_button(__("Password Setup Link"), () => {
				frm.call({ doc: frm.doc, method: "password_setup_link", freeze: true }).then((r) => {
					if (!r || r.exc || !r.message) return;
					const link = r.message.link;
					frappe.msgprint({
						title: __("Password Setup Link"),
						message:
							`<p>${__("Send this to {0}. It lets them set their own password.", [
								frappe.utils.escape_html(frm.doc.email),
							])}</p>` +
							`<div style="word-break:break-all;padding:.6rem;border:1px solid var(--border-color);border-radius:4px;font-family:monospace;font-size:.85em">${frappe.utils.escape_html(
								link
							)}</div>` +
							`<p style="margin-top:.7rem"><b>${__("Generating a new link cancels the previous one.")}</b></p>`,
						indicator: "blue",
					});
					navigator.clipboard?.writeText(link).then(
						() => frappe.show_alert({ message: __("Link copied"), indicator: "green" }),
						() => {}
					);
				});
			});

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
