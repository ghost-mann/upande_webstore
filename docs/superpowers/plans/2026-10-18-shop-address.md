# Shop Address Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Customers use the store only on a configurable shop address served by the gateway; the ERP sends them there and keeps staff out of it.

**Architecture:** Settings live in Webstore Settings (new "Shop Address" tab). A new `services/shop.py` decides "is this a shop request" (gateway secret header), builds shop URLs, and runs the ERP-side redirect and login rules from `before_request` / `on_login`. The gateway Worker fetches its rules from a secret-protected config endpoint and falls back to its built-in rules.

**Tech Stack:** Frappe/ERPNext v16 app (Python, doctype JSON, form JS), Cloudflare Worker (plain JS, wrangler 4.100.0).

**Spec:** `docs/superpowers/specs/2026-10-18-shop-address-design.md`

## Global Constraints

- Everything ships off. With a blank shop address, or the switch off, behaviour is identical to today.
- The shop address never names or links the ERP address. That covers pages, redirects and messages.
- Staff = `user_type == "System User"`. Customer = a Website User, or any user with the Customer role and no desk role.
- Refusal copy, verbatim:
  - staff logging in on the shop: "Staff accounts sign in on the ERP."
  - customers logging in on the ERP: "Please sign in on the shop."
- Gateway headers:
  - `X-Webstore-Gateway: <secret>` (request);
  - `X-Forwarded-Host: <shop host>` (request);
  - `X-Webstore-Gateway-Version: <n>` (response marker).
- Interlock: the switch can only be turned on with a successful reachability check less than 10 minutes old.
- Tests run on `webstore-test.localhost`: `bench --site webstore-test.localhost run-tests --module upande_webstore.tests.test_shop_address`.
- Commits as ghost-mann only; no co-author lines.

## Review Focus

1. **A shop address with a trailing slash or a path** (`https://shop.x/` or `https://shop.x/store`): normalise the trailing slash, refuse a path. Test in Task 1.
2. **A request with the right secret but the switch off:** still treated as a shop request (staff refused, links use the shop) so you can test before switching on. Test in Task 3.
3. **The `host_name` cached conf leaking into later ERP requests:** after a shop request, the next direct request's `get_url()` is the ERP address. Test in Task 3.
4. **A staff account linked to a customer** (`austin@upande.com` case): counts as staff on the shop. Test in Task 3.
5. **The gateway's config fetch failing or returning garbage:** keep the last good config, else built-in rules; never fail open. Covered by a gateway check in Task 5.

---

### Task 1: Settings and the shop service

**Files:**
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.json` (new tab `shop_address_tab` before `transfer_tab`)
- Modify: `upande_webstore/upande_webstore/doctype/webstore_settings/webstore_settings.py` (validate)
- Create: `upande_webstore/services/shop.py`
- Test: `upande_webstore/tests/test_shop_address.py`

**Interfaces:**
- Produces, in `services/shop.py`:
  - `shop_address() -> str | None`: normalised `https://host`, or None when blank.
  - `shop_enabled() -> bool`: the address is set and `send_customers_to_shop` is ticked.
  - `is_shop_request() -> bool`: the request carries `X-Webstore-Gateway` equal to the secret (`hmac.compare_digest`), and an address is set.
  - `shop_url(path: str) -> str`.
  - `is_staff(user: str) -> bool`.
  - `is_customer_account(user: str) -> bool`.
- Fields:
  - `shop_address` (Data);
  - `send_customers_to_shop` (Check);
  - `gateway_secret` (Password);
  - `shop_login_attempts_per_minute` (Int, default 10);
  - `shop_allow_indexing` (Check);
  - `shop_extra_pages` (Small Text);
  - `shop_extra_methods` (Small Text);
  - `shop_last_check_ok` (Datetime, read only);
  - `shop_last_check_result` (Small Text, read only);
  - `shop_status` (HTML).

