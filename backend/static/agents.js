// The agent crew on Discovery: who each agent is, what they say while they work, and the live chat answer
// that fills in, one line per agent, as the server streams each agent's start / done / failed / skipped event.
// The quips are fixed text: the characters never make up numbers. Every result line comes from the server.
const PERSONAS = {
  product: {
    name: "Iris", role: "Product agent", title: "The Spotter", job: "Looks at your product",
    icon: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z",
    quips: ["Squinting at your photo…", "Checking the fabric, the cut, the vibe…", "Matching it to your shelves…", "Making sure it's something you actually sell…"],
    wait: "Ready when you are.", done: "Got it.",
  },
  market: {
    name: "Scout", role: "Market agent", title: "The Bargain Hunter", job: "Checks prices online",
    icon: "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3",
    quips: ["Scouring Myntra, Amazon and Ajio…", "Haggling with the internet…", "Counting competitors so you don't have to…", "Reading price tags across India…", "Still searching. The internet is big…"],
    wait: "Waiting for Iris…", done: "Found them.",
  },
  demand: {
    name: "Ledger", role: "Demand agent", title: "The Number Cruncher", job: "Checks how similar products sell in your shop",
    icon: "M4 20V11M10 20V5M16 20v-6M2 20h20",
    quips: ["Looking through two years of your sales…", "Finding products like this one…", "Checking if they sell more or less lately…"],
    wait: "Waiting for Iris…", done: "Checked.",
  },
  fit: {
    name: "Echo", role: "Fit agent", title: "The Matchmaker", job: "Finds out who buys it",
    icon: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM22 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8",
    quips: ["Peeking into shopping baskets…", "Finding who buys this kind of thing…", "Checking channels and cities…"],
    wait: "Waiting for Iris…", done: "Found them.",
  },
  profit: {
    name: "Penny", role: "Profit agent", title: "The Accountant", job: "Works out what you'd earn",
    icon: "M6 4h12M6 9h12M6 4h3a5 5 0 010 10H6l8 6",
    quips: ["Counting every rupee…", "Taking off fees, shipping and returns…", "Working out your first order…"],
    wait: "Waiting for Ledger…", done: "Worked it out.",
  },
  verdict: {
    name: "Vera", role: "Verdict agent", title: "The Judge", job: "Checks your rules and gives the answer",
    icon: "M12 3v18M5 7h14M5 7l-3 7a3 3 0 006 0zM19 7l-3 7a3 3 0 006 0zM8 21h8",
    quips: ["Weighing the evidence…", "Checking it against your rules…", "No rule gets bent. Not even a little…", "Writing it up in plain words…"],
    wait: "Waiting for the whole crew…", done: "",
  },
};
const AGENT_ORDER = ["product", "market", "demand", "fit", "profit", "verdict"];
const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;

function avatarHTML(key) {
  const p = PERSONAS[key];
  return `<span class="avatar a-${key}" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20"><path d="${p.icon}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg></span>`;
}

// One answer in the chat while the team works: a line per finished agent, and a "who's working" line.
class LiveAnswer {
  constructor(container, onChange) {
    this.el = container;
    this.onChange = onChange || (() => {});
    this.working = new Map();       // agent -> start time
    this.t0 = Date.now();
    this.quip = 0;
    this.skippedShown = false;
    container.innerHTML = `<div class="steps"></div><div class="typing">${this.typingHTML()}</div>`;
    this.timer = setInterval(() => this.tick(), 2400);
  }
  typingHTML() {
    const keys = [...this.working.keys()];
    if (!keys.length) return `<span class="dots" aria-hidden="true"><i></i><i></i><i></i></span><span>Getting the team ready…</span>`;
    const names = keys.map(k => PERSONAS[k].name);
    const who = names.length === 1 ? names[0] : names.slice(0, -1).join(", ") + " and " + names.at(-1);
    const p = PERSONAS[keys[0]];
    return `${avatarHTML(keys[0])}<span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span><b>${esc(who)}</b> ${names.length === 1 ? "is" : "are"} working · <em>${esc(p.quips[this.quip % p.quips.length])}</em></span>`;
  }
  tick() { this.quip++; this.renderTyping(); }
  renderTyping() { const t = this.el.querySelector(".typing"); if (t) t.innerHTML = this.typingHTML(); this.onChange(); }
  step(key, html, kind = "") {
    const p = PERSONAS[key];
    this.el.querySelector(".steps").insertAdjacentHTML("beforeend",
      `<div class="step ${kind}">${avatarHTML(key)}<p><b>${esc(p.name)}</b> ${html}</p></div>`);
  }
  event(ev) {
    const key = ev.agent;
    if (!PERSONAS[key]) return;
    if (ev.type === "start") {
      this.working.set(key, Date.now());
    } else {
      this.working.delete(key);
      if (ev.type === "done" && key !== "verdict") this.step(key, esc(ev.summary || "Done."));
      else if (ev.type === "failed") this.step(key, "couldn't finish this time; the others carried on.", "bad");
      else if (ev.type === "skipped" && !this.skippedShown) {
        this.skippedShown = true;
        this.el.querySelector(".steps").insertAdjacentHTML("beforeend",
          `<div class="step quiet"><p>The rest of the team wasn't needed: this isn't something your shop sells.</p></div>`);
      }
    }
    this.renderTyping();
  }
  // Fold the steps into one line ("Checked by 6 agents in 21s") that opens to show them.
  finish(data) {
    clearInterval(this.timer);
    this.el.querySelector(".typing")?.remove();
    const steps = this.el.querySelector(".steps");
    const n = Object.values((data && data.agents) || {}).filter(a => a.status === "done").length;
    const secs = data && data.timing_ms != null ? (data.timing_ms / 1000).toFixed(0) : ((Date.now() - this.t0) / 1000).toFixed(0);
    const fold = document.createElement("details");
    fold.className = "steps-fold";
    fold.innerHTML = `<summary><span class="mini-team">${AGENT_ORDER.map(avatarHTML).join("")}</span>
      Checked by ${n} AI agents in ${secs}s</summary>`;
    fold.appendChild(steps);
    this.el.prepend(fold);
  }
  stop() { clearInterval(this.timer); this.el.querySelector(".typing")?.remove(); }
}

