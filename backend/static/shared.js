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
const VERDICT_LABEL = {go: "Go", go_with_conditions: "Conditions", no_go: "No-go"};
function loadChecks() {
  try { return JSON.parse(localStorage.getItem("gonogo.checks.v1") || "[]"); } catch (e) { return []; }
}
const TRASH = `<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
function deleteBtn(c) {
  return `<button type="button" class="del-check" data-id="${esc(c.id)}" title="Delete this check" aria-label="Delete ${esc(c.title)}">${TRASH}</button>`;
}
function checkLink(c, open) {
  return `<div class="recent-item"><a class="recent" href="/?c=${encodeURIComponent(c.id)}"${c.id === open ? ' aria-current="page"' : ""} title="${esc(c.title)}">
    <span class="vdot ${esc(c.verdict)}" aria-hidden="true"></span><span>${esc(c.title)}</span></a>${deleteBtn(c)}</div>`;
}
// Delete a saved check (asks first). Deleting the one that is open starts a new check.
function deleteCheck(id) {
  const list = loadChecks(), c = list.find(x => x.id === id);
  if (!c || !confirm(`Delete "${c.title}"? This can't be undone.`)) return;
  try { localStorage.setItem("gonogo.checks.v1", JSON.stringify(list.filter(x => x.id !== id))); } catch (e) { return; }
  if (new URLSearchParams(location.search).get("c") === id) { location.href = "/"; return; }
  renderSidebar();
  if ($("checks-modal")?.open) drawChecks();
}
document.addEventListener("click", (e) => {
  const b = e.target.closest(".del-check");
  if (b) { e.preventDefault(); e.stopPropagation(); deleteCheck(b.dataset.id); }
});
// Recent checks in the sidebar: the latest 3; "View all" and search open the list of every saved check.
function recentChecksHTML() {
  const list = loadChecks();
  const open = new URLSearchParams(location.search).get("c");
  const head = `<div class="group group-row"><span>Recent checks</span><span class="group-actions">
      <button type="button" class="icon-btn" onclick="openChecks(true)" title="Search your checks" aria-label="Search your checks">
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>
      <a class="new-check" href="/" title="Start a new check">+ New</a></span></div>`;
  if (!list.length) return head + `<p class="recent-empty">Your checks will appear here.</p>`;
  return head + `<div class="recent-list">${list.slice(0, 3).map(c => checkLink(c, open)).join("")}</div>` +
    (list.length > 3 ? `<button type="button" class="view-all" onclick="openChecks(false)">View all (${list.length})</button>` : "");
}

// The list of every saved check, with search and Go / Conditions / No-go filters (a dialog, on any page).
function openChecks(focusSearch) {
  let dlg = $("checks-modal");
  if (!dlg) {
    document.body.insertAdjacentHTML("beforeend", `<dialog class="modal" id="checks-modal" aria-labelledby="checks-title">
      <div class="modal-card">
        <div class="modal-head"><h2 id="checks-title">Your checks</h2><button type="button" class="modal-x" aria-label="Close" onclick="$('checks-modal').close()">×</button></div>
        <input type="search" id="checks-q" placeholder="Search by product name" aria-label="Search your checks">
        <div class="seg checks-filter" role="radiogroup" aria-label="Show">
          ${[["all", "All"], ["go", "Go"], ["go_with_conditions", "Conditions"], ["no_go", "No-go"]].map(([v, t], i) =>
            `<label><input type="radio" name="checks-f" value="${v}"${i ? "" : " checked"}><span>${t} <b class="cnt" data-v="${v}"></b></span></label>`).join("")}
        </div>
        <div class="checks-list" id="checks-list"></div>
      </div></dialog>`);
    dlg = $("checks-modal");
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
    $("checks-q").addEventListener("input", drawChecks);
    dlg.querySelectorAll("input[name=checks-f]").forEach(r => r.addEventListener("change", drawChecks));
  }
  $("checks-q").value = "";
  dlg.querySelector("input[name=checks-f][value=all]").checked = true;
  drawChecks();
  dlg.showModal();
  if (focusSearch) $("checks-q").focus();
}
function drawChecks() {
  const all = loadChecks();
  const q = $("checks-q").value.trim().toLowerCase();
  const f = document.querySelector("input[name=checks-f]:checked").value;
  const open = new URLSearchParams(location.search).get("c");
  document.querySelectorAll("#checks-modal .cnt").forEach(el => {
    el.textContent = el.dataset.v === "all" ? all.length : all.filter(c => c.verdict === el.dataset.v).length;
  });
  const rows = all.filter(c => (f === "all" || c.verdict === f) && (!q || (c.title || "").toLowerCase().includes(q)));
  const when = (t) => t ? new Date(t).toLocaleDateString("en-IN", {day: "numeric", month: "short"}) : "";
  $("checks-list").innerHTML = rows.length ? rows.map(c => `<div class="check-item"><a class="check-row" href="/?c=${encodeURIComponent(c.id)}"${c.id === open ? ' aria-current="page"' : ""}>
      <span class="vdot ${esc(c.verdict)}" aria-hidden="true"></span>
      <span class="check-name">${esc(c.title)}</span>
      <span class="check-verdict v-${esc(c.verdict)}">${esc(VERDICT_LABEL[c.verdict] || c.verdict)}</span>
      <span class="hint">${esc(when(c.updated))}</span></a>${deleteBtn(c)}</div>`).join("")
    : `<p class="note">${all.length ? "No checks match. Clear the search or pick another filter." : "Your checks will appear here."}</p>`;
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
      <div class="side-scroll">
        <div class="group">Your shop</div>
        ${NAV.map(item => link(item)).join("")}
        <div class="side-spacer"></div>
        ${recentChecksHTML()}
      </div>
      <a href="/" class="primary discover" title="Discovery: decide on a new product"${here === "/" && !openCheck ? ' aria-current="page"' : ""}>
        <svg class="disc-ico" viewBox="0 0 40 40" width="30" height="30" aria-hidden="true">
          <circle cx="20" cy="20" r="18.5" fill="none" stroke="currentColor" stroke-opacity=".35" stroke-width="2"/>
          <g class="disc-needle"><path d="M20 6.5L25 20H15Z" fill="currentColor"/><path d="M15 20H25L20 33.5Z" fill="currentColor" fill-opacity=".4"/></g>
          <circle cx="20" cy="20" r="2.4" fill="var(--brand)"/>
        </svg>
        <span>Discovery<small>Decide on a new product</small></span>
        <b class="disc-go" aria-hidden="true">→</b>
      </a>
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
