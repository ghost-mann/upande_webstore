(() => {
  // ../upande_webstore/upande_webstore/public/js/webstore.bundle.ts
  (() => {
    const call = (method, args) => {
      var _a;
      return fetch(`/api/method/${method}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Frappe-CSRF-Token": ((_a = window.frappe) == null ? void 0 : _a.csrf_token) || ""
        },
        body: JSON.stringify(args || {})
      }).then(async (r) => {
        const data = await r.json();
        if (!r.ok) {
          const server = JSON.parse(data._server_messages || "[]").map((m) => {
            try {
              return JSON.parse(m).message;
            } catch (e) {
              return m;
            }
          });
          throw new Error(server.join(" ") || "Request failed");
        }
        return data.message;
      });
    };
    const isGuest = () => {
      var _a;
      return !window.frappe || ((_a = window.frappe.session) == null ? void 0 : _a.user) === "Guest" || !window.frappe.csrf_token;
    };
    const toLogin = () => window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`;
    const money = (amount, currency) => `${currency || ""} ${Number(amount).toLocaleString(void 0, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim();
    const esc = (value) => value.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
    function toaster() {
      let el = document.getElementById("ws-toaster");
      if (!el) {
        el = document.createElement("div");
        el.id = "ws-toaster";
        document.body.appendChild(el);
      }
      return el;
    }
    const toast = (message, error) => {
      const el = document.createElement("div");
      el.className = `ws-toast ${error ? "err" : "ok"}`;
      el.innerHTML = `<span class="ws-toast-ico">${error ? "\u2715" : "\u2713"}</span><span>${esc(message)}</span>`;
      toaster().appendChild(el);
      requestAnimationFrame(() => el.classList.add("show"));
      setTimeout(() => {
        el.classList.remove("show");
        setTimeout(() => el.remove(), 250);
      }, 3600);
    };
    async function refreshCartBadge() {
      const badge = document.getElementById("webstore-cart-badge");
      if (!badge || isGuest())
        return;
      try {
        const count = await call("upande_webstore.api.cart.get_cart_count");
        badge.textContent = count > 0 ? String(count) : "";
      } catch (e) {
      }
    }
    const drawer = () => document.getElementById("ws-cart-drawer");
    function renderCart(cart) {
      const body = document.getElementById("ws-drawer-body");
      const foot = document.getElementById("ws-drawer-foot");
      if (!body || !foot)
        return;
      if (!cart.items.length) {
        body.innerHTML = `<div class="ws-drawer-empty">\u{1F9FA}<p>Your basket is empty.</p><a class="btn btn-primary btn-sm" href="/store">Browse the store</a></div>`;
        foot.innerHTML = "";
        return;
      }
      body.innerHTML = cart.items.map((line) => `
			<div class="ws-drawer-line" data-item="${esc(line.item_code)}">
				<div class="ws-drawer-line-main">
					<a href="${line.route ? "/" + esc(line.route) : "#"}" class="ws-drawer-title">${esc(line.web_title)}</a>
					<span class="ws-sku">${esc(line.item_code)}</span>
				</div>
				<div class="ws-drawer-line-controls">
					<button class="ws-step" data-ws-step="-1" aria-label="Decrease">\u2212</button>
					<span class="ws-step-qty">${line.qty}</span>
					<button class="ws-step" data-ws-step="1" aria-label="Increase">+</button>
					<button class="ws-step ws-step-remove" data-ws-remove aria-label="Remove">\u2715</button>
				</div>
				<div class="ws-drawer-line-amount">${money(line.amount, cart.currency)}</div>
			</div>`).join("");
      foot.innerHTML = `
			<div class="ws-drawer-total"><span>Subtotal</span><strong>${money(cart.total, cart.currency)}</strong></div>
			<a href="/cart" class="ws-drawer-checkout">Checkout \u2192</a>`;
    }
    async function openCart() {
      if (isGuest())
        return toLogin();
      const dialog = drawer();
      if (!dialog)
        return;
      if (!dialog.open)
        dialog.showModal();
      try {
        renderCart(await call("upande_webstore.api.cart.get_cart"));
      } catch (e) {
        toast(e.message, true);
      }
    }
    async function stepQty(itemCode, delta) {
      const row = document.querySelector(`.ws-drawer-line[data-item="${CSS.escape(itemCode)}"] .ws-step-qty`);
      const current = parseFloat((row == null ? void 0 : row.textContent) || "0");
      try {
        const cart = await call("upande_webstore.api.cart.update_qty", { item_code: itemCode, qty: current + delta });
        renderCart(cart);
        refreshCartBadge();
      } catch (e) {
        toast(e.message, true);
      }
    }
    const palette = () => document.getElementById("ws-palette");
    let debounceTimer;
    let activeIndex = -1;
    function openPalette() {
      const dialog = palette();
      if (!dialog)
        return;
      if (!dialog.open)
        dialog.showModal();
      const input = dialog.querySelector("#ws-palette-input");
      input == null ? void 0 : input.focus();
      input == null ? void 0 : input.select();
    }
    function renderHits(hits) {
      const list = document.getElementById("ws-palette-results");
      if (!list)
        return;
      activeIndex = hits.length ? 0 : -1;
      if (!hits.length) {
        list.innerHTML = `<div class="ws-palette-empty">Nothing fresh under that name \u2014 try \u201Croses\u201D or \u201Cspray\u201D.</div>`;
        return;
      }
      list.innerHTML = hits.map((hit, index) => `
			<a class="ws-palette-hit${index === 0 ? " active" : ""}" href="/${esc(hit.route)}" data-index="${index}">
				<span class="ws-palette-thumb">${hit.image ? `<img src="${esc(hit.image)}" alt="">` : "\u{1F33F}"}</span>
				<span class="ws-palette-hit-main">
					<span class="ws-palette-hit-title">${esc(hit.web_title)}</span>
					<span class="ws-sku">${esc(hit.category || "")}</span>
				</span>
				<span class="ws-palette-hit-side">${hit.rate != null ? money(hit.rate, hit.currency) : ""}${hit.in_stock ? "" : `<em>out of stock</em>`}</span>
			</a>`).join("");
    }
    function movePalette(delta) {
      const hits = [...document.querySelectorAll(".ws-palette-hit")];
      if (!hits.length)
        return;
      activeIndex = (activeIndex + delta + hits.length) % hits.length;
      hits.forEach((hit, index) => hit.classList.toggle("active", index === activeIndex));
      hits[activeIndex].scrollIntoView({ block: "nearest" });
    }
    async function addToCart(itemCode, qty) {
      var _a;
      if (isGuest())
        return toLogin();
      try {
        await call("upande_webstore.api.cart.add_item", { item_code: itemCode, qty: qty || 1 });
        toast("Added to basket");
        refreshCartBadge();
        if ((_a = drawer()) == null ? void 0 : _a.open)
          openCart();
      } catch (e) {
        toast(e.message, true);
      }
    }
    async function toggleWishlist(product, button) {
      var _a;
      if (isGuest())
        return toLogin();
      try {
        const result = await call("upande_webstore.api.wishlist.toggle", { product });
        toast(result.wishlisted ? "Saved to wishlist" : "Removed from wishlist");
        if (button && document.getElementById("wishlist-grid")) {
          (_a = button.closest(".col-md-4")) == null ? void 0 : _a.remove();
        }
      } catch (e) {
        toast(e.message, true);
      }
    }
    const productRoot = () => document.getElementById("webstore-product");
    async function onAttributeChange() {
      const root = productRoot();
      if (!root || root.getAttribute("data-is-template") !== "1")
        return;
      const selects = [...document.querySelectorAll("select.webstore-attribute")];
      const addBtn = document.getElementById("webstore-variant-add");
      if (!addBtn)
        return;
      if (selects.some((s) => !s.value)) {
        addBtn.disabled = true;
        return;
      }
      const attributes = Object.fromEntries(selects.map((s) => [s.getAttribute("data-attribute") || "", s.value]));
      try {
        const result = await call("upande_webstore.api.variants.resolve_variant", {
          template_item: root.getAttribute("data-item"),
          attributes
        });
        const priceEl = document.getElementById("webstore-variant-price");
        const stockEl = document.getElementById("webstore-variant-stock");
        if (!priceEl || !stockEl)
          return;
        if (!result.item_code || !result.price || !result.stock) {
          priceEl.textContent = "";
          stockEl.textContent = "This combination is not available.";
          addBtn.disabled = true;
          return;
        }
        priceEl.textContent = money(result.price.rate, result.price.currency);
        stockEl.textContent = result.stock.in_stock ? result.stock.qty != null ? `In stock: ${result.stock.qty}` : "In stock" : "Out of stock";
        addBtn.disabled = !result.stock.in_stock;
        addBtn.setAttribute("data-variant-item", result.item_code);
      } catch (e) {
        toast(e.message, true);
      }
    }
    document.addEventListener("click", async (event) => {
      var _a, _b, _c;
      const target = event.target;
      const logout = target.closest("[data-webstore-logout]");
      if (logout) {
        event.preventDefault();
        try {
          await call("logout");
        } catch (e) {
        }
        window.location.href = "/store";
        return;
      }
      const cartTrigger = target.closest("[data-ws-cart-drawer]");
      if (cartTrigger) {
        event.preventDefault();
        openCart();
        return;
      }
      const searchTrigger = target.closest("[data-ws-palette]");
      if (searchTrigger) {
        event.preventDefault();
        openPalette();
        return;
      }
      const closeTrigger = target.closest("[data-ws-close]");
      if (closeTrigger) {
        (_a = closeTrigger.closest("dialog")) == null ? void 0 : _a.close();
        return;
      }
      const step = target.closest("[data-ws-step]");
      if (step) {
        const item = (_b = step.closest(".ws-drawer-line")) == null ? void 0 : _b.getAttribute("data-item");
        if (item)
          stepQty(item, parseInt(step.getAttribute("data-ws-step") || "0", 10));
        return;
      }
      const remove = target.closest("[data-ws-remove]");
      if (remove) {
        const item = (_c = remove.closest(".ws-drawer-line")) == null ? void 0 : _c.getAttribute("data-item");
        if (item) {
          try {
            renderCart(await call("upande_webstore.api.cart.remove_item", { item_code: item }));
            refreshCartBadge();
          } catch (e) {
            toast(e.message, true);
          }
        }
        return;
      }
      const add = target.closest("[data-webstore-add-to-cart]");
      if (add) {
        const qtyInput = document.getElementById("webstore-qty");
        addToCart(add.getAttribute("data-webstore-add-to-cart") || "", parseFloat((qtyInput == null ? void 0 : qtyInput.value) || "1"));
        return;
      }
      const variantAdd = target.closest("#webstore-variant-add");
      if (variantAdd) {
        const code = variantAdd.getAttribute("data-variant-item");
        if (code)
          addToCart(code, 1);
        return;
      }
      const wish = target.closest("[data-webstore-wishlist-toggle]");
      if (wish) {
        toggleWishlist(wish.getAttribute("data-webstore-wishlist-toggle") || "", wish);
        return;
      }
      if (target instanceof HTMLDialogElement)
        target.close();
    });
    document.addEventListener("change", (event) => {
      if (event.target.matches("select.webstore-attribute"))
        onAttributeChange();
    });
    document.addEventListener("input", (event) => {
      const input = event.target;
      if (input.id !== "ws-palette-input")
        return;
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(async () => {
        const q = input.value.trim();
        if (q.length < 2) {
          renderHits([]);
          return;
        }
        try {
          renderHits(await call("upande_webstore.api.search.search_products", { q }));
        } catch (e) {
        }
      }, 180);
    });
    document.addEventListener("keydown", (event) => {
      var _a;
      const inPalette = (_a = palette()) == null ? void 0 : _a.open;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openPalette();
        return;
      }
      if (event.key === "/" && !inPalette && !event.target.matches("input, textarea, select")) {
        event.preventDefault();
        openPalette();
        return;
      }
      if (inPalette) {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          movePalette(1);
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          movePalette(-1);
        }
        if (event.key === "Enter") {
          const active = document.querySelector(".ws-palette-hit.active");
          if (active) {
            event.preventDefault();
            window.location.href = active.href;
          }
        }
      }
    });
    function initReveals() {
      const nodes = [...document.querySelectorAll(".rv:not(.in)")];
      if (!nodes.length || !("IntersectionObserver" in window)) {
        nodes.forEach((n) => n.classList.add("in"));
        return;
      }
      const io = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        });
      }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
      nodes.forEach((n) => {
        if (n.getBoundingClientRect().top < window.innerHeight * 0.96) {
          n.classList.add("in");
        } else {
          io.observe(n);
        }
      });
      window.setTimeout(() => nodes.forEach((n) => n.classList.add("in")), 1600);
    }
    function initOccasionBar() {
      var _a;
      const bar = document.querySelector(".ws-occasion-bar");
      if (!bar)
        return;
      const key = `ws-occasion-dismissed:${bar.dataset.wsOccasion || ""}`;
      try {
        if (localStorage.getItem(key)) {
          bar.remove();
          return;
        }
      } catch (e) {
      }
      (_a = bar.querySelector("[data-ws-occasion-close]")) == null ? void 0 : _a.addEventListener("click", () => {
        bar.remove();
        try {
          localStorage.setItem(key, "1");
        } catch (e) {
        }
      });
    }
    document.addEventListener("DOMContentLoaded", () => {
      refreshCartBadge();
      initReveals();
      initOccasionBar();
    });
    window.webstore = { addToCart, toggleWishlist, refreshCartBadge, openCart, openPalette, call, toast };
  })();
})();
//# sourceMappingURL=webstore.bundle.QDIHUAKF.js.map