- [ ] **Write failing tests:**
  - `test_blank_address_is_off`
  - `test_trailing_slash_normalised`
  - `test_address_with_path_refused`
  - `test_http_address_refused`
  - `test_secret_header_identifies_shop_request` (right, wrong and missing secret, using `frappe.local.request` with headers set)
  - `test_staff_and_customer_classification` (System User + Customer role → staff; Website User → customer)
- [ ] Run → fail. Implement fields, validation (`frappe.ValidationError`) and helpers. Run → pass. Commit `feat(shop): shop address settings and service`.

### Task 2: Gateway config endpoint and the method allow-list

**Files:**
- Create: `upande_webstore/api/gateway.py`
- Modify: `upande_webstore/services/shop.py` (add `CUSTOMER_METHODS`, `DESK_ONLY_METHODS`)
- Test: `upande_webstore/tests/test_shop_address.py`

**Interfaces:**
- `upande_webstore.api.gateway.config()`: whitelisted, `allow_guest=True`. Raises `frappe.PageDoesNotExistError` (404) unless `is_shop_request()`. Returns:
  `{"shop_address", "send_customers_to_shop", "login_attempts_per_minute", "allow_indexing", "extra_pages": [..], "methods": [..]}`.
  `methods` = `CUSTOMER_METHODS` plus the extra methods. `CUSTOMER_METHODS` holds today's gateway list (frappe login/password methods plus webstore storefront and portal methods).

- [ ] **Write failing tests:**
  - `test_config_refuses_without_secret`
  - `test_config_returns_settings_with_secret`
  - `test_every_whitelisted_webstore_method_is_classified`: walk `upande_webstore.api.*` modules for whitelisted functions; each dotted path must be in exactly one of `CUSTOMER_METHODS` / `DESK_ONLY_METHODS`.
- [ ] Run → fail. Implement. Run → pass. Commit `feat(shop): gateway config endpoint and classified method list`.

### Task 3: ERP-side rules — redirect, links, logins

**Files:**
- Modify: `upande_webstore/services/shop.py`
- Modify: `upande_webstore/hooks.py` (`before_request` += `upande_webstore.services.shop.before_request`; `after_request` += `upande_webstore.services.shop.after_request`; `on_login` = `upande_webstore.services.shop.on_login`)
- Test: `upande_webstore/tests/test_shop_address.py`

**Interfaces:**
- `before_request()`:
  - **Shop request:** replace `frappe.local.conf` with a copy whose `host_name` is the shop address. The conf is a shared cached object, so it must never be mutated in place.
  - **Not a shop request, `shop_enabled()`, customer path:** 302 to `shop_url(path + query)`, using `portal._redirect`.
  - **Not a shop request, logged-in customer session:** log out, then redirect.
- `after_request()`: restore the original conf.
- `on_login(login_manager)`:
  - shop request and `is_staff` → `frappe.throw("Staff accounts sign in on the ERP.", frappe.AuthenticationError)`;
  - not a shop request, `shop_enabled()` and `is_customer_account` → `frappe.throw("Please sign in on the shop.", frappe.AuthenticationError)`.
- Customer paths are matched as in the gateway: `/store`, `/store/*`, `/<slug>/store*`, `/cart`, `/wishlist`, `/<slug>/cart|wishlist`, `/portal*`, `/signup`.

- [ ] **Write failing tests:**
  - `test_customer_path_redirects_when_on` (location = shop URL + same path + query)
  - `test_no_redirect_when_off`
  - `test_no_redirect_for_shop_request`
  - `test_desk_and_login_paths_never_redirect`
  - `test_get_url_is_shop_address_during_shop_request`
  - `test_get_url_restored_for_next_request` (Review Focus 3)
  - `test_staff_login_refused_on_shop`
  - `test_staff_linked_to_customer_refused_on_shop` (Review Focus 4)
  - `test_customer_login_refused_on_erp_when_on`
  - `test_customer_login_allowed_on_erp_when_off`
  - `test_secret_with_switch_off_still_refuses_staff` (Review Focus 2)
