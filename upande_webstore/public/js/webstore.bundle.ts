// Upande Webstore storefront runtime (TypeScript, bundled by frappe esbuild)
declare global {
	interface Window {
		frappe?: { csrf_token?: string; session?: { user?: string } };
		webstore: {
			addToCart: (itemCode: string, qty?: number) => Promise<void>;
			toggleWishlist: (product: string, button?: Element | null) => Promise<void>;
			refreshCartBadge: () => Promise<void>;
			openCart: () => Promise<void>;
			openPalette: () => void;
			call: <T = unknown>(method: string, args?: Record<string, unknown>) => Promise<T>;
			toast: (message: string, error?: boolean) => void;
		};
	}
}

interface PriceInfo { rate: number; currency: string; price_list: string; is_customer_price: boolean }
interface StockInfo { in_stock: boolean; qty: number | null; show_qty: boolean }
interface VariantResult { item_code: string | null; price?: PriceInfo; stock?: StockInfo }
interface CartLine { item_code: string; item_name: string; web_title: string; route: string | null; qty: number; rate: number; amount: number }
interface Cart { name: string | null; items: CartLine[]; total: number; currency: string | null; count: number }
interface SearchHit { web_title: string; route: string; item: string; image: string | null; category: string | null; rate: number | null; currency: string | null; in_stock: boolean; has_variants: boolean }

