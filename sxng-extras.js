/*
 * Client side of the instant answers + personal site ranking
 * (plugins/smallapp_answers.py, plugins/smallapp_sites.py).
 * No dependencies, no network: everything here runs in the browser.
 */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const rnd = (n) => {
    // unbiased integer in [0, n) from the CSPRNG
    const a = new Uint32Array(1), lim = Math.floor(0x100000000 / n) * n;
    do crypto.getRandomValues(a); while (a[0] >= lim);
    return a[0] % n;
  };
  const card = (el) => el.closest(".ia-card");
  const pop = (el) => { el.classList.remove("ia-pop"); void el.offsetWidth; el.classList.add("ia-pop"); };
  const setValue = (c, text) => {
    let v = $(".ia-value", c);
    if (!v) { v = document.createElement("div"); v.className = "ia-value"; $(".ia-head", c).after(v); }
    v.textContent = text; pop(v);
  };

  // ---------------------------------------------------------------- toast
  let toastTimer;
  function toast(html, ms = 2200) {
    let t = $(".ia-toast");
    if (!t) { t = document.createElement("div"); t.className = "ia-toast"; t.setAttribute("role", "status"); document.body.append(t); }
    t.innerHTML = html; t.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), ms);
  }
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = Object.assign(document.createElement("textarea"), { value: text });
      document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    toast(`Copied <b>${esc(text.length > 40 ? text.slice(0, 40) + "…" : text)}</b>`);
  }

  // ---------------------------------------------------------------- generators
  const PW = { lo: "abcdefghijklmnopqrstuvwxyz", up: "ABCDEFGHIJKLMNOPQRSTUVWXYZ", d: "0123456789", s: "!@#$%^&*-_=+?" };
  function password(n, sym) {
    const all = PW.lo + PW.up + PW.d + (sym ? PW.s : "");
    for (;;) {
      let p = ""; for (let i = 0; i < n; i++) p += all[rnd(all.length)];
      if (/[a-z]/.test(p) && /[A-Z]/.test(p) && /\d/.test(p) && (!sym || n < 8 || /[!@#$%^&*\-_=+?]/.test(p))) return p;
    }
  }
  function uuid(ver) {
    const b = crypto.getRandomValues(new Uint8Array(16));
    if (ver === "v7") {
      let ms = Date.now();
      for (let i = 5; i >= 0; i--) { b[i] = ms & 0xff; ms = Math.floor(ms / 256); }
      b[6] = (b[6] & 0x0f) | 0x70;
    } else b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  function dieHTML(v, sides) {
    return sides === 6
      ? `<span class="ia-die d6" data-v="${v}">${"<i></i>".repeat(v)}</span>`
      : `<span class="ia-die dn" data-v="${v}"><b>${v}</b><small>d${sides}</small></span>`;
  }

  // ---------------------------------------------------------------- timers
  const clocks = new WeakMap();
  function fmtClock(ms, tenths) {
    const neg = ms < 0; ms = Math.abs(ms);
    const s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    const base = (h ? `${h}:${String(m).padStart(2, "0")}` : String(m).padStart(2, "0")) + ":" + String(ss).padStart(2, "0");
    return (neg ? "−" : "") + base + (tenths ? "." + Math.floor((ms % 1000) / 100) : "");
  }
  function beep() {
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.35, 0.7].forEach((t) => {
        const o = ac.createOscillator(), g = ac.createGain();
        o.frequency.value = 880; o.type = "sine"; o.connect(g); g.connect(ac.destination);
        g.gain.setValueAtTime(0.0001, ac.currentTime + t);
        g.gain.exponentialRampToValueAtTime(0.3, ac.currentTime + t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + t + 0.28);
        o.start(ac.currentTime + t); o.stop(ac.currentTime + t + 0.3);
      });
    } catch { /* no audio */ }
  }
  const baseTitle = document.title;
  function clockState(el) {
    let st = clocks.get(el);
    if (!st) {
      st = { mode: el.dataset.mode, total: +el.dataset.secs * 1000, left: +el.dataset.secs * 1000, elapsed: 0, running: false, t0: 0, raf: 0, done: false };
      clocks.set(el, st);
    }
    return st;
  }
  function renderClock(el) {
    const st = clockState(el), face = $(".ia-clock-face", el);
    if (st.mode === "timer") {
      const left = st.running ? st.left - (performance.now() - st.t0) : st.left;
      face.textContent = fmtClock(Math.max(0, Math.ceil(left / 1000) * 1000));
      const ring = $(".ia-ring .p", el);
      if (ring) ring.style.strokeDashoffset = String(339.3 * (1 - Math.max(0, left) / st.total));
      if (st.running) document.title = `⏲ ${face.textContent} · ${baseTitle}`;
      if (left <= 0 && st.running) {
        st.running = false; st.left = 0; st.done = true; el.classList.add("done"); beep();
        document.title = `⏰ Time's up! · ${baseTitle}`;
        const b = $('[data-ia="start"]', card(el)); if (b) b.textContent = "▶ Start";
        if ("Notification" in window && Notification.permission === "granted") new Notification("⏰ Time's up!");
        return;
      }
    } else {
      const el2 = st.running ? st.elapsed + (performance.now() - st.t0) : st.elapsed;
      face.textContent = fmtClock(el2, true);
    }
    if (st.running) st.raf = requestAnimationFrame(() => renderClock(el));
  }
  function clockAction(c, action, btn) {
    const el = $(".ia-clock", c), st = clockState(el);
    if (action === "start") {
      if (st.running) {
        // pause
        if (st.mode === "timer") st.left -= performance.now() - st.t0; else st.elapsed += performance.now() - st.t0;
        st.running = false; cancelAnimationFrame(st.raf); btn.textContent = "▶ Resume"; document.title = baseTitle;
      } else {
        if (st.mode === "timer" && st.left <= 0) { st.left = st.total; el.classList.remove("done"); }
        if ("Notification" in window && Notification.permission === "default" && st.mode === "timer") Notification.requestPermission();
        st.running = true; st.t0 = performance.now(); btn.textContent = "❚❚ Pause"; renderClock(el);
      }
    } else if (action === "reset") {
      cancelAnimationFrame(st.raf); st.running = false; st.left = st.total; st.elapsed = 0; el.classList.remove("done");
      document.title = baseTitle; const b = $('[data-ia="start"]', c); if (b) b.textContent = "▶ Start";
      const laps = $(".ia-laps", c); if (laps) laps.innerHTML = "";
      renderClock(el);
    } else if (action === "lap" && st.mode === "stopwatch") {
      const t = st.running ? st.elapsed + (performance.now() - st.t0) : st.elapsed;
      const li = document.createElement("li"); li.textContent = fmtClock(t, true); $(".ia-laps", c).prepend(li);
    } else if (action === "preset") {
      cancelAnimationFrame(st.raf);
      st.total = st.left = +btn.dataset.secs * 1000; st.running = false; el.classList.remove("done");
      const b = $('[data-ia="start"]', c); renderClock(el); clockAction(c, "start", b);
    }
  }

  // ---------------------------------------------------------------- live countdowns / unix clock
  function tick() {
    $$(".ia-countdown[data-target]").forEach((el) => {
      let ms = new Date(el.dataset.target) - Date.now();
      if (ms < 0) ms = 0;
      const d = Math.floor(ms / 864e5), h = Math.floor(ms / 36e5) % 24, m = Math.floor(ms / 6e4) % 60, s = Math.floor(ms / 1e3) % 60;
      el.innerHTML = [[d, "days"], [h, "hours"], [m, "min"], [s, "sec"]].map(([v, l]) => `<div><b>${v}</b><small>${l}</small></div>`).join("");
    });
    $$(".ia-worldclock[data-tz]").forEach((el) => {
      try {
        el.querySelector(".ia-live-time").textContent = new Intl.DateTimeFormat("en-GB", {
          timeZone: el.dataset.tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
        }).format(new Date());
      } catch { /* unknown zone in this browser */ }
    });
    $$('[data-live="unix"]').forEach((el) => {
      el.textContent = Math.floor(Date.now() / 1000);
      const dd = el.parentElement.querySelector(".ia-kv dd span");
      if (dd) dd.textContent = Date.now();
    });
  }

  // ---------------------------------------------------------------- morse audio
  function playMorse(code) {
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)(), u = 0.07;
      let t = ac.currentTime + 0.05;
      const o = ac.createOscillator(), g = ac.createGain();
      o.frequency.value = 650; o.connect(g); g.connect(ac.destination); g.gain.value = 0; o.start();
      for (const ch of code) {
        if (ch === "." || ch === "-") {
          const len = ch === "." ? u : 3 * u;
          g.gain.setValueAtTime(0.25, t); g.gain.setValueAtTime(0, t + len); t += len + u;
        } else if (ch === " ") t += 2 * u; else if (ch === "/") t += 4 * u;
      }
      o.stop(t + 0.1);
    } catch { /* no audio */ }
  }

  // ---------------------------------------------------------------- actions
  const RPS = ["🪨", "📄", "✂️"], RPSN = ["Rock", "Paper", "Scissors"];
  let rpsScore = [0, 0];

  document.addEventListener("click", (ev) => {
    const t = ev.target;

    const cp = t.closest("[data-copy], [data-copy-from]");
    if (cp && cp.closest(".ia-card")) {
      ev.preventDefault();
      const src = cp.dataset.copyFrom ? $(cp.dataset.copyFrom, card(cp)).textContent : cp.dataset.copy;
      copy(src); return;
    }

    const rps = t.closest("[data-rps]");
    if (rps) {
      const me = +rps.dataset.rps, cpu = rnd(3), c = card(rps);
      const res = (me - cpu + 3) % 3; // 0 draw, 1 win, 2 lose
      if (res === 1) rpsScore[0]++; else if (res === 2) rpsScore[1]++;
      const out = $(".ia-rps-out", c);
      out.innerHTML = `${RPS[me]} vs ${RPS[cpu]} — <b>${["Draw!", "You win! 🎉", "I win! 😈"][res]}</b> <span style="opacity:.6">(you ${rpsScore[0]} · me ${rpsScore[1]})</span>`;
      pop(out); return;
    }

    const b = t.closest("[data-ia]");
    if (!b || !card(b)) return;
    const c = card(b), a = b.dataset.ia, box = b.closest("[data-opts],[data-lo]") || b.parentElement;

    switch (a) {
      case "dice": {
        const d = $(".ia-dice", c), n = +d.dataset.n, sides = +d.dataset.sides, mod = +d.dataset.mod;
        const vals = Array.from({ length: n }, () => rnd(sides) + 1);
        d.innerHTML = vals.map((v) => dieHTML(v, sides)).join("");
        d.classList.remove("ia-rolling"); void d.offsetWidth; d.classList.add("ia-rolling");
        setValue(c, String(vals.reduce((x, y) => x + y, 0) + mod));
        const sub = $(".ia-sub", c);
        if (sub) sub.textContent = vals.join(" + ") + (mod ? ` ${mod > 0 ? "+" : "−"} ${Math.abs(mod)}` : "");
        break;
      }
      case "coin": {
        const coin = $(".ia-coin", c), heads = rnd(2) === 0, dk = coin.dataset.dk === "1";
        const cur = parseFloat(coin.dataset.rot || (coin.classList.contains("tails") ? 180 : 0));
        let next = cur + 1800 + (heads ? 0 : 180);
        next += ((heads ? 0 : 180) - (next % 360) + 360) % 360;
        coin.dataset.rot = next; coin.classList.remove("tails");
        coin.style.transform = `rotateY(${next}deg)`;
        const v = $(".ia-value", c); if (v) v.style.visibility = "hidden";
        setTimeout(() => { setValue(c, dk ? (heads ? "Krone" : "Plat") : (heads ? "Heads" : "Tails")); $(".ia-value", c).style.visibility = ""; }, 1000);
        break;
      }
      case "number": {
        const lo = +box.dataset.lo, hi = +box.dataset.hi;
        setValue(c, String(lo + rnd(hi - lo + 1)));
        break;
      }
      case "pick": {
        const opts = JSON.parse(box.dataset.opts), spans = $$(".ia-options span", c);
        const win = rnd(opts.length), steps = 12 + opts.length * 2;
        let i = 0;
        const spin = () => {
          spans.forEach((s, k) => s.classList.toggle("win", k === i % opts.length));
          if (i++ < steps) setTimeout(spin, 40 + i * 6); else { spans.forEach((s, k) => s.classList.toggle("win", k === win)); setValue(c, opts[win]); }
        };
        spin();
        break;
      }
      case "shuffle": {
        const opts = JSON.parse(box.dataset.opts);
        for (let i = opts.length - 1; i > 0; i--) { const j = rnd(i + 1); [opts[i], opts[j]] = [opts[j], opts[i]]; }
        const ol = $(".ia-shuffle", c); ol.innerHTML = opts.map((o) => `<li>${esc(o)}</li>`).join(""); pop(ol);
        break;
      }
      case "8ball": {
        const ball = $(".ia-8ball", c), opts = JSON.parse(box.dataset.opts);
        ball.classList.remove("shake"); void ball.offsetWidth; ball.classList.add("shake");
        const w = $(".ia-8ball-window span", c); w.style.opacity = 0;
        setTimeout(() => { w.textContent = opts[rnd(opts.length)]; w.style.opacity = 1; pop(w); }, 600);
        break;
      }
      case "yesno": {
        const cur = $(".ia-value", c).textContent, dk = cur === "Ja" || cur === "Nej", y = rnd(2) === 0;
        setValue(c, dk ? (y ? "Ja" : "Nej") : (y ? "Yes" : "No"));
        break;
      }
      case "password": {
        const n = +$(".ia-pw-len", c).value, sym = $(".ia-pw-sym", c).checked, out = $(".ia-pw-out", c);
        out.textContent = password(n, sym); pop(out);
        break;
      }
      case "uuid": { const out = $(".ia-uuid-out", c); out.textContent = uuid(b.dataset.ver); pop(out); break; }
      case "morse-play": playMorse(b.dataset.morse); break;
      case "start": case "reset": case "lap": case "preset": clockAction(c, a, b); break;
    }
  });

  document.addEventListener("input", (ev) => {
    if (ev.target.matches(".ia-pw-len")) {
      const c = card(ev.target);
      $("output", ev.target.parentElement).textContent = ev.target.value;
      $(".ia-pw-out", c).textContent = password(+ev.target.value, $(".ia-pw-sym", c).checked);
    } else if (ev.target.matches(".ia-pw-sym")) {
      const c = card(ev.target);
      $(".ia-pw-out", c).textContent = password(+$(".ia-pw-len", c).value, ev.target.checked);
    }
  });

  // ================================================================= site ranking
  const COOKIE = "sx_sites";
  const MODE_LABEL = { b: "Boosted", l: "Lowered", x: "Blocked" };
  function readSites() {
    const m = document.cookie.match(/(?:^|;\s*)sx_sites=([^;]*)/);
    const out = {};
    if (!m) return out;
    decodeURIComponent(m[1]).split("~").forEach((it) => {
      const i = it.lastIndexOf("!");
      if (i > 0) out[it.slice(0, i)] = it.slice(i + 1);
    });
    return out;
  }
  function writeSites(obj) {
    const v = Object.entries(obj).map(([d, m]) => `${d}!${m}`).join("~");
    const secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie = v
      ? `${COOKIE}=${v}; Path=/; Max-Age=${5 * 365 * 864e2}; SameSite=Lax${secure}`
      : `${COOKIE}=; Path=/; Max-Age=0; SameSite=Lax${secure}`;
  }
  const normHost = (h) => h.toLowerCase().replace(/^www\./, "");
  function ruleFor(host, rules) {
    let best = null;
    for (const [d, m] of Object.entries(rules)) {
      let ok;
      if (d.endsWith(".*")) ok = new RegExp(`(^|\\.)${d.slice(0, -2).replace(/\./g, "\\.")}(\\.[a-z0-9-]+){1,2}$`).test(host);
      else ok = host === d || host.endsWith("." + d);
      if (ok && (!best || d.length > best[0].length)) best = [d, m];
    }
    return best;
  }
  function setSite(dom, mode) {
    const s = readSites();
    if (mode) s[dom] = mode; else delete s[dom];
    writeSites(s);
    decorate();
    const verb = mode ? { b: "boosted ▲", l: "lowered ▼", x: "blocked ⊘" }[mode] : "reset";
    toast(`<b>${esc(dom)}</b> ${verb} — applies from your next search <a href="#" data-sx-reload>Refresh now</a>`, 4500);
  }

  function closeMenus() {
    $$(".sx-rank-menu").forEach((m) => m.remove());
    $$(".sx-rank-btn[aria-expanded=true]").forEach((b) => b.setAttribute("aria-expanded", "false"));
  }
  function openMenu(btn) {
    const art = btn.closest("article"), host = art.dataset.sxHost;
    const parts = host.split("."), base = parts.length > 2 ? parts.slice(-2).join(".") : host;
    const rules = readSites(), cur = ruleFor(host, rules);
    const doms = [...new Set([host, base])];
    let html = "";
    doms.forEach((d, i) => {
      const on = (m) => (cur && cur[0] === d && cur[1] === m ? "on" : "");
      if (i) html += "<hr>";
      html += `<div class="h">${esc(d)}${d !== host ? " and all subdomains" : ""}</div>
        <button data-sx="${esc(d)}" data-m="b" class="${on("b")}">▲ Boost — rank higher</button>
        <button data-sx="${esc(d)}" data-m="l" class="${on("l")}">▼ Lower — push down</button>
        <button data-sx="${esc(d)}" data-m="x" class="${on("x")}">⊘ Block — never show</button>`;
    });
    if (cur) html += `<hr><button data-sx="${esc(cur[0])}" data-m="">↺ Reset ${esc(cur[0])}</button>`;
    html += `<hr><a href="./search?q=sites">⭐ Manage all sites…</a>`;
    const menu = document.createElement("div");
    menu.className = "sx-rank-menu"; menu.setAttribute("role", "menu"); menu.innerHTML = html;
    art.append(menu); btn.setAttribute("aria-expanded", "true");
    menu.style.top = btn.getBoundingClientRect().bottom - art.getBoundingClientRect().top + 4 + "px";
  }

  function decorate() {
    const rules = readSites();
    $$("#urls article.result").forEach((art) => {
      const a = art.querySelector("a.url_header, h3 a, a[href]");
      if (!a) return;
      let host;
      try { host = normHost(new URL(a.href).hostname); } catch { return; }
      art.dataset.sxHost = host;
      if (!art.querySelector(".sx-rank-btn")) {
        const b = document.createElement("button");
        b.className = "sx-rank-btn"; b.type = "button"; b.title = "Personalize this site"; b.textContent = "⋯";
        b.setAttribute("aria-haspopup", "menu"); b.setAttribute("aria-expanded", "false");
        // sits in the result's bottom row (engines · cached); float top-right if a template has none
        const row = art.querySelector(".engines");
        if (row) row.append(b); else { b.classList.add("float"); art.append(b); }
      }
      const r = ruleFor(host, rules);
      art.classList.remove("sx-b", "sx-l", "sx-x");
      if (r) art.classList.add("sx-" + r[1]);
    });
  }

  document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (t.closest("[data-sx-reload]")) { ev.preventDefault(); location.reload(); return; }
    const btn = t.closest(".sx-rank-btn");
    if (btn) {
      ev.preventDefault(); ev.stopPropagation();
      const open = btn.getAttribute("aria-expanded") === "true";
      closeMenus(); if (!open) openMenu(btn); return;
    }
    const item = t.closest(".sx-rank-menu [data-sx]");
    if (item) { ev.preventDefault(); setSite(item.dataset.sx, item.dataset.m); closeMenus(); return; }
    if (!t.closest(".sx-rank-menu")) closeMenus();

    // "sites" management card
    const seg = t.closest("[data-site-set]");
    if (seg) {
      const tr = seg.closest("tr"), dom = tr.dataset.dom, m = seg.dataset.siteSet;
      const s = readSites();
      if (m) s[dom] = m; else if (tr.querySelector("small")) s[dom] = "n"; else delete s[dom];
      writeSites(s);
      if (!m) tr.remove();
      else {
        $$("button", seg.parentElement).forEach((x) => x.classList.toggle("on", x === seg));
        const badge = tr.querySelector(".ia-mode");
        badge.className = "ia-mode m-" + m; badge.textContent = { b: "boost", l: "lower", x: "block" }[m];
      }
      toast(`Saved — <b>${esc(dom)}</b>`);
    }
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeMenus(); });
  document.addEventListener("submit", (ev) => {
    const f = ev.target.closest(".ia-site-add");
    if (!f) return;
    ev.preventDefault();
    let d = f.dom.value.trim().toLowerCase();
    try { if (/^[a-z]+:\/\//.test(d)) d = new URL(d).hostname; } catch { /* keep */ }
    d = d.replace(/^www\./, "").replace(/\/.*$/, "");
    if (!/^(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)*(\.\*)?$/.test(d)) { toast("That doesn't look like a domain"); return; }
    const s = readSites(); s[d] = f.mode.value; writeSites(s);
    location.reload();
  });

  // ================================================================= boot
  function boot() {
    decorate();
    tick(); setInterval(tick, 1000);
    const urls = $("#urls");
    if (urls) new MutationObserver(() => decorate()).observe(urls, { childList: true, subtree: false });
    // the landing page: rotate a few "try …" hints through the search box placeholder
    const q = $("#q");
    if (q && !q.value && document.body.classList.contains("index_endpoint")) {
      const hints = ["roll 2d6", "weather aarhus", "timer 10 min", "days until christmas", "#ff7a59", "uge 42", "password 24", "flip a coin", "192.168.8.0/24", "help"];
      q.placeholder = "Try “" + hints[rnd(hints.length)] + "”";
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
