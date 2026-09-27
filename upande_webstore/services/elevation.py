"""Run a block as Administrator inside a website user's request.

`frappe.set_user()` is not a plain user switch: it also overwrites
`session.sid` with the user name and empties `session.data`. Switching back
with `set_user(session_user)` restores the user but leaves `sid` equal to the
user's email, and that is the value the response then writes into the `sid`
cookie — so the buyer was silently logged out the moment their checkout
succeeded, and lost their CSRF token with it. This puts the whole session
back, not just the user.
"""

from contextlib import contextmanager

import frappe


@contextmanager
def as_administrator():
	session = frappe.local.session
	user, sid, data = session.user, session.sid, session.data
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)
		frappe.local.session.sid = sid
		frappe.local.session.data = data
