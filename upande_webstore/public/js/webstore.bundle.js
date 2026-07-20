(() => {
	const call = (method, args) =>
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
				const server = JSON.parse(data._server_messages || "[]").map((m) => {
					try { return JSON.parse(m).message; } catch { return m; }
				});
				throw new Error(server.join(" ") || "Request failed");
			}
			return data.message;
		});

	const isGuest = () => !window.frappe || frappe.session?.user === "Guest" || !frappe.csrf_token;
	const toLogin = () => (window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`);
	const toast = (message, error) => {
		const el = document.createElement("div");
		el.className = `alert ${error ? "alert-danger" : "alert-success"} webstore-toast`;
		el.style.cssText = "position:fixed;top:70px;right:20px;z-index:1050;max-width:320px;";
		el.textContent = message;
		document.body.appendChild(el);
		setTimeout(() => el.remove(), 4000);
	};

	async function refreshCartBadge() {
		const badge = document.getElementById("webstore-cart-badge");
		if (!badge || isGuest()) return;
		try {
			const count = await call("upande_webstore.api.cart.get_cart_count");
			badge.textContent = count > 0 ? count : "";
		} catch {}
	}

	async function addToCart(itemCode, qty) {
		if (isGuest()) return toLogin();
		try {
			await call("upande_webstore.api.cart.add_item", { item_code: itemCode, qty: qty || 1 });
			toast("Added to cart");
			refreshCartBadge();
		} catch (e) {
			toast(e.message, true);
		}
	}

	async function toggleWishlist(product, button) {
		if (isGuest()) return toLogin();
		try {
			const result = await call("upande_webstore.api.wishlist.toggle", { product });
			toast(result.wishlisted ? "Saved to wishlist" : "Removed from wishlist");
			if (button && document.getElementById("wishlist-grid")) {
				button.closest(".col-md-4")?.remove();
			}
		} catch (e) {
			toast(e.message, true);
		}
	}

	document.addEventListener("click", async (event) => {
		const logout = event.target.closest("[data-webstore-logout]");
		if (logout) {
			event.preventDefault();
			try {
				await call("logout");
			} catch {}
			window.location.href = "/store";
			return;
		}
		const add = event.target.closest("[data-webstore-add-to-cart]");
		if (add) {
			const qty = parseFloat(document.getElementById("webstore-qty")?.value || "1");
			addToCart(add.dataset.webstoreAddToCart, qty);
			return;
		}
		const wish = event.target.closest("[data-webstore-wishlist-toggle]");
		if (wish) toggleWishlist(wish.dataset.webstoreWishlistToggle, wish);
	});

	// Variant picker
	const productRoot = () => document.getElementById("webstore-product");
	async function onAttributeChange() {
		const root = productRoot();
		if (!root || root.dataset.isTemplate !== "1") return;
		const selects = [...document.querySelectorAll("select.webstore-attribute")];
		const addBtn = document.getElementById("webstore-variant-add");
		if (selects.some((s) => !s.value)) { addBtn.disabled = true; return; }
		const attributes = Object.fromEntries(selects.map((s) => [s.dataset.attribute, s.value]));
		try {
			const result = await call("upande_webstore.api.variants.resolve_variant", {
				template_item: root.dataset.item,
				attributes,
			});
			const priceEl = document.getElementById("webstore-variant-price");
			const stockEl = document.getElementById("webstore-variant-stock");
			if (!result.item_code) {
				priceEl.textContent = "";
				stockEl.textContent = "This combination is not available.";
				addBtn.disabled = true;
				return;
			}
			priceEl.textContent = `${result.price.currency} ${result.price.rate.toFixed(2)}`;
			stockEl.textContent = result.stock.in_stock
				? result.stock.qty != null ? `In stock: ${result.stock.qty}` : "In stock"
				: "Out of stock";
			addBtn.disabled = !result.stock.in_stock;
			addBtn.dataset.variantItem = result.item_code;
		} catch (e) {
			toast(e.message, true);
		}
	}
	document.addEventListener("change", (event) => {
		if (event.target.matches("select.webstore-attribute")) onAttributeChange();
	});
	document.addEventListener("click", (event) => {
		if (event.target.id === "webstore-variant-add" && event.target.dataset.variantItem) {
			addToCart(event.target.dataset.variantItem, 1);
		}
	});

	document.addEventListener("DOMContentLoaded", refreshCartBadge);
	window.webstore = { addToCart, toggleWishlist, refreshCartBadge, call, toast };
})();
