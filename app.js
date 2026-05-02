/**
 * NexRec AI - Frontend Application Logic
 * Communicates with Python backend API at localhost:8000
 */

const API = "/api";

// ──────────────────────────────────────────
// STATE
// ──────────────────────────────────────────
const state = {
  products: [],
  categories: [],
  viewedIds: JSON.parse(localStorage.getItem("viewedIds") || "[]"),
  recsGenerated: parseInt(localStorage.getItem("recsGenerated") || "0"),
  searchQuery: "",
  selectedCategory: "",
  currentView: "home",
};

// ──────────────────────────────────────────
// DOM REFS
// ──────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const views = { home: $("viewHome"), catalog: $("viewCatalog"), recommendations: $("viewRecommendations"), analytics: $("viewAnalytics") };
const navItems = document.querySelectorAll(".nav-item");

// ──────────────────────────────────────────
// UTILITIES
// ──────────────────────────────────────────
const categoryEmoji = {
  "Electronics": "💻", "Footwear": "👟", "Clothing": "👕",
  "Home & Kitchen": "🏠", "Accessories": "🕶️", "default": "📦"
};

function emoji(category) {
  return categoryEmoji[category] || categoryEmoji["default"];
}

function formatPrice(p) {
  return "$" + parseFloat(p).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function renderStars(rating) {
  return `
    <svg viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
    ${rating}
  `;
}

function showToast(msg, duration = 2500) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => t.classList.add("hidden"), duration);
}

// ──────────────────────────────────────────
// API CALLS
// ──────────────────────────────────────────
async function fetchProducts(q = "", category = "") {
  let url = `${API}/products`;
  if (q || category) {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    url = `${API}/products/search?${params}`;
  }
  const res = await fetch(url);
  const data = await res.json();
  return data.products || [];
}

async function fetchCategories() {
  const res = await fetch(`${API}/categories`);
  const data = await res.json();
  return data.categories || [];
}

