// Shared by both pages: the shop's numbers and rules, saved in this browser.
const RULE_GROUPS = [
  ["Your shop", [
    ["avg_units_per_product", "Units a typical product sells per month", 30, "Used to turn comparable sales speed into your expected sales."],
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
    ["min_velocity", "Minimum sales speed vs store average", 0.7, "Hard rule: comparables must sell at least this fast (1.0 = average)."],
    ["price_band_pct", "Comparable price band (± %)", 30, "Which products count as comparable, by price."],
  ]],
];
const RULES = RULE_GROUPS.flatMap(([, rules]) => rules);
const STORE_KEY = "gonogo.organisation.v1";

function loadOrg() {
  const defaults = Object.fromEntries(RULES.map(([k, , v]) => [k, v]));
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch (e) { saved = {}; }
  return {shop_name: saved.shop_name || "", rules: {...defaults, ...(saved.rules || {})}};
}
function saveOrg(org) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(org)); return true; } catch (e) { return false; }
}
function resetOrg() {
  try { localStorage.removeItem(STORE_KEY); } catch (e) {}
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const inr = (n) => n == null ? "-" : "₹" + Math.round(n).toLocaleString("en-IN");
const num = (n) => n == null ? "-" : Math.round(n).toLocaleString("en-IN");
const $ = (id) => document.getElementById(id);