(() => {
	const call = <T = unknown>(method: string, args?: Record<string, unknown>): Promise<T> =>
		fetch(`/api/method/${method}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": window.frappe?.csrf_token || "",
			},
			body: JSON.stringify(args || {}),
		}).then(async (r) => {
			const data = await r.json();
			if (!r.ok) {
				const server = JSON.parse(data._server_messages || "[]").map((m: string) => {
					try { return JSON.parse(m).message; } catch { return m; }
				});
				throw new Error(server.join(" ") || "Request failed");
			}
			return data.message as T;
		});

	const isGuest = () => !window.frappe || window.frappe.session?.user === "Guest" || !window.frappe.csrf_token;
	const toLogin = () => (window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`);
	const money = (amount: number, currency: string | null) =>
		`${currency || ""} ${Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim();
	const esc = (value: string) => value.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

	/* ---------- toasts (shadcn/sonner style) ---------- */
	function toaster(): HTMLElement {
		let el = document.getElementById("ws-toaster");
		if (!el) {
			el = document.createElement("div");
			el.id = "ws-toaster";
			document.body.appendChild(el);
		}
		return el;
	}
	const toast = (message: string, error?: boolean): void => {
		const el = document.createElement("div");
		el.className = `ws-toast ${error ? "err" : "ok"}`;
		el.innerHTML = `<span class="ws-toast-ico">${error ? "✕" : "✓"}</span><span>${esc(message)}</span>`;
		toaster().appendChild(el);
		requestAnimationFrame(() => el.classList.add("show"));
		setTimeout(() => {
			el.classList.remove("show");
			setTimeout(() => el.remove(), 250);
		}, 3600);
	};

	/* ---------- cart badge ---------- */
	async function refreshCartBadge(): Promise<void> {
		const badge = document.getElementById("webstore-cart-badge");
		if (!badge || isGuest()) return;
		try {
			const count = await call<number>("upande_webstore.api.cart.get_cart_count");
			badge.textContent = count > 0 ? String(count) : "";
		} catch { /* silent */ }
	}

	/* ---------- cart drawer ---------- */
	const drawer = () => document.getElementById("ws-cart-drawer") as HTMLDialogElement | null;

	function renderCart(cart: Cart): void {
		const body = document.getElementById("ws-drawer-body");
		const foot = document.getElementById("ws-drawer-foot");
		if (!body || !foot) return;
		if (!cart.items.length) {
			body.innerHTML = `<div class="ws-drawer-empty">🧺<p>Your basket is empty.</p><a class="btn btn-primary btn-sm" href="/store">Browse the store</a></div>`;
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
					<button class="ws-step" data-ws-step="-1" aria-label="Decrease">−</button>
					<span class="ws-step-qty">${line.qty}</span>
					<button class="ws-step" data-ws-step="1" aria-label="Increase">+</button>
					<button class="ws-step ws-step-remove" data-ws-remove aria-label="Remove">✕</button>
				</div>
				<div class="ws-drawer-line-amount">${money(line.amount, cart.currency)}</div>
			</div>`).join("");
		foot.innerHTML = `
			<div class="ws-drawer-total"><span>Subtotal</span><strong>${money(cart.total, cart.currency)}</strong></div>
			<a href="/cart" class="ws-drawer-checkout">Checkout →</a>`;
	}

	async function openCart(): Promise<void> {
		if (isGuest()) return toLogin();
		const dialog = drawer();
		if (!dialog) return;
		if (!dialog.open) dialog.showModal();
		try {
			renderCart(await call<Cart>("upande_webstore.api.cart.get_cart"));
		} catch (e) { toast((e as Error).message, true); }
	}

	async function stepQty(itemCode: string, delta: number): Promise<void> {
		const row = document.querySelector(`.ws-drawer-line[data-item="${CSS.escape(itemCode)}"] .ws-step-qty`);
		const current = parseFloat(row?.textContent || "0");
		try {
			const cart = await call<Cart>("upande_webstore.api.cart.update_qty", { item_code: itemCode, qty: current + delta });
			renderCart(cart);
			refreshCartBadge();
		} catch (e) { toast((e as Error).message, true); }
	}

	/* ---------- command palette (⌘K) ---------- */
	const palette = () => document.getElementById("ws-palette") as HTMLDialogElement | null;
	let debounceTimer: number | undefined;
	let activeIndex = -1;

	function openPalette(): void {
		const dialog = palette();
		if (!dialog) return;
		if (!dialog.open) dialog.showModal();
		const input = dialog.querySelector<HTMLInputElement>("#ws-palette-input");
		input?.focus();
		input?.select();
	}

	function renderHits(hits: SearchHit[]): void {
		const list = document.getElementById("ws-palette-results");
		if (!list) return;
		activeIndex = hits.length ? 0 : -1;
		if (!hits.length) {
			list.innerHTML = `<div class="ws-palette-empty">Nothing fresh under that name — try “roses” or “coffee”.</div>`;
			return;
		}
		list.innerHTML = hits.map((hit, index) => `
			<a class="ws-palette-hit${index === 0 ? " active" : ""}" href="/${esc(hit.route)}" data-index="${index}">
				<span class="ws-palette-thumb">${hit.image ? `<img src="${esc(hit.image)}" alt="">` : "🌿"}</span>
				<span class="ws-palette-hit-main">
					<span class="ws-palette-hit-title">${esc(hit.web_title)}</span>
					<span class="ws-sku">${esc(hit.category || "")}</span>
				</span>
				<span class="ws-palette-hit-side">${hit.rate != null ? money(hit.rate, hit.currency) : ""}${hit.in_stock ? "" : `<em>out of stock</em>`}</span>
			</a>`).join("");
	}

	function movePalette(delta: number): void {
		const hits = [...document.querySelectorAll<HTMLElement>(".ws-palette-hit")];
		if (!hits.length) return;
		activeIndex = (activeIndex + delta + hits.length) % hits.length;
		hits.forEach((hit, index) => hit.classList.toggle("active", index === activeIndex));
		hits[activeIndex].scrollIntoView({ block: "nearest" });
	}

	/* ---------- shopping actions ---------- */
	async function addToCart(itemCode: string, qty?: number): Promise<void> {
		if (isGuest()) return toLogin();
		try {
			await call("upande_webstore.api.cart.add_item", { item_code: itemCode, qty: qty || 1 });
			toast("Added to basket");
			refreshCartBadge();
			if (drawer()?.open) openCart();
		} catch (e) { toast((e as Error).message, true); }
	}

	async function toggleWishlist(product: string, button?: Element | null): Promise<void> {
		if (isGuest()) return toLogin();
		try {
			const result = await call<{ wishlisted: boolean; count: number }>("upande_webstore.api.wishlist.toggle", { product });
			toast(result.wishlisted ? "Saved to wishlist" : "Removed from wishlist");
			if (button && document.getElementById("wishlist-grid")) {
				button.closest(".col-md-4")?.remove();
			}
		} catch (e) { toast((e as Error).message, true); }
	}

	/* ---------- variant picker ---------- */
	const productRoot = () => document.getElementById("webstore-product");
	async function onAttributeChange(): Promise<void> {
		const root = productRoot();
		if (!root || root.getAttribute("data-is-template") !== "1") return;
		const selects = [...document.querySelectorAll<HTMLSelectElement>("select.webstore-attribute")];
		const addBtn = document.getElementById("webstore-variant-add") as HTMLButtonElement | null;
		if (!addBtn) return;
		if (selects.some((s) => !s.value)) { addBtn.disabled = true; return; }
		const attributes = Object.fromEntries(selects.map((s) => [s.getAttribute("data-attribute") || "", s.value]));
		try {
			const result = await call<VariantResult>("upande_webstore.api.variants.resolve_variant", {
				template_item: root.getAttribute("data-item"), attributes,
			});
			const priceEl = document.getElementById("webstore-variant-price");
			const stockEl = document.getElementById("webstore-variant-stock");
			if (!priceEl || !stockEl) return;
			if (!result.item_code || !result.price || !result.stock) {
				priceEl.textContent = "";
				stockEl.textContent = "This combination is not available.";
				addBtn.disabled = true;
				return;
			}
			priceEl.textContent = money(result.price.rate, result.price.currency);
			stockEl.textContent = result.stock.in_stock
				? result.stock.qty != null ? `In stock: ${result.stock.qty}` : "In stock"
				: "Out of stock";
			addBtn.disabled = !result.stock.in_stock;
			addBtn.setAttribute("data-variant-item", result.item_code);
		} catch (e) { toast((e as Error).message, true); }
	}

	/* ---------- global listeners ---------- */
	document.addEventListener("click", async (event) => {
		const target = event.target as HTMLElement;
		const logout = target.closest("[data-webstore-logout]");
		if (logout) {
			event.preventDefault();
			try { await call("logout"); } catch { /* session already gone */ }
			window.location.href = "/store";
			return;
		}
		const cartTrigger = target.closest("[data-ws-cart-drawer]");
		if (cartTrigger) { event.preventDefault(); openCart(); return; }
		const searchTrigger = target.closest("[data-ws-palette]");
		if (searchTrigger) { event.preventDefault(); openPalette(); return; }
		const closeTrigger = target.closest("[data-ws-close]");
		if (closeTrigger) { closeTrigger.closest("dialog")?.close(); return; }
		const step = target.closest<HTMLElement>("[data-ws-step]");
		if (step) {
			const item = step.closest<HTMLElement>(".ws-drawer-line")?.getAttribute("data-item");
			if (item) stepQty(item, parseInt(step.getAttribute("data-ws-step") || "0", 10));
			return;
		}
		const remove = target.closest("[data-ws-remove]");
		if (remove) {
			const item = remove.closest<HTMLElement>(".ws-drawer-line")?.getAttribute("data-item");
			if (item) {
				try {
					renderCart(await call<Cart>("upande_webstore.api.cart.remove_item", { item_code: item }));
					refreshCartBadge();
				} catch (e) { toast((e as Error).message, true); }
			}
			return;
		}
		const add = target.closest<HTMLElement>("[data-webstore-add-to-cart]");
		if (add) {
			const qtyInput = document.getElementById("webstore-qty") as HTMLInputElement | null;
			addToCart(add.getAttribute("data-webstore-add-to-cart") || "", parseFloat(qtyInput?.value || "1"));
			return;
		}
		const variantAdd = target.closest("#webstore-variant-add");
		if (variantAdd) {
			const code = variantAdd.getAttribute("data-variant-item");
			if (code) addToCart(code, 1);
			return;
		}
		const wish = target.closest<HTMLElement>("[data-webstore-wishlist-toggle]");
		if (wish) { toggleWishlist(wish.getAttribute("data-webstore-wishlist-toggle") || "", wish); return; }
		// click on the translucent backdrop area of a native dialog closes it
		if (target instanceof HTMLDialogElement) target.close();
	});

	document.addEventListener("change", (event) => {
		if ((event.target as HTMLElement).matches("select.webstore-attribute")) onAttributeChange();
	});

	document.addEventListener("input", (event) => {
		const input = event.target as HTMLInputElement;
		if (input.id !== "ws-palette-input") return;
		window.clearTimeout(debounceTimer);
		debounceTimer = window.setTimeout(async () => {
			const q = input.value.trim();
			if (q.length < 2) { renderHits([]); return; }
			try {
				renderHits(await call<SearchHit[]>("upande_webstore.api.search.search_products", { q }));
			} catch { /* transient */ }
		}, 180);
	});

	document.addEventListener("keydown", (event) => {
		const inPalette = palette()?.open;
		if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
			event.preventDefault();
			openPalette();
			return;
		}
		if (event.key === "/" && !inPalette && !(event.target as HTMLElement).matches("input, textarea, select")) {
			event.preventDefault();
			openPalette();
			return;
		}
		if (inPalette) {
			if (event.key === "ArrowDown") { event.preventDefault(); movePalette(1); }
			if (event.key === "ArrowUp") { event.preventDefault(); movePalette(-1); }
			if (event.key === "Enter") {
				const active = document.querySelector<HTMLAnchorElement>(".ws-palette-hit.active");
				if (active) { event.preventDefault(); window.location.href = active.href; }
			}
		}
	});

	function initReveals(): void {
		const nodes = [...document.querySelectorAll<HTMLElement>(".rv:not(.in)")];
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
			// reveal immediately when already in the first viewport (no observer race)
			if (n.getBoundingClientRect().top < window.innerHeight * 0.96) {
				n.classList.add("in");
			} else {
				io.observe(n);
			}
		});
		// safety net: never leave content hidden (broken observer, prerender, print)
		window.setTimeout(() => nodes.forEach((n) => n.classList.add("in")), 1600);
	}

	document.addEventListener("DOMContentLoaded", () => {
		refreshCartBadge();
		initReveals();
	});
	window.webstore = { addToCart, toggleWishlist, refreshCartBadge, openCart, openPalette, call, toast };
})();

export {};