async function fetchRecommendations(viewedIds, limit = 4) {
  const res = await fetch(`${API}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ viewed_ids: viewedIds, limit }),
  });
  const data = await res.json();
  state.recsGenerated += data.recommendations?.length || 0;
  localStorage.setItem("recsGenerated", state.recsGenerated);
  $("statRecs").textContent = state.recsGenerated;
  return data.recommendations || [];
}

// ──────────────────────────────────────────
// PRODUCT CARD
// ──────────────────────────────────────────
function createProductCard(product) {
  const isViewed = state.viewedIds.includes(product.id);
  const card = document.createElement("div");
  card.className = `product-card${isViewed ? " viewed" : ""}`;
  card.dataset.id = product.id;

  card.innerHTML = `
    <div class="card-img" style="background:${randomGradient(product.id)}">
      ${emoji(product.category)}
    </div>
    <div class="card-body">
      <p class="card-category">${product.category}</p>
      <h3 class="card-name">${product.name}</h3>
      <p class="card-desc">${product.description}</p>
      <div class="card-meta">
        <span class="card-price">${formatPrice(product.price)}</span>
        <span class="card-rating">${renderStars(product.rating)}</span>
      </div>
      <p class="card-reviews">${product.reviews.toLocaleString()} reviews</p>
    </div>
  `;

  card.addEventListener("click", () => openModal(product));
  return card;
}

function randomGradient(seed) {
  const palettes = [
    "linear-gradient(135deg,#1e1b4b,#312e81)",
    "linear-gradient(135deg,#0c4a6e,#0e7490)",
    "linear-gradient(135deg,#14532d,#15803d)",
    "linear-gradient(135deg,#7c2d12,#b45309)",
    "linear-gradient(135deg,#4c0519,#9f1239)",
    "linear-gradient(135deg,#1e3a5f,#7c3aed)",
  ];
  return palettes[seed % palettes.length];
}

// ──────────────────────────────────────────
// MODAL
// ──────────────────────────────────────────
function openModal(product) {
  // Track view
  if (!state.viewedIds.includes(product.id)) {
    state.viewedIds.push(product.id);
    localStorage.setItem("viewedIds", JSON.stringify(state.viewedIds));
    $("statViewed").textContent = state.viewedIds.length;
    // Mark card as viewed in all grids
    document.querySelectorAll(`.product-card[data-id="${product.id}"]`).forEach(c => c.classList.add("viewed"));
  }

  const inner = $("modalInner");
  inner.innerHTML = `
    <div class="modal-img" style="background:${randomGradient(product.id)}; font-size:5rem;">
      ${emoji(product.category)}
    </div>
    <p class="modal-category">${product.category}</p>
    <h2 class="modal-name">${product.name}</h2>
    <p class="modal-desc">${product.description}</p>
    <div class="modal-stats">
      <div class="modal-stat">
        <p class="modal-stat-label">Price</p>
        <p class="modal-stat-value">${formatPrice(product.price)}</p>
      </div>
      <div class="modal-stat">
        <p class="modal-stat-label">Rating</p>
        <p class="modal-stat-value" style="color:var(--accent-orange)">⭐ ${product.rating}</p>
      </div>
      <div class="modal-stat">
        <p class="modal-stat-label">Reviews</p>
        <p class="modal-stat-value">${product.reviews.toLocaleString()}</p>
      </div>
    </div>
    <div class="modal-tags">
      ${product.tags.map(t => `<span class="modal-tag">#${t}</span>`).join("")}
    </div>
    <div class="modal-actions">
      <button class="btn-add-cart" id="btnAddCart">🛒 Add to Cart</button>
      <button class="btn-wishlist" id="btnWishlist">♡ Wishlist</button>
    </div>
  `;

  $("modalOverlay").classList.remove("hidden");
  $("btnAddCart").addEventListener("click", () => { showToast(`✅ "${product.name}" added to cart!`); closeModal(); });
  $("btnWishlist").addEventListener("click", () => { showToast(`♡ "${product.name}" saved to wishlist!`); });

  // Refresh recommendations silently
  setTimeout(() => {
    refreshRecommendations();
    updateAnalytics();
  }, 200);
}

function closeModal() {
  $("modalOverlay").classList.add("hidden");
}

$("modalClose").addEventListener("click", closeModal);
$("modalOverlay").addEventListener("click", (e) => { if (e.target === $("modalOverlay")) closeModal(); });

// ──────────────────────────────────────────
// RENDER GRIDS
// ──────────────────────────────────────────
function renderGrid(gridEl, products) {
  gridEl.innerHTML = "";
  if (!products.length) {
    gridEl.innerHTML = `<p style="color:var(--text-muted);font-size:.9rem;grid-column:1/-1;padding:2rem 0;">No products found.</p>`;
    return;
  }
  products.forEach(p => gridEl.appendChild(createProductCard(p)));
}

async function refreshRecommendations() {
  const recs = await fetchRecommendations(state.viewedIds, 8);

  // Home recs
  renderGrid($("homeRecsGrid"), recs.slice(0, 4));

  // Recommendations page
  const recGrid = $("recGrid");
  const recEmpty = $("recEmpty");
  if (recs.length === 0) {
    recGrid.innerHTML = "";
    recEmpty.classList.remove("hidden");
  } else {
    recEmpty.classList.add("hidden");
    renderGrid(recGrid, recs);
  }
}

// ──────────────────────────────────────────
// ANALYTICS
// ──────────────────────────────────────────
function updateAnalytics() {
  const viewedProducts = state.products.filter(p => state.viewedIds.includes(p.id));

  // Category scores
  const catFreq = {};
  const tagFreq = {};
  viewedProducts.forEach(p => {
    catFreq[p.category] = (catFreq[p.category] || 0) + 1;
    p.tags.forEach(t => tagFreq[t] = (tagFreq[t] || 0) + 1);
  });

  const maxCat = Math.max(1, ...Object.values(catFreq));
  $("categoryBars").innerHTML = Object.entries(catFreq).length
    ? Object.entries(catFreq).sort((a, b) => b[1] - a[1]).map(([cat, count]) => `
        <div class="bar-row">
          <span class="bar-label">${emoji(cat)} ${cat}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.round((count / maxCat) * 100)}%"></div></div>
          <span class="bar-value">${count}</span>
        </div>`).join("")
    : `<p style="color:var(--text-muted);font-size:.85rem;">No data yet. Browse some products!</p>`;

  // Tag cloud
  const sortedTags = Object.entries(tagFreq).sort((a, b) => b[1] - a[1]);
  const maxTag = sortedTags[0]?.[1] || 1;
  $("tagCloud").innerHTML = sortedTags.length
    ? sortedTags.map(([tag, count]) =>
        `<span class="tag-pill ${count >= maxTag * 0.6 ? "hot" : ""}">#${tag} <small style="opacity:.6">${count}</small></span>`
      ).join("")
    : `<p style="color:var(--text-muted);font-size:.85rem;">Browse products to build your profile.</p>`;

  // Session summary
  const avgPrice = viewedProducts.length
    ? (viewedProducts.reduce((s, p) => s + p.price, 0) / viewedProducts.length).toFixed(2)
    : "—";
  const topCat = Object.entries(catFreq).sort((a, b) => b[1] - a[1])[0]?.[0] || "—";
  $("sessionSummary").innerHTML = `
    <div class="summary-row"><span>Products Viewed</span><span>${state.viewedIds.length}</span></div>
    <div class="summary-row"><span>AI Recommendations Served</span><span>${state.recsGenerated}</span></div>
    <div class="summary-row"><span>Top Category Interest</span><span>${topCat !== "—" ? emoji(topCat) + " " + topCat : "—"}</span></div>
    <div class="summary-row"><span>Avg. Viewed Price</span><span>${avgPrice !== "—" ? "$" + avgPrice : "—"}</span></div>
    <div class="summary-row"><span>Unique Tags Explored</span><span>${Object.keys(tagFreq).length}</span></div>
  `;
}

