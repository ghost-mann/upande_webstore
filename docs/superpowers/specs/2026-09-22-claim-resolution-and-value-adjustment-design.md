# Claim Resolution and Value Adjustment

Turn a `Webstore Claim` from a note with a resolution box into the record of a
settlement: which invoice lines are being claimed, what commerce asks for, what
finance agrees, and what was done about it. ERPNext still issues the money.

## Problem

A claim today carries a customer, a type, a free-text description, a document
reference, and two fields the sales team fills in at the end — `resolution` and
`credit_note`. Everything between "something went wrong" and "here is a credit
note" happens in conversation and is never recorded.

Three things are missing:

- **No line detail.** A claim points at a whole Sales Invoice. A twenty-line
  invoice where two lines arrived damaged looks identical to one where
  everything did.
- **No agreed value.** The amount settled on exists only inside the credit note,
  if one was raised at all. Nothing records what was asked for, what was
  granted, or the difference.
- **No outcome.** `credit_note` is the only recordable remedy. A replacement, a
  discount on the next order, or a goodwill gesture leaves no trace.

## Constraints

- **The claim never posts to the ledger.** ERPNext owns the money. The existing
  rule stands: `assert_credit_note` requires a real return invoice
  (`is_return: 1`) for the same customer, raised in ERPNext and linked here.
  This app creates no accounting document.
- **The farm's workflow is theirs, and lives in the UI.** The `Claim Approval`
  workflow is configured in the desk. This design ships no Workflow fixture and
  must work with the one already there.
- **No farm-specific coupling.** Role names and claim actions are
  configuration, not code, the way `Webstore Claim Type` already is.
- **Deploying changes nothing.** No lines fetched, no action chosen, no approval
  recorded: a claim behaves exactly as it does today.
- **Never trust the client.** Totals are summed server-side.

## Decisions

| Decision | Choice |
|---|---|
| Money | Claim records the decision; **ERPNext issues the credit note** |
| Invoice lines | **Snapshot**, fetched by a deliberate button |
| Granularity | Per line: claimed qty and proposed value |
| Outcome | **One action per claim**, from a configurable master |
| Commerce vs finance | Commerce proposes per line; finance approves **one total**, at permlevel 1 |
| Portal | Customer sees the action and the approved total, not the lines |

### Why a snapshot

A claim is an argument about what was delivered on a particular day. An invoice
can be amended or cancelled afterwards, and a live read would let the basis of
an approved settlement shift underneath it. Stored rows are also the only place
a per-line proposed value can live.

Re-fetching is **refused once `approved_total` is set**. Without that, an
approval silently detaches from the lines it was given for.

### Data model

**`Webstore Claim Line`** — new child table on `Webstore Claim`, one row per
invoice line:

| Field | Owner | Notes |
|---|---|---|
| `item_code`, `item_name`, `uom`, `rate`, `invoiced_qty`, `invoiced_amount` | snapshot | copied at fetch, read-only |
| `is_claimed` | commerce | unticked rows contribute nothing |
| `claimed_qty` | commerce | must be ≤ `invoiced_qty` |
| `proposed_value` | commerce | what commerce asks for on this line |

The snapshot copies **standard `Sales Invoice Item` fields only**. Kaitet's
`custom_length` and `custom_box_type` are site-specific custom fields; any read
of them guards on the field existing first, the way `packing.py` guards on
`Box Type`. This app must work on a farm that has neither.

**`Webstore Claim Action`** — new standalone master, the same shape as
`Webstore Claim Type`: autonamed `field:action`, plus a description. Shipped
values: Credit Note, Replacement, Discount on next order, Goodwill, No action.
`Webstore Claim.action` is a Link to it.

**On `Webstore Claim`:**

- `proposed_total` — Currency, read-only, summed from the lines
- `approved_total`, `approval_note` — Currency and Small Text at **permlevel 1**
- `credit_note` — unchanged, and unchanged in meaning