// The folded "Checked by N agents" line for an answer opened from Recent checks (no live events then).
function savedStepsHTML(data) {
  const agents = (data && data.agents) || {};
  let lines = "", skipped = false;
  AGENT_ORDER.forEach(k => {
    const a = agents[k], p = PERSONAS[k];
    if (!a || k === "verdict") return;
    if (a.status === "done") lines += `<div class="step">${avatarHTML(k)}<p><b>${esc(p.name)}</b> ${esc(a.summary || "Done.")}</p></div>`;
    else if (a.status === "failed") lines += `<div class="step bad">${avatarHTML(k)}<p><b>${esc(p.name)}</b> couldn't finish this time; the others carried on.</p></div>`;
    else if (a.status === "skipped" && !skipped) {
      skipped = true;
      lines += `<div class="step quiet"><p>The rest of the team wasn't needed: this isn't something your shop sells.</p></div>`;
    }
  });
  const n = Object.values(agents).filter(a => a.status === "done").length;
  const secs = data && data.timing_ms != null ? (data.timing_ms / 1000).toFixed(0) : "";
  return `<details class="steps-fold"><summary><span class="mini-team">${AGENT_ORDER.map(avatarHTML).join("")}</span>
    Checked by ${n} AI agents${secs ? ` in ${secs}s` : ""}</summary><div class="steps">${lines}</div></details>`;
}

// GoNoGo, the buying buddy who talks to you on Discovery (fixed wording; every number in it comes from code).
function gogoHTML(size = 36) {
  // GoNoGo's mark: a compass. A solid circle (steady, trusted) with one bold needle pointing up and
  // forward (a clear direction). While the team works it "thinks": the needle swings, its two halves swap,
  // meet in the middle and become two blinking eyes, then turn back into the needle (see app.css).
  return `<span class="gogo" style="--s:${size}px" aria-hidden="true"><svg viewBox="0 0 40 40" width="${size}" height="${size}">
    <circle cx="20" cy="20" r="20" fill="var(--brand)"/>
    <circle cx="20" cy="20" r="15.5" fill="none" stroke="var(--brand-ink)" stroke-opacity=".22" stroke-width="1.2"/>
    <g class="gogo-needle">
      <path class="n-front" d="M20 6.5L25 20H15Z" fill="var(--brand-ink)"/>
      <path class="n-back" d="M15 20H25L20 33.5Z" fill="var(--brand-ink)" fill-opacity=".38"/>
      <circle class="n-pivot" cx="20" cy="20" r="2.3" fill="var(--brand)"/>
    </g>
    <g class="gogo-eyes">
      <ellipse class="eye" cx="15.2" cy="19.5" rx="2.4" ry="3.3" fill="var(--brand-ink)"/>
      <ellipse class="eye" cx="24.8" cy="19.5" rx="2.4" ry="3.3" fill="var(--brand-ink)"/>
    </g>
  </svg></span>`;
}
function gogoSay(html, cls = "") {
  return `<div class="gogo-say ${cls}">${gogoHTML(30)}<div class="gogo-bubble">${html}</div></div>`;
}