// ──────────────────────────────────────────
// VIEW SWITCHING
// ──────────────────────────────────────────
const viewMeta = {
  home:            { title: "Dashboard",           subtitle: "Next-Generation AI Product Recommendation Platform" },
  catalog:         { title: "Product Catalog",     subtitle: "Browse all available products" },
  recommendations: { title: "AI Recommendations", subtitle: "Personalized picks powered by our AI engine" },
  analytics:       { title: "Analytics",           subtitle: "Your browsing profile and AI insights" },
};

function switchView(viewName) {
  state.currentView = viewName;
  Object.entries(views).forEach(([k, el]) => el.classList.toggle("hidden", k !== viewName));
  navItems.forEach(n => n.classList.toggle("active", n.dataset.view === viewName));
  const meta = viewMeta[viewName];
  $("pageTitle").textContent = meta.title;
  $("pageSubtitle").textContent = meta.subtitle;

  if (viewName === "analytics") updateAnalytics();
  if (viewName === "recommendations") refreshRecommendations();
  if (viewName === "catalog") {
    $("catalogCount").textContent = filteredProducts().length;
    renderGrid($("catalogGrid"), filteredProducts());
  }
}

navItems.forEach(n => n.addEventListener("click", (e) => { e.preventDefault(); switchView(n.dataset.view); }));
$("viewAllLink").addEventListener("click", (e) => { e.preventDefault(); switchView("catalog"); });
$("goCatalogBtn").addEventListener("click", () => switchView("catalog"));

// ──────────────────────────────────────────
// SEARCH & FILTER
// ──────────────────────────────────────────
function filteredProducts() {
  const q = state.searchQuery.toLowerCase();
  const cat = state.selectedCategory;
  return state.products.filter(p =>
    (!q || p.name.toLowerCase().includes(q) || p.tags.some(t => t.includes(q))) &&
    (!cat || p.category === cat)
  );
}

let searchTimeout;
$("searchInput").addEventListener("input", (e) => {
  state.searchQuery = e.target.value;
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    if (state.currentView === "catalog") {
      const fp = filteredProducts();
      $("catalogCount").textContent = fp.length;
      renderGrid($("catalogGrid"), fp);
    }
  }, 300);
});

$("categoryFilter").addEventListener("change", (e) => {
  state.selectedCategory = e.target.value;
  if (state.currentView === "catalog") {
    const fp = filteredProducts();
    $("catalogCount").textContent = fp.length;
    renderGrid($("catalogGrid"), fp);
  }
});

// ──────────────────────────────────────────
// INIT
// ──────────────────────────────────────────
async function init() {
  try {
    // Load data in parallel
    const [products, categories] = await Promise.all([fetchProducts(), fetchCategories()]);
    state.products = products;
    state.categories = categories;

    // Stats
    $("statTotal").textContent = products.length;
    $("statCategories").textContent = categories.length;
    $("statViewed").textContent = state.viewedIds.length;
    $("statRecs").textContent = state.recsGenerated;

    // Populate category dropdown
    const catSelect = $("categoryFilter");
    categories.forEach(cat => {
      const opt = document.createElement("option");
      opt.value = cat;
      opt.textContent = `${emoji(cat)} ${cat}`;
      catSelect.appendChild(opt);
    });

    // Top rated products (sorted by rating)
    const topRated = [...products].sort((a, b) => b.rating - a.rating).slice(0, 4);
    renderGrid($("topRatedGrid"), topRated);

    // Initial catalog render
    renderGrid($("catalogGrid"), products);
    $("catalogCount").textContent = products.length;

    // AI recommendations
    await refreshRecommendations();

  } catch (err) {
    console.error("Failed to connect to backend:", err);
    document.querySelectorAll(".skeleton-card").forEach(s => {
      s.innerHTML = `<div style="padding:2rem;color:var(--accent-red);font-size:.85rem;">⚠️ Cannot connect to backend.<br>Make sure <code>python app.py</code> is running.</div>`;
      s.style.height = "auto";
    });
  }
}

document.addEventListener("DOMContentLoaded", init);