- [ ] Run → fail. Implement. Run → pass. Commit `feat(shop): send customers to the shop address and keep staff on the ERP`.

### Task 4: Customer emails use the shop address

**Files:**
- Modify: `upande_webstore/services/shop.py` (`as_shop()` context manager: swaps the conf like a shop request, no-op when no address is set)
- Modify: `upande_webstore/upande_webstore/doctype/webstore_portal_access/webstore_portal_access.py` (`password_setup_link`)
- Modify: `upande_webstore/services/provisioning.py` (`ensure_user` welcome email)
- Test: `upande_webstore/tests/test_shop_address.py`

- [ ] **Write failing tests:**
  - `test_password_setup_link_uses_shop_address` (address set, called from a desk request)
  - `test_password_setup_link_unchanged_when_blank`
  - `test_welcome_email_link_uses_shop_address` (inspect the Email Queue message for the shop host)
- [ ] Run → fail. Wrap both in `as_shop()` when `shop_address()` is set. Staff-facing mails (`api/portal.py`, `api/checkout.py`) are left alone. Run → pass. Commit `feat(shop): customer emails link to the shop address`.

### Task 5: Reachability check, interlock, status panel, daily watch

**Files:**
- Modify: `upande_webstore/services/shop.py`:
  - `check_shop_address() -> dict`, whitelisted for System Manager: GETs `shop_url("/store")` with `requests` and a 10 s timeout. It succeeds only with a 200 and the `X-Webstore-Gateway-Version` header present, then stores `shop_last_check_ok` / `shop_last_check_result`.
  - `daily_watch()`
- Modify: `webstore_settings.py` (interlock in validate), `webstore_settings.js` (buttons "Check shop address" and "Generate gateway secret"; renders `shop_status` with the DNS hint and last check)
- Modify: `hooks.py` (`scheduler_events = {"daily": ["upande_webstore.services.shop.daily_watch"]}`)
- Test: `upande_webstore/tests/test_shop_address.py`

- [ ] **Write failing tests** (patch `requests.get`):
  - `test_switch_refused_without_recent_check`
  - `test_switch_allowed_after_recent_check`
  - `test_check_fails_without_marker_header`
  - `test_daily_watch_emails_when_unreachable_and_leaves_switch_on`
  - `test_generate_secret_is_long_and_random` (≥ 32 url-safe chars)
- [ ] Run → fail. Implement. Run → pass. Run the full suite: no new failures beyond the 7 known ones. Commit `feat(shop): reachability check, safety interlock and daily watch`.

### Task 6: Gateway reads its rules from the ERP

**Files** (repo `~/vscodeProjects/mona-shop-gateway`):
- Modify: `src/index.js`:
  - fetch `${ORIGIN}/api/method/upande_webstore.api.gateway.config` with the secret, caching about 60 s at module scope; keep the last good config, else the built-in lists;
  - send `X-Webstore-Gateway` and `X-Forwarded-Host`;
  - add `X-Webstore-Gateway-Version`;
  - apply `extra_pages` / `methods` / the limit / `allow_indexing`;
  - pass the ERP's login refusal through unchanged.
- Modify: `wrangler.toml` (document the `GATEWAY_SECRET` secret), `check.sh` (new cases)
- Create: `README.md` (deploy steps)

- [ ] **Extend `check.sh`:**
  - the marker header is present;
  - a staff login through the shop gives 401 with "Staff accounts sign in on the ERP." (local only);
  - with the switch on, a direct ERP `/store` returns 302 to the shop (local only);
  - with config fetch broken (wrong secret), the built-in rules still block `/api/resource/Customer` (Review Focus 5).
- [ ] End-to-end on webstore.localhost behind `wrangler dev`:
  1. set the shop address to the dev URL and generate the secret;
  2. Check → switch on → `check.sh`, `portalcrawl.sh`;
  3. customer login, basket, staff refusal, redirect from the ERP.
- [ ] Commit `feat: read rules from the ERP, identify the gateway, and mark responses`.