**No arithmetic ties `approved_total` to the credit note.** They are
deliberately independent: a settlement may be paid as a replacement or a
discount rather than a credit, and a credit note may cover more than one
claim. Reconciling the two is a reporting question, not a validation rule —
enforcing equality here would block the ordinary cases.

### Permissions

`approved_total` and `approval_note` sit at permlevel 1 so commerce can read
them and only finance can write them. Frappe's permlevel is the native
mechanism; a workflow state cannot restrict a single field.

**`services/roles.py` cannot grant this today.** It hardcodes `permlevel=0` in
both its Custom DocPerm query and its `add_permission` call, so the existing
Webstore Settings role fields reach permlevel 0 only. It gains permlevel
support and a new `claim_finance_roles` field beside the three that already
exist. The existing three keep granting permlevel 0 only; the new field is
the sole grantor of permlevel 1, so widening one cannot accidentally widen
the other. Hardcoding a role name in the doctype JSON was rejected: which role is
finance is a property of the farm, not of this app.

### How this meets the existing workflow

The farm's `Claim Approval` workflow has `Approved` at docstatus 0 and
`Resolved` at docstatus 1. A docstatus of 1 makes Frappe refuse further edits
(`UpdateAfterSubmitError`, verified — no field on this doctype is
`allow_on_submit`). The sequence that works, with the workflow unchanged:

> Finance edits `approved_total` while the claim is still in **`Approved`**,
> then transitions it to **`Resolved`**, which locks it.

The lock becomes a feature: the agreed figure is frozen at the moment of
resolution. Two consequences the farm must act on, both configuration:

- `Accounts Manager` currently has **no permission at all** on `Webstore
  Claim`. It needs permlevel 0 via `portal_manager_roles` and permlevel 1 via
  the new `claim_finance_roles`.
- `Sales Master Manager`, used for the Approve transition, likewise has none.

### Behaviour

**Fetch** is a button, never automatic. It requires `customer` and
`against_document`, refuses when `approved_total` is set, and replaces the rows
when re-run.

**`validate()` owns the arithmetic.** `proposed_total` is summed from claimed
lines server-side and never read from the client — the stance `packing.py`
already takes on box counts. `claimed_qty > invoiced_qty` is refused, naming the
line.

**Seeding.** `Webstore Claim Action` is seeded from values already used on
existing claims first, then the shipped defaults — the ordering
`seed_claim_types()` uses, and for the same reason: miss the existing values and
every historical claim gets a dangling Link.

### Portal

`CLAIM_FIELDS` gains `action` and `approved_total`. It deliberately does **not**
gain the lines or `proposed_total`: the customer should see the outcome and the
figure agreed, not commerce's opening position.

## Error handling

Messages name the line, not the claim: *"Line 3 (Fuchsiana): claimed 120 of 100
invoiced."* Fetching with no invoice chosen says so rather than silently
producing nothing. Fetching after approval explains why it is refused and what
to do — withdraw the approval first. A claim with no lines is valid: not every
claim is about specific goods.

## Testing

- Per-line arithmetic and the ≤-invoiced-qty rule, as service tests.
- The fetch guard: refused once `approved_total` is set.
- Snapshot independence: amending the invoice afterwards does not move the
  claim's stored lines or its `proposed_total`.
- A permlevel test proving a commerce role can read but not write
  `approved_total`, and that the finance role can.
- Seeding, mirroring the claim-type test: an `action` value already on a claim
  survives as a master record.
- Absent-custom-field guard: the snapshot works on a site with no
  `custom_length` or `custom_box_type`.

## Non-goals

- Generating the credit note, or any accounting document, from the claim.
- Posting a Journal Entry or any ledger entry.
- Per-line actions, and claims carrying more than one action.
- Shipping or modifying the farm's Workflow; it stays in the UI.
- The 14-day claim window, which still blocks the desk and is tracked
  separately.
