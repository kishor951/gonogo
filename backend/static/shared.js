// Shared by every page: the shop's numbers and rules. They live in BigQuery (GET/PUT /api/settings);
// this browser keeps a copy only as an offline fallback.
const RULE_GROUPS = [
  ["Your shop", [
    ["launch_cost", "Launch cost (₹)", 10000, "Samples, photos, listing and first promotion for one new product."],
  ]],
  ["Costs per order", [
    ["shipping_per_unit", "Shipping per order (₹)", 60, "Returns cost this twice, once each way."],
    ["platform_fee_pct", "Platform and payment fees (%)", 15, "Marketplace commission plus payment gateway, as % of price."],
  ]],
  ["Stock", [
    ["lead_time_weeks", "Supplier lead time (weeks)", 2, "Time from placing an order to having stock."],
    ["cover_weeks", "Weeks of stock to hold", 4, "Opening order = weekly sales x (lead time + cover)."],
  ]],
  ["Decision rules", [
    ["min_margin_pct", "Minimum margin (%)", 20, "Hard rule: below this, the verdict is no-go."],
    ["max_breakeven_weeks", "Break-even within (weeks)", 12, "Hard rule: launch cost must be earned back in this time."],
    ["min_velocity", "Minimum sales speed vs shop average", 0.7, "Hard rule: comparables must sell at least this fast (1.0 = average)."],
    ["price_band_pct", "Comparable price band (± %)", 30, "Which products count as comparable, by price."],
  ]],
  ["Experiment budget", [
    ["experiment_pct", "Share of monthly profit for new products (%)", 10, "Adjusted up for growth and down for slow stock. See the budget on this page."],
    ["launches_per_month", "New launches per month", 2, "Hard rule: each launch's opening order + launch cost must fit its share."],
  ]],
];
const RULES = RULE_GROUPS.flatMap(([, rules]) => rules);
const STORE_KEY = "gonogo.settings.v2";
const DEFAULT_RULES = Object.fromEntries(RULES.map(([k, , v]) => [k, v]));

// The browser's offline copy.
function loadOrg() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch (e) { saved = {}; }
  return {shop_name: saved.shop_name || "", rules: {...DEFAULT_RULES, ...(saved.rules || {})}, profile: saved.profile || {}, source: "browser"};
}
function saveOrg(org) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify({shop_name: org.shop_name, rules: org.rules, profile: org.profile || {}})); return true; } catch (e) { return false; }
}

// The shop's saved rules from BigQuery; falls back to this browser's copy if the server can't be reached.
async function fetchSettings() {
  try {
    const res = await fetch("/api/settings");
    if (!res.ok) throw new Error();
    const s = await res.json();
    const org = {shop_name: s.shop_name || "", rules: {...DEFAULT_RULES, ...s.rules}, profile: s.profile || {}, updated_at: s.updated_at, source: "bigquery"};
    saveOrg(org);
    setSidebarShop(org.shop_name, org.profile.tagline);
    return org;
  } catch (e) {
    return loadOrg();
  }
}

// Save to BigQuery: send only what this page changes ({rules} or {shop_name, profile}); the server keeps the rest.
// Throws with the server's message if that fails (the caller keeps a local copy).
async function putSettings(changes) {
  const res = await fetch("/api/settings", {method: "PUT", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(changes)});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `The server answered ${res.status}.`);
  const saved = {shop_name: data.shop_name, rules: {...DEFAULT_RULES, ...data.rules}, profile: data.profile || {}, updated_at: data.updated_at, source: "bigquery"};
  saveOrg(saved);
  return saved;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const inr = (n) => n == null ? "-" : "₹" + Math.round(n).toLocaleString("en-IN");
const num = (n) => n == null ? "-" : Math.round(n).toLocaleString("en-IN");
const pctText = (x, d = 1) => x == null ? "-" : (x * 100).toFixed(d) + "%";
const $ = (id) => document.getElementById(id);
const inrShort = (n) => n == null ? "-" : Math.abs(n) >= 1e7 ? "₹" + (n / 1e7).toFixed(Math.abs(n) >= 1e8 ? 0 : 1) + " Cr"
  : Math.abs(n) >= 1e5 ? "₹" + (n / 1e5).toFixed(Math.abs(n) >= 1e6 ? 0 : 1) + " L" : inr(n);
const longDate = (iso) => iso ? new Date(String(iso).slice(0, 10) + "T00:00:00").toLocaleDateString("en-IN", {day: "numeric", month: "short", year: "numeric"}) : "-";

