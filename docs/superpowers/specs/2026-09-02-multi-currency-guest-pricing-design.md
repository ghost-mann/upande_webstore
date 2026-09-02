# Multi-Currency Guest Pricing

Let a farm offer its storefront in several currencies, and let an anonymous
visitor choose which one they browse in, without disturbing the price a
logged-in customer has negotiated.

## Problem

`Webstore Settings.guest_price_list` is a single Link. Every anonymous visitor
sees one currency, whatever the farm picked. Karen Roses staging carries nine
enabled selling price lists across four currencies:

| Price list | Currency |
|---|---|
| Standard Selling, Webstore Demo | KES |
| EUR Price List, Coffee EUR Price List, May EUR | EUR |
| GBP Price List, May GBP | GBP |
| USD Price List, May USD | USD |

A Dutch buyer landing on the storefront sees KES, or a Kenyan buyer sees EUR.
Neither can change it, and neither is told why.

## What makes this smaller than it looks

`api/cart.py::_require_login` gates every cart mutation, so **an anonymous
visitor can never hold a cart**. A currency choice therefore changes only what
prices are *displayed while browsing*. There are no stored cart rates to
invalidate, no cart currency to migrate, and no checkout consequence — because
by the time anyone checks out they have logged in, and `get_price_list()`
resolves a linked customer's own price list first.

One case does have teeth, and the design turns on it: **a logged-in user with no
linked Customer** falls through to the guest price list (`services/pricing.py:27`)
*and* can hold a cart. Switching currency mid-basket must not leave rows priced
in a currency the cart total no longer uses.

## Constraints

- **A customer's own price list always wins.** Negotiated pricing is never
  overridden by a currency picker. `get_price_list()` keeps checking
  `Customer.default_price_list` first.
- **Only price lists the farm offers.** A visitor may not name an arbitrary
  price list and read pricing the farm never published — the choice is validated
  against the configured table on every resolution, not trusted from the client.
- **Deploying must change nothing.** A farm that configures no table keeps
  today's single `guest_price_list` behaviour exactly.
- **No new currency conversion.** ERPNext owns rates. This design selects among
  price lists a farm has already built; it never converts.

## Decisions

| Decision | Choice |
|---|---|
| Where the offer is configured | Child table on Webstore Settings, one row per offered price list |
| What the visitor picks | **Currency**, not price list — the price list is an implementation detail |
| Where the choice lives | A cookie, `webstore_price_list`, validated on every read |
| Legacy `guest_price_list` | Kept as the fallback when the table is empty |
| Cart repricing | Re-price on switch, for the logged-in-without-customer case |
| Checkout | Unchanged — the resolved price list flows through as it does today |

### Schema

New child doctype `Webstore Guest Price List`:

| Field | Type | Note |
|---|---|---|
| `price_list` | Link → Price List | must be `selling` and `enabled` |
| `label` | Data | optional display name; blank uses the currency code |
| `is_default` | Check | the one used before a visitor chooses |

Added to Webstore Settings as `guest_price_lists` (Table), in the existing
commerce section beside `guest_price_list`. Validation on save: every row must
be a selling, enabled price list; exactly one row may be `is_default`; two rows
may not share a currency, because the visitor picks a currency and an ambiguous
mapping cannot be resolved.

### Resolution order

`services/pricing.get_price_list(user)` becomes:

```
customer's default_price_list          (unchanged, always wins)
else cookie choice, IF it names a row in guest_price_lists
else the row marked is_default
else the first row
else Webstore Settings.guest_price_list      (today's behaviour)
```

The cookie is never trusted: a value not present in the configured table is
ignored and the default used. That is what stops a visitor reading an unpublished
price list by setting a cookie by hand.

### The picker

A currency control in the storefront header, rendered only when
`guest_price_lists` holds more than one row — a farm with one currency sees no
picker. Selecting writes the cookie and reloads, so every price on the page comes
from one resolution rather than being patched client-side.

Hidden entirely for a visitor whose customer has a default price list: their
price is not theirs to change, and offering a control that does nothing is worse
than offering none.

### The cart case

For a logged-in user with no linked Customer, changing currency must re-price the
open cart through the existing `_reprice(cart)` — the same server-side
re-resolution that already runs on every cart mutation. The setter endpoint calls
it when a cart exists. An item with no price in the newly chosen list is dropped
from the cart with a message naming it, rather than silently carried at a rate
from another currency.

## Error handling

| Condition | Behaviour |
|---|---|
| Table empty | Fall back to `guest_price_list`; no picker |
| One row | Use it; no picker |
| Cookie names a row no longer offered | Ignore, use default, overwrite the cookie |
| Cookie names a disabled or non-selling list | Same |
| Chosen list has no price for an item | Item shows no price, exactly as today |
| Logged-in customer with own price list | Picker hidden, choice ignored |

## Testing

- Resolution: customer default beats cookie; cookie beats default row; default
  row beats first row; empty table falls back to `guest_price_list`.
- A cookie naming a price list absent from the table is ignored — the security
  case, and the one worth writing first.
- Validation: a buying or disabled price list is refused; two rows with the same
  currency are refused; two defaults are refused.
- Picker renders for two rows, not for one, not for a customer with their own list.
- Cart: switching currency re-prices an open cart; an item unpriced in the new
  list is dropped with a message.
- Inert path: no table configured behaves exactly as today.

## Non-goals

- **Currency conversion.** No exchange rates are read or written.
- **Per-currency stock or box rules.** Pack rates are stems, not money.
- **Guest carts.** Login still gates the cart; this design does not change that.
- **Remembering the choice across devices.** A cookie is per-browser, and an
  anonymous visitor has nowhere else to keep it.

## Prerequisites before enabling

1. Build the price lists per currency in ERPNext and price the published items in
   each — an item absent from a list simply shows no price.
2. Add the rows to Webstore Settings and mark one default.
3. The picker appears once a second row exists.
