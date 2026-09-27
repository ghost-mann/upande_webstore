"""Carry existing claims across the claim-form rework.

- `raised_by` (a User) gave way to `contact_person` (a Contact of the
  customer). The column outlives the field, so it is read here and mapped
  through the portal user's Contact; a desk user who is no customer contact
  maps to nothing, and `owner` still records who filed it.
- Claim lines lost the "Claimed" tick: a line is claimed when its quantity is
  above zero. An unticked line never counted, so its quantity is zeroed rather
  than suddenly joining the claim.
- `proposed_value` (a line total the user typed) gave way to `claim_amount`,
  computed as Claimed Quantity × Rate. Every claim before this was
  quantity-based, so that is the rule the totals are rebuilt on.
- The shipped Credit Note action gets the marker that shows the Credit Note
  field, and each claim picks up its action's markers.

Everything is written straight to the table: re-saving would re-run the claim
window check, which an older claim can no longer pass.
"""

import frappe

from upande_webstore.services.claims import contact_for_user

CLAIM = "Webstore Claim"
LINE = "Webstore Claim Line"
ACTION = "Webstore Claim Action"


def execute():
	if not frappe.db.table_exists(CLAIM):
		return
	_contacts_from_raised_by()
	_lines()
	_action_markers()


def _contacts_from_raised_by():
	if not frappe.db.has_column(CLAIM, "raised_by"):
		return
	rows = frappe.db.sql(
		f"""select name, customer, raised_by from `tab{CLAIM}`
		where ifnull(raised_by, '') != '' and ifnull(contact_person, '') = ''""",
		as_dict=True,
	)
	for row in rows:
		contact = contact_for_user(row.customer, row.raised_by)
		if contact:
			frappe.db.set_value(CLAIM, row.name, "contact_person", contact, update_modified=False)


def _lines():
	if not frappe.db.table_exists(LINE):
		return
	if frappe.db.has_column(LINE, "is_claimed"):
		frappe.db.sql(f"update `tab{LINE}` set claimed_qty = 0 where ifnull(is_claimed, 0) = 0")
	frappe.db.sql(
		f"""update `tab{LINE}`
		set claim_amount = if(ifnull(claimed_qty, 0) > 0, claimed_qty * ifnull(rate, 0), 0),
			new_rate = 0"""
	)
	frappe.db.sql(
		f"""update `tab{CLAIM}` claim
		set proposed_total = (
			select ifnull(sum(line.claim_amount), 0) from `tab{LINE}` line
			where line.parent = claim.name and line.parenttype = %s
		)
		where exists (
			select 1 from `tab{LINE}` line where line.parent = claim.name and line.parenttype = %s
		)""",
		(CLAIM, CLAIM),
	)


def _action_markers():
	if frappe.db.exists(ACTION, "Credit Note"):
		frappe.db.set_value(ACTION, "Credit Note", "requires_credit_note", 1, update_modified=False)
	frappe.db.sql(
		f"""update `tab{CLAIM}` claim
		join `tab{ACTION}` action on action.name = claim.action
		set claim.is_price_adjustment = ifnull(action.is_price_adjustment, 0),
			claim.requires_credit_note = ifnull(action.requires_credit_note, 0)"""
	)
