// The shop data pages (Products, Inventory, Sales, Returns, Customers, Suppliers): one renderer for all.
// The server sends the page as {title, intro, kpis, tables}; see backend/agents/pages.py.
const PAGE = location.pathname.replace(/^\/+|\/+$/g, "");
const PARAMS = new URLSearchParams(location.search);
const STATUS = {
  healthy: ["Healthy", "pass"], reorder: ["Reorder", "fail"], overstock: ["Overstock", "warn"], dead: ["Dead stock", "fail"],
  active: ["Active", "pass"], discontinued: ["Discontinued", "off"],
};
const FILTER_LABEL = {department: "Department", category: "Category", status: "Status", brand: "Brand",
                      channel: "Channel", city: "City", age_band: "Age band"};
const FILTER_ALL = {department: "All departments", category: "All categories", status: "All statuses", brand: "All brands",
                    channel: "All channels", city: "All cities", age_band: "All age bands"};
const NUMERIC = new Set(["inr", "num", "dec1", "pct", "days"]);
const PAGE_SIZES = [25, 50, 100];

function fmt(v, f) {
  if (v == null || v === "") return "-";
  switch (f) {
    case "inr": return inr(v);
    case "num": return num(v);
    case "dec1": return Number(v).toFixed(1);
    case "pct": return pctText(v);
    case "days": return num(v) + (Math.round(v) === 1 ? " day" : " days");
    case "date": return longDate(v);
    case "month": {   // "2026-10" or "2026-10 (to date)" -> "Oct 2026 (to date)"
      const d = new Date(String(v).slice(0, 7) + "-01T00:00:00");
      return d.toLocaleDateString("en-IN", {month: "short", year: "numeric"}) + String(v).slice(7);
    }
    case "yesno": return v ? "Yes" : "-";
    case "status": return (STATUS[v] || [v])[0];
    default: return String(v);
  }
}
function cell(v, f) {
  if (f === "status") {
    const [label, kind] = STATUS[v] || [v, "off"];
    return `<span class="pill ${kind}">${esc(label)}</span>`;
  }
  return esc(fmt(v, f));
}
function kpiHTML(k) {
  const value = k.format === "inr" ? (Math.abs(k.value) >= 1e7 ? inrShort(k.value) : inr(k.value)) : fmt(k.value, k.format);
  let note = esc(k.note || "");
  if (k.change != null) {
    const good = (k.change >= 0) === k.higher_is_better;
    note = `<span class="delta ${good ? "good" : "bad"}">${k.change >= 0 ? "▲" : "▼"} ${Math.abs(k.change * 100).toFixed(1)}%</span> ${note}`;
  }
  return `<div class="kpi"><span class="k">${esc(k.label)}</span><span class="v" title="${k.format === "inr" ? esc(inr(k.value)) : ""}">${esc(value)}</span><span class="s">${note}</span></div>`;
}

// Page buttons: first, last, and the pages around the current one, with … for the gaps.
function pagerHTML(page, pages, from, count, total, size) {
  const nums = [...new Set([1, page - 1, page, page + 1, pages])].filter(p => p >= 1 && p <= pages).sort((a, b) => a - b);
  let links = "", last = 0;
  nums.forEach(p => {
    if (p - last > 1) links += `<span class="gap" aria-hidden="true">…</span>`;
    links += `<button type="button" class="pg" data-page="${p}"${p === page ? ' aria-current="page"' : ""} aria-label="Page ${p}">${p}</button>`;
    last = p;
  });
  return `<span class="hint">Showing ${num(from + 1)}–${num(from + count)} of ${num(total)}</span>
    <span class="pages">
      <button type="button" class="pg" data-page="${page - 1}"${page === 1 ? " disabled" : ""}>‹ Prev</button>
      ${links}
      <button type="button" class="pg" data-page="${page + 1}"${page === pages ? " disabled" : ""}>Next ›</button>
    </span>
    <label class="hint size-pick">Rows per page <select class="size">${PAGE_SIZES.map(n => `<option${n === size ? " selected" : ""}>${n}</option>`).join("")}</select></label>`;
}

