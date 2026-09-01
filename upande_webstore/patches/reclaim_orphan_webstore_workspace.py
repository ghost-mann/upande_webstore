"""Reclaim a hand-made "Upande Webstore" workspace for this app.

Before the app shipped a Workspace, /desk/upande-webstore resolved to nothing and
the page 404'd. The workaround on some sites was to create the workspace by hand
in the desk UI. Those records have no `module`, which leaves them outside the join
in `frappe.boot.load_desktop_data` — the route resolves, but the app still reports
zero workspaces and the sidebar never binds to it.

The repair names the module and backdates `modified`, which hands the record to
`sync_all` in the same migrate: `import_file_by_path` skips a file whose `modified`
is older than the row in the database, so without the backdate a shell edited
yesterday would keep the shipped workspace out indefinitely. Hence pre_model_sync.

Deleting the shell would be the obvious move and is the wrong one — Workspace has a
delete hook in each direction, and between them they destroy the very things this
patch exists to install:

  * Workspace.on_trash deletes the same-titled Workspace Sidebar when the workspace
    has no module — on every site, developer_mode or not.
  * Workspace.after_delete deletes the workspace's own source folder off disk when
    the module IS set and developer_mode is on.

Updating in place fires neither.

A workspace someone actually built content in is left alone: it is worth more than
an automatic repair, and its owner can merge it by hand.
"""

import frappe

WORKSPACE = "Upande Webstore"
MODULE = "Upande Webstore"

# comfortably older than any shipped workspace file, so the import always wins
BACKDATED = "2000-01-01 00:00:00.000000"


def execute():
	reclaim_orphan(WORKSPACE, MODULE)


def reclaim_orphan(workspace: str, module: str) -> bool:
	"""Hand an empty, module-less `workspace` to `module` and let sync_all refill it.

	Returns True when the record was reclaimed. Split out from execute() so it can be
	exercised against a throwaway workspace instead of the shipped one.
	"""
	# get_value returns None both for a missing workspace and for a NULL module, and
	# a NULL module is precisely what needs repairing — so ask the two questions apart.
	if not frappe.db.exists("Workspace", workspace):
		return False

	current = frappe.db.get_value("Workspace", workspace, "module")
	if current == module:
		return False

	doc = frappe.get_doc("Workspace", workspace)
	if doc.links or doc.shortcuts or frappe.parse_json(doc.content or "[]"):
		frappe.log_error(
			title="Upande Webstore workspace not reclaimed",
			message=(
				f"Workspace {workspace!r} has module={current!r} instead of {module!r}, "
				"but carries content, so it was left as it is. Move anything worth "
				"keeping onto the standard workspace and delete this one."
			),
		)
		return False

	frappe.db.set_value(
		"Workspace",
		workspace,
		{"module": module, "public": 1, "modified": BACKDATED},
		update_modified=False,
	)
	return True