// --- the sidebar, the same on every page ---
const DISCOVERY = ["/", "Discovery", "Decide on a new product", "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8z"];
const NAV = [
  ["/business", "Business", "", "M4 20V11M10 20V5M16 20v-6M2 20h20"],
  ["/products", "Products", "", "M3 12V4h8l9 9-8 8zM7.5 7.5h.01"],
  ["/inventory", "Inventory", "", "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10"],
  ["/sales", "Sales", "", "M3 17l6-6 4 4 8-8M15 7h6v6"],
  ["/returns", "Returns", "", "M9 14L4 9l5-5M4 9h11a5 5 0 010 10h-3"],
  ["/customers", "Customers", "", "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM22 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8"],
  ["/suppliers", "Suppliers", "", "M1 4h14v12H1zM15 8h4l3 3v5h-7M5.5 21a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM18.5 21a2.5 2.5 0 100-5 2.5 2.5 0 000 5z"],
];
// Recent checks: conversations from Discovery, saved in this browser (newest first).
function recentChecksHTML() {
  let list = [];
  try { list = JSON.parse(localStorage.getItem("gonogo.checks.v1") || "[]"); } catch (e) { list = []; }
  const open = new URLSearchParams(location.search).get("c");
  const head = `<div class="group group-row">Recent checks <a class="new-check" href="/" title="Start a new check">+ New</a></div>`;
  if (!list.length) return head + `<p class="recent-empty">Your checks will appear here.</p>`;
  return head + `<div class="recent-list">${list.slice(0, 12).map(c => `<a class="recent" href="/?c=${encodeURIComponent(c.id)}"${c.id === open ? ' aria-current="page"' : ""}
      title="${esc(c.title)}"><span class="vdot ${esc(c.verdict)}" aria-hidden="true"></span><span>${esc(c.title)}</span></a>`).join("")}</div>`;
}

function renderSidebar() {
  const side = $("side");
  if (!side) return;
  const here = location.pathname.replace(/\/+$/, "") || "/";
  const openCheck = here === "/" && new URLSearchParams(location.search).get("c");
  const icon = (d) => `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="${d}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const link = (item, cls = "", current = item[0] === here) =>
    `<a href="${item[0]}" title="${esc(item[1])}"${current ? ' aria-current="page"' : ""}${cls ? ` class="${cls}"` : ""}>${icon(item[3])}<span>${esc(item[1])}${item[2] ? `<small>${esc(item[2])}</small>` : ""}</span></a>`;
  // collapsed (icons only) or full: remembered in this browser
  let collapsed = false;
  try { collapsed = localStorage.getItem("gonogo.side.collapsed") === "1"; } catch (e) {}
  side.closest(".app")?.classList.toggle("side-collapsed", collapsed);
  side.innerHTML = `
    <div class="side-top">
      <a class="brand" href="/">
        <svg width="34" height="34" viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="20" fill="var(--brand)"/>
          <circle cx="20" cy="20" r="15.5" fill="none" stroke="var(--brand-ink)" stroke-opacity=".22" stroke-width="1.2"/>
          <g transform="rotate(40 20 20)"><path d="M20 6.5L25 20H15Z" fill="var(--brand-ink)"/><path d="M15 20H25L20 33.5Z" fill="var(--brand-ink)" fill-opacity=".38"/>
          <circle cx="20" cy="20" r="2.3" fill="var(--brand)"/></g></svg>
        <span class="brand-name">Go<b>No</b>Go</span>
      </a>
      <button class="collapse-btn" type="button" aria-label="${collapsed ? "Expand" : "Collapse"} the sidebar" title="${collapsed ? "Expand" : "Collapse"} the sidebar">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="15" rx="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M9.5 4.5v15" stroke="currentColor" stroke-width="1.7"/></svg>
      </button>
      <button class="menu-btn" type="button" aria-expanded="false" aria-controls="side-nav">Menu</button>
    </div>
    <nav id="side-nav" aria-label="Pages">
      <div class="group">Your shop</div>
      ${NAV.map(item => link(item)).join("")}
      <div class="side-spacer"></div>
      ${recentChecksHTML()}
      ${link(DISCOVERY, "primary", here === "/" && !openCheck)}
    </nav>
    <a class="side-foot" id="side-shop" href="/shop"${here === "/shop" ? ' aria-current="page"' : ""}>
      ${icon("M3 9l1.5-5h15L21 9M3 9h18M3 9a3 3 0 006 0 3 3 0 006 0 3 3 0 006 0M5 12v8h14v-8M10 20v-5h4v5")}
      <span><b id="side-shop-name"></b><small id="side-shop-line"></small></span>
      <span class="side-foot-go" aria-hidden="true">›</span>
    </a>`;
  side.querySelector(".collapse-btn").addEventListener("click", () => {
    const now = !side.closest(".app").classList.contains("side-collapsed");
    try { localStorage.setItem("gonogo.side.collapsed", now ? "1" : "0"); } catch (e) {}
    renderSidebar();
  });
  const btn = side.querySelector(".menu-btn");
  btn.addEventListener("click", () => { const open = side.classList.toggle("open"); btn.setAttribute("aria-expanded", open); });
  const local = loadOrg();
  setSidebarShop(local.shop_name, (local.profile || {}).tagline);
  // Pages that don't load the settings themselves (the shop data pages) still get the real name.
  if (!local.shop_name && !["/", "/business", "/shop"].includes(here)) fetchSettings();
}
// The shop card at the bottom of the sidebar: name + tagline, links to the Shop profile page.
function setSidebarShop(name, tagline) {
  if (!$("side-shop-name")) return;
  $("side-shop-name").textContent = name || "Your shop";
  $("side-shop-line").textContent = tagline || "Shop profile";
  $("side-shop").title = "Shop profile" + (name ? `: ${name}` : "");
}
renderSidebar();