function mountTable(holder, t) {
  const state = {q: "", filters: {}, sort: t.sort || null, page: 1, size: PAGE_SIZES[0]};
  const search = t.search || [], filters = (t.filters || []).filter(k => t.rows.some(r => r[k] != null));
  // Links like /inventory?sku=W-LEG-001 or ?status=reorder open the page pre-filtered.
  const preset = PARAMS.get("q") || PARAMS.get("sku");
  if (preset && search.length) state.q = preset;
  filters.forEach(k => { if (PARAMS.get(k)) state.filters[k] = PARAMS.get(k); });

  const options = (k) => [...new Set(t.rows.map(r => r[k]).filter(v => v != null))].sort();
  holder.innerHTML = `
    <div class="section-head"><h2>${esc(t.title)}</h2><span class="hint count"></span></div>
    ${search.length || filters.length ? `<div class="toolbar">
      ${search.length ? `<input type="search" class="q" placeholder="Search" aria-label="Search ${esc(t.title)}" value="${esc(state.q)}">` : ""}
      ${filters.map(k => `<select data-k="${esc(k)}" aria-label="${esc(FILTER_LABEL[k] || k)}">
        <option value="">${esc(FILTER_ALL[k] || "All")}</option>
        ${options(k).map(v => `<option value="${esc(v)}"${state.filters[k] === String(v) ? " selected" : ""}>${esc(fmt(v, k === "status" ? "status" : "text"))}</option>`).join("")}
      </select>`).join("")}
    </div>` : ""}
    <div class="tbl-wrap"><table class="data"><thead><tr>${t.columns.map(c => `<th class="${NUMERIC.has(c.format) ? "n" : ""}" data-k="${esc(c.key)}">
      <button type="button" class="sort">${esc(c.label)}<span class="arrow" aria-hidden="true"></span></button></th>`).join("")}</tr></thead><tbody></tbody></table></div>
    <nav class="pager" aria-label="${esc(t.title)} pages"></nav>
    ${t.note ? `<p class="note">${esc(t.note)}</p>` : ""}`;

  const fmtOf = Object.fromEntries(t.columns.map(c => [c.key, c.format]));
  function draw() {
    const q = state.q.trim().toLowerCase();
    let rows = t.rows.filter(r =>
      (!q || search.some(k => String(r[k] ?? "").toLowerCase().includes(q))) &&
      Object.entries(state.filters).every(([k, v]) => !v || String(r[k]) === v));
    if (state.sort) {
      const [k, dir] = state.sort, f = fmtOf[k], sign = dir === "asc" ? 1 : -1;
      rows = [...rows].sort((a, b) => {
        const x = a[k], y = b[k];
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        return (NUMERIC.has(f) ? x - y : String(x).localeCompare(String(y))) * sign;
      });
    }
    const pages = Math.max(1, Math.ceil(rows.length / state.size));
    state.page = Math.min(Math.max(1, state.page), pages);
    const from = (state.page - 1) * state.size;
    const shown = rows.slice(from, from + state.size);
    holder.querySelector("tbody").innerHTML = shown.length ? shown.map(r => `<tr>${t.columns.map(c =>
      `<td class="${NUMERIC.has(c.format) ? "n" : ""}">${cell(r[c.key], c.format)}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${t.columns.length}" class="note">Nothing matches. Clear the search or filters.</td></tr>`;
    holder.querySelector(".count").textContent = rows.length === t.rows.length ? `${num(rows.length)} rows` : `${num(rows.length)} of ${num(t.rows.length)} rows`;
    holder.querySelector(".pager").innerHTML = rows.length > PAGE_SIZES[0] ? pagerHTML(state.page, pages, from, shown.length, rows.length, state.size) : "";
    holder.querySelectorAll("th").forEach(th => {
      const on = state.sort && state.sort[0] === th.dataset.k;
      th.setAttribute("aria-sort", on ? (state.sort[1] === "asc" ? "ascending" : "descending") : "none");
      th.querySelector(".arrow").textContent = on ? (state.sort[1] === "asc" ? " ▲" : " ▼") : "";
    });
  }
  // Searching, filtering or sorting starts again from page 1.
  holder.querySelector(".q")?.addEventListener("input", (e) => { state.q = e.target.value; state.page = 1; draw(); });
  holder.querySelectorAll(".toolbar select").forEach(s => s.addEventListener("change", () => { state.filters[s.dataset.k] = s.value; state.page = 1; draw(); }));
  holder.querySelectorAll("th .sort").forEach(b => b.addEventListener("click", () => {
    const k = b.parentElement.dataset.k;
    const first = NUMERIC.has(fmtOf[k]) ? "desc" : "asc";
    state.sort = state.sort && state.sort[0] === k ? [k, state.sort[1] === "asc" ? "desc" : "asc"] : [k, first];
    state.page = 1;
    draw();
  }));
  const pager = holder.querySelector(".pager");
  pager.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-page]");
    if (!b || b.disabled) return;
    state.page = +b.dataset.page;
    draw();
    // keep the table in view when its top has scrolled away
    if (holder.getBoundingClientRect().top < 0) holder.scrollIntoView({block: "start"});
    pager.querySelector(`button[data-page="${state.page}"][aria-current]`)?.focus();
  });
  pager.addEventListener("change", (e) => {
    if (e.target.matches(".size")) { state.size = +e.target.value; state.page = 1; draw(); }
  });
  draw();
}

// Each page's fixed heading, shown at once while the numbers load (same words as agents/pages.py).
const HEADS = {
  inventory: ["Inventory", "Stock for every active product. Sales speed is the last 8 weeks; cover = days the stock on hand lasts at that speed.", "Stock by product"],
  products: ["Products", "The whole catalogue with list prices and the last 12 months of sales.", "Catalogue"],
  sales: ["Sales", "The last 30 days compared with the 30 days before, sales by month, and the latest orders.", "By month"],
  returns: ["Returns", "What comes back, from where, and which products are sent back most. Last 12 months.", "By category"],
  customers: ["Customers", "Who buys from the shop. Activity is the last 12 months.", "By age band"],
  suppliers: ["Suppliers", "Who makes the products, how long they take, and how much of the shop depends on each.", "All suppliers"],
};
if (HEADS[PAGE]) {
  const [title, intro, first] = HEADS[PAGE];
  document.title = `GoNoGo ${title}`;
  $("title").textContent = title;
  $("intro").textContent = intro;
  const h = document.querySelector("#page .sk-h2");
  if (h) h.outerHTML = `<div class="section-head"><h2>${esc(first)}</h2></div>`;
}

fetch(`/api/pages/${encodeURIComponent(PAGE)}`).then(async r => {
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : `The server answered ${r.status}.`);
  return d;
}).then(d => {
  document.title = `GoNoGo ${d.title}`;
  $("title").textContent = d.title;
  $("intro").textContent = d.intro;
  $("page").innerHTML = `<div class="stats${d.kpis.length === 4 ? " four" : ""}">${d.kpis.map(kpiHTML).join("")}</div>` +
    d.tables.map((t, i) => `<div class="panel section" id="t${i}"></div>`).join("");
  d.tables.forEach((t, i) => mountTable($("t" + i), t));
}).catch(err => {
  $("title").textContent = PAGE.charAt(0).toUpperCase() + PAGE.slice(1);
  $("page").innerHTML = `<div class="error" role="alert"><strong>Couldn't load this page.</strong> ${esc(err.message)}</div>`;
});
