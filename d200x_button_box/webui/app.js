// D200x Button Box — web UI (organised vanilla, no build step).
// Phase 1 of the frontend overhaul: tokens + hero deck + docked editor +
// sim/box registers + autosave-by-default. Dialogs still <dialog> (phase 3).

const KEY_ROWS = [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11, 12, 13]];
const AUX_L = 15, AUX_R = 16, STATUS = 13, KNOBS = [17, 18, 19];
const ACTIONS = ["none", "gamepad", "key", "command", "profile", "page"];
const ACTION_HINT = {
  gamepad: "virtual joystick button the game binds",
  key: "keystroke (ydotool/xdotool)",
  command: "shell command on the daemon host",
  profile: "switch profile — or auto / next / prev / home",
  page: "switch page in this profile",
};
const STYLE_KEYS = ["mode", "shape", "fill", "border", "fg", "font"];
const NAV_BASE = { mode: "ring", shape: "round", fill: "#0d0f13", border: "#7d8794", fg: "#aeb6c2", font: "sans" };
const GAME_BASE = { mode: "solid", shape: "circle", fill: "#2a3140", border: "#4a9eff", fg: "#ffffff", font: "sans" };

const S = {
  name: null, profile: null, page: 0, sel: null, listening: false,
  profiles: [], settings: null, es: null, dirty: false, saveT: null, bindGame: null,
};
let GAMES = {}, GAME_CONTROLS = {};
let GLYPHS = { telltales: [], material: {}, composed: [] };
let COMPOSED_NAMES = new Set();
let TELLTALE_SET = new Set();
let ICONV = 0;                       // bumped after an icon edit to bust cached previews
const bumpIcons = () => { ICONV++; ICON_CACHE.clear(); };

const api = (p, o = {}) => fetch("api/" + p, o).then(r => {
  if (!r.ok) return r.text().then(t => Promise.reject(t || r.status));
  const c = r.headers.get("content-type") || "";
  return c.includes("json") ? r.json() : r;
});
const $ = s => document.querySelector(s);
const el = (t, p = {}, k = []) => {
  const e = document.createElement(t);
  for (const [key, val] of Object.entries(p)) {
    if (key === "class") e.className = val;
    else if (key === "html") e.innerHTML = val;
    else e[key] = val;
  }
  for (const c of [].concat(k)) e.append(c);
  return e;
};

// ---- model ---------------------------------------------------------
const pages = () => S.profile.pages;
const curPage = () => pages()[S.page] || pages()[0];
const keyB = i => curPage().keys[i] || (curPage().keys[i] = {});
const knobB = (i, s) => { const k = curPage().knobs[i] || (curPage().knobs[i] = {}); return k[s] || (k[s] = {}); };
const actOf = b => ACTIONS.find(a => a !== "none" && a in b) || "none";
function setAct(b, act, val) {
  for (const a of ACTIONS) if (a !== "none") delete b[a];
  if (act === "gamepad") b.gamepad = Number(val) || 1;
  else if (act !== "none") b[act] = val ?? "";
}
const intKeys = o => Object.fromEntries(Object.entries(o || {}).map(([k, v]) => [Number(k), v || {}]));
function normalize(name, raw) {
  const mk = p => ({ name: p.name || "", style: p.style || {}, keys: intKeys(p.keys), knobs: intKeys(p.knobs) });
  const pg = raw.pages ? raw.pages.map(mk) : [mk(raw)];
  return { name, pages: pg.length ? pg : [mk({})] };
}
function serialize() {
  const p = S.profile;
  const dump = g => ({
    ...(g.name ? { name: g.name } : {}),
    ...(g.style && Object.keys(g.style).length ? { style: g.style } : {}),
    keys: g.keys, knobs: g.knobs,
  });
  return (p.pages.length === 1 && !p.pages[0].name && !Object.keys(p.pages[0].style || {}).length)
    ? dump(p.pages[0]) : { pages: p.pages.map(dump) };
}

function isNav(b) { return b.role === "nav" || "page" in b || "profile" in b; }
// sim = a car input (gamepad, or a still-empty key); box = nav / util / macro
function registerOf(b) {
  if (isNav(b)) return "box";
  if ("command" in b || "key" in b) return "box";
  return "sim";
}

// ---- load / save --------------------------------------------------
async function boot() {
  const st = await api("state"); setConn(true); setDeck(st.device.connected);
  const pl = await api("profiles"); S.profiles = pl.profiles; S.name = pl.active;
  S.settings = await api("settings");
  GAMES = await api("games").catch(() => ({}));
  GLYPHS = await api("glyphs").catch(() => GLYPHS);
  COMPOSED_NAMES = new Set(GLYPHS.composed || []);
  TELLTALE_SET = new Set(GLYPHS.telltales || GLYPHS.bases || []);
  S.bindGame = Object.entries(GAMES).find(([, g]) => g.can_write && g.path)?.[0] || null;
  await loadProfile(S.name);
  connectSSE();
}
async function loadProfile(name) {
  S.name = name; S.page = 0; S.sel = null; S.dirty = false;
  S.profile = normalize(name, await api("profiles/" + name));
  render();
}
function touched() { S.dirty = true; renderStatus(); scheduleSave(); }
function scheduleSave() { clearTimeout(S.saveT); S.saveT = setTimeout(save, 800); }
async function save() {
  clearTimeout(S.saveT);
  if (!S.dirty) return;
  renderStatus("saving");
  try {
    await api("profiles/" + S.name, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(serialize()),
    });
    S.dirty = false; renderStatus();
  } catch (e) { renderStatus("error"); }
}

// ---- connection / SSE -------------------------------------------
function setConn(on) {
  $("#dot").classList.toggle("on", on);
  $("#dot").title = on ? "daemon connected" : "daemon offline";
}
function setDeck(on) {
  let w = $("#deckwarn");
  if (!on && !w) {
    w = el("span", { id: "deckwarn", class: "deckwarn", textContent: "⚠ deck disconnected" });
    $("#status").before(w);
  } else if (on && w) { w.remove(); }
}
function connectSSE() {
  S.es?.close();
  S.es = new EventSource("api/events");
  S.es.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === "state") { setConn(true); setDeck(m.device.connected); }
    if (m.type === "device") setDeck(m.connected);
    if (m.type === "input") onInput(m);
    if (m.type === "profile" && m.name !== S.name && !S.dirty) { S.name = m.name; syncProfileSel(); loadProfile(m.name); }
  };
  S.es.onerror = () => setConn(false);
}
function onInput(m) {
  const c = document.querySelector(`.cell[data-id="${m.index}"]`);
  if (c) { c.classList.add("hit"); setTimeout(() => c.classList.remove("hit"), 450); }
  if (S.listening && m.action !== "release") {
    S.listening = false;
    $("#listenBtn").classList.remove("on"); $("#listenBtn").textContent = "Listen";
    selectControl(m.kind, m.index);
  }
}

// ---- render orchestration --------------------------------------
function render() { syncProfileSel(); renderTabs(); renderDeck(); renderEditor(); renderStatus(); }
function renderStatus(kind) {
  const s = $("#status");
  s.className = "statuspill";
  if (kind === "saving") { s.classList.add("saving"); s.textContent = "saving…"; return; }
  if (kind === "error") { s.classList.add("error"); s.textContent = "save failed"; return; }
  if (S.dirty) { s.textContent = "editing…"; return; }
  s.classList.add("saved"); s.textContent = "saved";
}
function syncProfileSel() {
  const ps = $("#profileSel"); ps.innerHTML = "";
  S.profiles.forEach(n => ps.append(el("option", { value: n, textContent: n, selected: n === S.name })));
}
function renderTabs() {
  const tb = $("#tabs"); tb.innerHTML = "";
  pages().forEach((pg, i) => {
    const b = el("button", { textContent: pg.name || ("page " + (i + 1)) });
    b.classList.toggle("on", i === S.page);
    b.onclick = () => {
      S.page = i; S.sel = null; render();
      api("page", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ page: i }) });
    };
    b.ondblclick = () => { const n = prompt("Page name:", pg.name); if (n !== null) { pg.name = n || ""; render(); touched(); } };
    tb.append(b);
  });
}

// ---- deck ------------------------------------------------------
const ICON_CACHE = new Map();        // url -> <img>, so an unrelated re-render doesn't reload icons
function iconImg(url) {
  let im = ICON_CACHE.get(url);
  if (!im) { im = el("img", { src: url, alt: "" }); ICON_CACHE.set(url, im); return im; }
  return im.isConnected ? im.cloneNode() : im;  // same icon on two keys -> clone, no reload
}
function labelFor(id) {
  return id === STATUS ? "status" : id === AUX_L ? "aux ◀" : id === AUX_R ? "aux ▶" : "key " + id;
}
function iconURL(path) {
  const n = (path || "").split("/").pop();
  return /^[0-9a-f]{16}\.png$/.test(n) ? "api/icons/" + n : "";
}
function shortVal(b) {
  const a = actOf(b);
  if (a === "none") return "";
  if (a === "gamepad") return "btn " + b.gamepad + (b.momentary ? " ·pulse" : "");
  return a + ": " + (b[a] ?? "");
}
function mergedStyle(b) {
  const base = registerOf(b) === "box"
    ? NAV_BASE
    : Object.assign({}, GAME_BASE, S.settings?.icon?.game, curPage().style);
  return Object.assign({}, base, b.icon_style || {});
}
function previewURL(b) {
  if (iconURL(b.icon)) return iconURL(b.icon);
  if (b.icon) return "";
  const q = new URLSearchParams();
  // explicit wins: a chosen glyph, else chosen letters, else derive one.
  // a picked or action-implied glyph carries the label as a caption under it.
  if (b.glyph) { q.set("glyph", b.glyph); if (b.label) q.set("caption", b.label); }
  else if (b.icon_text) q.set("text", b.icon_text);
  else {
    const g = derivedGlyph(b);
    if (g) { q.set("glyph", g); if (b.label) q.set("caption", b.label); }
    else if (b.label) q.set("label", b.label);
    else return "";
  }
  const s = mergedStyle(b);
  STYLE_KEYS.forEach(k => { if (s[k]) q.set(k, s[k]); });
  if (ICONV) q.set("v", ICONV);
  return "api/icon-preview?" + q;
}
// which of the four icon sources a binding currently uses
function iconSource(b) {
  if (b.icon) return "image";
  if (b.glyph) return "symbol";
  if (b.icon_text) return "letters";
  return "auto";
}
function symbolKind(name) { return TELLTALE_SET.has(name) ? "dashboard symbol" : "Material icon"; }
// the glyph a binding gets with no explicit b.glyph (action-derived only)
function derivedGlyph(b) {
  if ("page" in b) { const v = String(b.page).toLowerCase(); return v === "prev" || v === "previous" ? "chevron_left" : v === "next" ? "chevron_right" : "layers"; }
  if ("profile" in b) { const v = String(b.profile).toLowerCase(); return { home: "home", auto: "refresh", next: "swap", prev: "swap" }[v] || "swap"; }
  if ("command" in b) return "terminal";
  return "";
}
function iconCaption(b) {
  switch (iconSource(b)) {
    case "image": return "your uploaded image";
    case "symbol": return `${symbolKind(b.glyph)} “${b.glyph}”`;
    case "letters": return `letters “${b.icon_text}”`;
    default: {
      const g = derivedGlyph(b);
      if (g) return `auto — ${symbolKind(g)} “${g}”`;
      if (b.label) return `auto — letters from the label`;
      return "auto — add a label or pick a symbol";
    }
  }
}

function navBindingFor(id) {
  const n = S.settings?.nav || {}, h = S.settings?.home || {};
  const isPrev = n.prev_key === id, isNext = n.next_key === id, isHome = h.key != null && h.key === id;
  if (!(isPrev || isNext || isHome)) return null;
  if (isHome && (isPrev || isNext) && pages().length > 1) return { page: isPrev ? "prev" : "next", hold: { profile: "home" }, role: "nav" };
  if (isHome) return { profile: "home", role: "nav" };
  return { page: isPrev ? "prev" : "next", role: "nav" };
}
function cellFor(id, cls) {
  const explicit = curPage().keys[id];
  const b = explicit || navBindingFor(id) || {};
  const reg = registerOf(b);
  const c = el("div", { class: `cell reg-${reg} ${cls || ""}` });
  c.dataset.id = id;
  if (!explicit && !b.role && id !== STATUS) c.classList.add("empty");
  if (S.sel && S.sel.kind === "key" && S.sel.index === id) c.classList.add("sel");
  if (id === (S.settings?.home?.key)) c.append(el("span", { class: "badge", textContent: "HOME" }));
  const u = id === STATUS ? iconURL(b.icon) : previewURL(b);
  if (u) c.append(iconImg(u));
  else c.append(el("div", { class: "lbl", textContent: b.label || labelFor(id), title: b.label || "" }));
  const v = explicit ? shortVal(b) : (b.role ? (b.hold ? "tap: page / hold: home" : b.page ? ("page " + b.page) : "home") : "");
  if (v) c.append(el("div", { class: "v", textContent: v, title: v }));
  c.onclick = () => selectControl("key", id);
  return c;
}
function renderDeck() {
  const d = $("#deck"); d.innerHTML = "";
  for (const row of KEY_ROWS) for (const id of row) d.append(cellFor(id, id === STATUS ? "wide" : ""));
  d.append(cellFor(AUX_L, "round"));
  for (const k of KNOBS) {
    const kb = curPage().knobs[k] || {};
    const c = el("div", { class: "cell knob reg-box" });
    c.dataset.id = k;
    if (S.sel && S.sel.kind === "knob" && S.sel.index === k) c.classList.add("sel");
    if (k === (S.settings?.home?.key)) c.append(el("span", { class: "badge", textContent: "HOME" }));
    c.append(el("div", { class: "lbl", textContent: "⟳ enc " + k }));
    const parts = ["left", "right", "press"].filter(s => kb[s] && actOf(kb[s]) !== "none")
      .map(s => kb[s].label || (s + " " + shortVal(kb[s])));
    if (parts.length) c.append(el("div", { class: "v", textContent: parts.join(" · "), title: parts.join(" · ") }));
    c.onclick = () => selectControl("knob", k);
    d.append(c);
  }
  d.append(cellFor(AUX_R, "round"));
}
function selectControl(kind, index) { S.sel = { kind, index }; renderDeck(); renderEditor(); }

// ---- editor: action block ------------------------------------
function actionBlock(binding, onChange) {
  const wrap = el("div");
  const sel = el("select");
  ACTIONS.forEach(a => sel.append(el("option", { value: a, textContent: a, selected: a === actOf(binding) })));
  const valFld = el("div", { class: "fld" });
  const rebuild = () => {
    valFld.innerHTML = "";
    const a = sel.value;
    if (a === "none") return;
    let input;
    if (a === "gamepad") input = el("input", { type: "number", min: 1, value: binding.gamepad || 1 });
    else if (a === "profile") { input = el("select"); [...S.profiles, "auto", "next", "prev", "home"].forEach(o => input.append(el("option", { value: o, textContent: o, selected: o === binding.profile }))); }
    else if (a === "page") { input = el("select"); ["next", "prev", "0", "1", "2", "3", "4"].forEach(o => input.append(el("option", { value: o, textContent: o, selected: String(binding.page) === o }))); }
    else input = el("input", { type: "text", value: binding[a] || "", placeholder: a === "key" ? "F13" : "e.g. sh -c 'crew-chief …'" });
    input.oninput = input.onchange = () => { setAct(binding, a, input.value); onChange(); };
    valFld.append(el("label", { textContent: "value" }), input);
    if (a === "gamepad") {
      const m = el("input", { type: "checkbox", checked: !!binding.momentary });
      m.onchange = () => { binding.momentary = m.checked || undefined; onChange(); };
      valFld.append(el("span"), el("label", { style: "display:flex;gap:.4rem;align-items:center" }, [m, "pulse (tap, not hold)"]));
    }
    if (ACTION_HINT[a]) valFld.append(el("div", { class: "hint", textContent: ACTION_HINT[a] }));
  };
  sel.onchange = () => { setAct(binding, sel.value, sel.value === "gamepad" ? 1 : ""); rebuild(); onChange(); };
  rebuild();
  wrap.append(el("div", { class: "fld" }, [el("label", { textContent: "action" }), sel]), valFld);
  return wrap;
}

// "bind this button in <game>" — writes the game's own controller config
async function ensureControls(game) {
  if (!(game in GAME_CONTROLS)) GAME_CONTROLS[game] = await api("games/" + game + "/controls").catch(() => null);
  return GAME_CONTROLS[game];
}
function gameBindRow(button) {
  const game = S.bindGame;
  const wrap = el("div"); wrap.style.gridColumn = "1 / -1";
  const head = el("div", { class: "hint", style: "margin-top:.4rem", textContent: "bind this button in " + game.toUpperCase() + " (game must be closed):" });
  const box = el("div", { style: "display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;margin-top:.2rem" });
  const sel = el("select"); sel.append(el("option", { textContent: "…" }));
  const go = el("button", { class: "ghost", textContent: "apply" });
  const msg = el("span", { class: "hint" });
  box.append(sel, go, msg); wrap.append(head, box);
  ensureControls(game).then(info => {
    sel.innerHTML = "";
    if (!info) { sel.append(el("option", { textContent: "(game config not found)" })); go.disabled = true; return; }
    if (!info.device_present) { sel.append(el("option", { textContent: "— bind any control to the deck in-game once first —" })); go.disabled = true; return; }
    sel.append(el("option", { value: "", textContent: "— not bound —" }));
    const cur = Object.entries(info.bound).find(([, b]) => b === button)?.[0] || "";
    info.controls.forEach(c => sel.append(el("option", { value: c, textContent: c, selected: c === cur })));
  });
  go.onclick = async () => {
    const info = GAME_CONTROLS[game] || { bound: {} };
    const prev = Object.entries(info.bound).find(([, b]) => b === button)?.[0];
    const next = sel.value;
    msg.textContent = "…"; msg.style.color = "var(--text-dim)";
    try {
      if (prev && prev !== next) await api("games/" + game + "/bind", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ control: prev, clear: true }) });
      if (next) await api("games/" + game + "/bind", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ control: next, button }) });
      GAME_CONTROLS[game] = undefined; msg.textContent = "saved"; msg.style.color = "var(--ok)";
    } catch (e) { msg.textContent = String(e).slice(0, 80); msg.style.color = "var(--danger)"; }
  };
  return wrap;
}

// ---- editor: the "Look" group -------------------------------
const SYMBOL_MEM = {};   // last symbol chosen per key this session, for quick Auto<->Symbol toggling
function initials(s) {
  const w = (s || "").replace(/[^\p{L}\p{N} ]+/gu, " ").trim().split(/\s+/).filter(Boolean);
  if (!w.length) return "";
  return (w.length === 1 ? w[0] : w.map(x => x[0]).join("")).slice(0, 4).toUpperCase();
}
// does mode `m` render on a circle/square frame? (frameless tell-tales don't)
function usesFrame(m, kb) {
  if (m === "image") return false;
  if (m === "symbol") return !TELLTALE_SET.has(kb.glyph);
  if (m === "letters") return true;
  const g = derivedGlyph(kb);
  return g ? !TELLTALE_SET.has(g) : true;   // label-initials sit on a frame
}
function lookField(kb, index) {
  const memk = `${S.name}/${S.page}/${index}`;
  if (kb.glyph) SYMBOL_MEM[memk] = kb.glyph;
  const grp = el("div", { class: "grp" }, [el("h3", { textContent: "Look" })]);
  const lab = el("input", { type: "text", value: kb.label || "", placeholder: "shown on the key" });
  grp.append(el("div", { class: "fld" }, [el("label", { textContent: "label" }), lab]));

  const grid = el("div", { class: "lookgrid" });
  const prev = el("div", { class: "lookprev" });
  const body = el("div", { class: "lookbody" });
  grid.append(prev, body);
  grp.append(grid);
  const cap = el("div", { class: "lookcap" });

  let mode = iconSource(kb);   // seg control drives this; may lead the data briefly

  const captionFor = () => {
    if (mode === "symbol" && !kb.glyph) return "pick a symbol";
    if (mode === "image" && !kb.icon) return "upload a PNG";
    return iconCaption(kb);
  };
  const draw = () => {                       // repaint preview + caption only
    prev.innerHTML = "";
    const u = previewURL(kb);
    prev.append(u ? el("img", { src: u }) : el("span", { class: "lookprev-empty", textContent: "—" }));
    cap.textContent = captionFor();
  };
  const commit = () => { draw(); renderDeck(); touched(); };   // the user changed something

  const applySymbol = name => {
    if (name) { kb.glyph = name; SYMBOL_MEM[memk] = name; delete kb.icon; delete kb.icon_text; mode = "symbol"; }
    else if (mode === "symbol" && !kb.glyph) mode = "auto";    // picker cancelled with nothing set
    paint(); commit();
  };
  const setMode = m => {
    mode = m;
    if (m === "auto") { delete kb.glyph; delete kb.icon_text; delete kb.icon; }
    if (m === "symbol") {
      delete kb.icon; delete kb.icon_text;
      if (!kb.glyph) {
        const g = SYMBOL_MEM[memk] || derivedGlyph(kb);   // adopt the current symbol; picker only if there's none
        if (g) kb.glyph = g;
        else { openSymbolPicker("", applySymbol); return; }
      }
    }
    if (m === "letters") { delete kb.glyph; delete kb.icon; if (!kb.icon_text) kb.icon_text = initials(kb.label) || undefined; }
    if (m === "image") { delete kb.glyph; delete kb.icon_text; }
    paint(); commit();
    if (m === "letters") body.querySelector("input")?.focus();
    if (m === "image" && !kb.icon) body.querySelector('input[type=file]')?.click();
  };
  const linkBtn = (text, onclick) => Object.assign(el("button", { class: "ghost", textContent: text }), { onclick });

  function paint() {
    body.innerHTML = "";
    const seg = el("div", { class: "seg" });
    for (const [k, txt] of [["auto", "Auto"], ["symbol", "Symbol"], ["letters", "Letters"], ["image", "Image"]]) {
      const b = el("button", { textContent: txt });
      b.classList.toggle("on", k === mode);
      b.onclick = () => setMode(k);
      seg.append(b);
    }
    body.append(seg);

    if (mode === "symbol") {
      const row = el("div", { class: "iconrow" });
      row.append(linkBtn(kb.glyph ? "Change…" : "Choose…", () => openSymbolPicker(kb.glyph, applySymbol)));
      if (COMPOSED_NAMES.has(kb.glyph)) row.append(linkBtn("customise", () => openCompose(kb.glyph)));
      body.append(row);
    } else if (mode === "auto") {
      const g = derivedGlyph(kb);
      if (COMPOSED_NAMES.has(g))
        body.append(el("div", { class: "iconrow" }, [linkBtn("customise " + g, () => openCompose(g))]));
    } else if (mode === "letters") {
      const t = el("input", { type: "text", maxLength: 4, value: kb.icon_text || "", placeholder: "1–4 letters" });
      t.oninput = () => { kb.icon_text = t.value.trim() || undefined; commit(); };
      body.append(el("div", { class: "iconrow" }, [t]));
    } else if (mode === "image") {
      const file = el("input", { type: "file", accept: "image/*", style: "max-width:12rem" });
      file.onchange = async () => {
        if (!file.files[0]) return;
        const buf = await file.files[0].arrayBuffer();
        const r = await api("icons", { method: "POST", headers: { "content-type": "image/png" }, body: buf });
        kb.icon = r.path; delete kb.icon_style; paint(); commit();
      };
      const row = el("div", { class: "iconrow" }, [file]);
      if (kb.icon) row.append(linkBtn("remove", () => { delete kb.icon; paint(); commit(); }));
      body.append(row);
    }

    if (usesFrame(mode, kb)) {
      const frame = el("div", { class: "lookframe" });
      frame.append(document.createTextNode(kb.icon_style ? "Frame & colour — custom  " : "Frame & colour — page default  "));
      frame.append(linkBtn("edit", () => openFrame(kb, mode)));
      if (kb.icon_style) frame.append(linkBtn("reset", () => { delete kb.icon_style; paint(); commit(); }));
      body.append(frame);
    }
    body.append(cap);
    draw();
  }

  lab.oninput = () => { kb.label = lab.value || undefined; commit(); };
  paint();
  return grp;
}
function openFrame(kb, mode) {
  const baseline = registerOf(kb) === "box"
    ? NAV_BASE
    : Object.assign({}, GAME_BASE, S.settings?.icon?.game, curPage().style);
  // preview what the key actually shows: letters -> the text, otherwise the glyph
  const glyph = (mode === "letters" || mode === "image") ? null : (kb.glyph || derivedGlyph(kb) || null);
  openIconStyle(kb, style => {
    if (Object.keys(style).length) kb.icon_style = style; else delete kb.icon_style;
    renderEditor(); renderDeck(); touched();
  }, "Frame & colour", {
    noText: true, baseline, glyph,
    note: "Just this key. “use page default” drops the override and follows the page again.",
  });
}

// ---- symbol picker -----------------------------------------
let SYM_ONPICK = null, SYM_CUR = "";
function openSymbolPicker(current, onPick) {
  SYM_ONPICK = onPick; SYM_CUR = current || "";
  $("#sym_q").value = "";
  buildSymGrid("");
  $("#symPick").showModal();
  setTimeout(() => $("#sym_q").focus(), 30);
}
function symTile(name, node) {
  const t = el("div", { class: "symtile" + (name === SYM_CUR ? " on" : "") });
  t.append(node, el("span", { textContent: name, title: name }));
  t.onclick = () => { $("#symPick").close(); SYM_ONPICK(name); };
  return t;
}
function buildSymGrid(q) {
  const box = $("#sym_grid"); box.innerHTML = "";
  const tt = (GLYPHS.telltales || GLYPHS.bases || []).filter(n => n.includes(q));
  const mat = Object.keys(GLYPHS.material || {}).filter(n => n.includes(q)).sort();
  if (tt.length) {
    box.append(el("h4", { textContent: "Dashboard & ISO" }));
    const grid = el("div", { class: "symtiles" });
    for (const n of tt)
      grid.append(symTile(n, el("img", { loading: "lazy", src: `api/icon-preview?glyph=${encodeURIComponent(n)}&fg=%23e7e9ec` })));
    box.append(grid);
  }
  if (mat.length) {
    box.append(el("h4", { textContent: "Material" }));
    const grid = el("div", { class: "symtiles" });
    for (const n of mat)
      grid.append(symTile(n, el("span", { class: "mi", textContent: String.fromCodePoint(parseInt(GLYPHS.material[n], 16)) })));
    box.append(grid);
  }
  if (!tt.length && !mat.length) box.append(el("div", { class: "lookcap", textContent: "no match" }));
}
$("#sym_q").oninput = () => buildSymGrid($("#sym_q").value.trim().toLowerCase());
$("#sym_cancel").onclick = () => $("#symPick").close();
$("#sym_clear").onclick = () => { $("#symPick").close(); if (SYM_ONPICK) SYM_ONPICK(null); };

// ---- editor: main --------------------------------------------
function renderEditor() {
  const e = $("#editor"); e.innerHTML = "";
  if (!S.sel) {
    document.body.dataset.register = "sim";
    e.classList.remove("reg-box");
    e.append(el("p", { class: "emptyhint", textContent: "Pick a control on the deck — or hit Listen and press one on the D200x." }));
    return;
  }
  const { kind, index } = S.sel;
  const isKnob = kind === "knob";
  const b = isKnob ? {} : (curPage().keys[index] || navBindingFor(index) || {});
  const reg = isKnob ? "box" : registerOf(curPage().keys[index] || b);
  document.body.dataset.register = reg;
  e.classList.toggle("reg-box", reg === "box");

  e.append(el("div", { class: "eyebrow", textContent: reg === "sim" ? "sim control" : "box control" }));
  e.append(el("h2", { textContent: (isKnob ? "Encoder " : "Key ") + index }));
  e.append(el("div", {
    class: "who",
    textContent: isKnob ? "rotary encoder — turn left / right / click"
      : index === STATUS ? "wide status key (also shows the clock)"
        : index === AUX_L || index === AUX_R ? "round aux button — no screen"
          : "LCD key",
  }));

  if (kind === "key") {
    const kb = keyB(index);
    const g1 = el("div", { class: "grp" }, [el("h3", { textContent: "Action" })]);
    g1.append(actionBlock(kb, () => { renderDeck(); touched(); }));
    e.append(g1);

    if (index === AUX_L || index === AUX_R) {
      e.append(el("p", { class: "hint", style: "margin-top:1rem", textContent: "This round button has no screen — a label or icon has no effect on the device. When there is more than one page it drives page navigation automatically." }));
      const clr0 = el("button", { class: "ghost danger", textContent: "clear this control", style: "margin-top:1rem" });
      clr0.onclick = () => { delete curPage().keys[index]; S.sel = null; render(); touched(); };
      e.append(clr0);
      return;
    }

    e.append(lookField(kb, index));
  } else {
    for (const sub of ["left", "right", "press"]) {
      const box = el("div", { class: "knobsub" }, [el("b", { textContent: sub === "press" ? "click" : "turn " + sub })]);
      const sb = knobB(index, sub);
      box.append(actionBlock(sb, () => { renderDeck(); touched(); }));
      const lab = el("input", { type: "text", value: sb.label || "", placeholder: "note (editor only)" });
      lab.oninput = () => { sb.label = lab.value || undefined; renderDeck(); touched(); };
      box.append(el("div", { class: "fld" }, [el("label", { textContent: "note" }), lab]));
      e.append(box);
    }
    e.append(el("p", { class: "hint", textContent: "Encoder click fires on release (firmware) — always a short pulse." }));
  }

  const clr = el("button", { class: "ghost danger", textContent: "clear this control", style: "margin-top:1rem" });
  clr.onclick = () => {
    if (kind === "key") delete curPage().keys[index]; else delete curPage().knobs[index];
    S.sel = null; render(); touched();
  };
  e.append(clr);
}

// ---- settings dialog ----------------------------------------
function openSettings() {
  const s = S.settings;
  $("#s_bri").value = s.device.brightness ?? 80; $("#s_bri_v").textContent = $("#s_bri").value;
  $("#s_hb").value = s.device.heartbeat_seconds;
  $("#s_grab").checked = s.device.grab_keyboard;
  $("#s_revert").value = s.home.revert_seconds;
  const hk = $("#s_homekey"); hk.innerHTML = ""; hk.append(el("option", { value: "", textContent: "(off)" }));
  [...KEY_ROWS.flat(), AUX_L, AUX_R, ...KNOBS].forEach(i =>
    hk.append(el("option", { value: i, textContent: labelFor(i) + " (" + i + ")", selected: String(s.home.key) === String(i) })));
  const hp = $("#s_homeprof"); hp.innerHTML = "";
  S.profiles.forEach(n => hp.append(el("option", { value: n, textContent: n, selected: n === s.home.profile })));
  $("#settings").showModal();
}
$("#s_bri").oninput = () => $("#s_bri_v").textContent = $("#s_bri").value;
$("#s_cancel").onclick = () => $("#settings").close();
$("#s_save").onclick = async () => {
  const s = S.settings;
  s.device.brightness = Number($("#s_bri").value);
  s.device.heartbeat_seconds = Number($("#s_hb").value);
  s.device.grab_keyboard = $("#s_grab").checked;
  s.home.key = $("#s_homekey").value === "" ? null : Number($("#s_homekey").value);
  s.home.profile = $("#s_homeprof").value;
  s.home.revert_seconds = Number($("#s_revert").value);
  await api("settings", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(s) });
  $("#settings").close(); renderDeck();
};

// ---- import dialog ----------------------------------------
async function openImport() {
  if (!Object.keys(GAMES).length) GAMES = await api("games").catch(() => ({}));
  const g = $("#i_game"); g.innerHTML = "";
  Object.keys(GAMES).forEach(k => g.append(el("option", { value: k, textContent: k.toUpperCase(), selected: true })));
  $("#i_report").hidden = true;
  syncImportPath();
  $("#importDlg").showModal();
}
function syncImportPath() {
  const info = GAMES[$("#i_game").value] || {};
  $("#i_path").value = info.path || "";
  $("#i_pathhint").textContent = info.path ? "auto-detected" : "not found — enter the game's install folder";
}
$("#i_game").onchange = syncImportPath;
$("#i_cancel").onclick = () => $("#importDlg").close();
$("#i_run").onclick = async () => {
  const body = { game: $("#i_game").value, path: $("#i_path").value || undefined, overwrite: $("#i_over").checked };
  try {
    const rep = await api("profiles/" + S.name + "/import", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const lines = [`labelled ${Object.keys(rep.applied).length} button(s)`];
    if (Object.keys(rep.skipped).length) lines.push(`\nkept your labels on: ${Object.entries(rep.skipped).map(([n, v]) => `btn ${n} (${v})`).join(", ")}`);
    if (Object.keys(rep.unmatched).length) lines.push(`\nbound in-game but not on any control:\n` + Object.entries(rep.unmatched).map(([n, v]) => `  btn ${n} = ${v}`).join("\n"));
    $("#i_report").textContent = lines.join("\n"); $("#i_report").hidden = false;
    await loadProfile(S.name);
  } catch (e) { $("#i_report").textContent = "import failed: " + e; $("#i_report").hidden = false; }
};

// ---- icon "style" generator (server-rendered preview) --------
let IG_ONSAVE = null, IG_BASE = null, IG_TARGET = null, IG_GLYPH = null;
const IG_DEFAULTS = { mode: "solid", shape: "circle", fill: "#1b1f26", border: "#4a9eff", fg: "#ffffff", font: "sans" };
function igStyle() {
  return {
    mode: $("#ig_mode").value, shape: $("#ig_shape").value, font: $("#ig_font").value,
    border: $("#ig_border").value, fill: $("#ig_fill").value, fg: $("#ig_fg").value,
  };
}
function igGlyph() { return IG_GLYPH || (IG_TARGET && IG_TARGET.glyph) || null; }
function igPreview() {
  const q = new URLSearchParams(igStyle());
  if (igGlyph()) q.set("glyph", igGlyph());              // preview the actual icon, not "AB"
  else q.set("text", $("#ig_text").value || (IG_TARGET && IG_TARGET.label) || "AB");
  $("#ig_prev").src = "api/icon-preview?" + q;
  // fill only matters with a solid frame; font only matters for text
  $("#ig_fill_fld").style.opacity = $("#ig_mode").value === "ring" ? ".45" : "";
  $("#ig_fill").disabled = $("#ig_mode").value === "ring";
  $("#ig_font_fld").style.display = igGlyph() ? "none" : "";
  $("#ig_fg_lbl").textContent = igGlyph() ? "Icon colour" : "Icon / text";
}
function openIconStyle(eff, onSave, title, opts = {}) {
  IG_TARGET = eff; IG_ONSAVE = onSave; IG_GLYPH = opts.glyph || null;
  IG_BASE = Object.assign({}, IG_DEFAULTS, opts.baseline || curPage().style || {});
  const s = Object.assign({}, IG_BASE, eff.icon_style || eff.style || {});
  $("#ig_title").textContent = title || "Icon style";
  $("#ig_note").textContent = opts.note || "";
  $("#ig_note").style.display = opts.note ? "" : "none";
  $("#ig_text_fld").style.display = (opts.noText || igGlyph()) ? "none" : "";
  $("#ig_text").value = eff.icon_text || "";
  $("#ig_mode").value = s.mode; $("#ig_shape").value = s.shape; $("#ig_font").value = s.font;
  $("#ig_border").value = s.border; $("#ig_fill").value = s.fill; $("#ig_fg").value = s.fg;
  $("#ig_sync").checked = false;
  igPreview();
  $("#iconGen").showModal();
}
function openPageStyle() {
  const pg = curPage();
  openIconStyle(pg.style || {}, style => {
    if (Object.keys(style).length) pg.style = style; else delete pg.style;
    renderDeck(); touched();
  }, "Default look — page " + (S.page + 1), {
    noText: true, baseline: IG_DEFAULTS,
    note: "The frame and colours every auto-generated icon on this page starts from. Any key can still override its own look.",
  });
}
["ig_text", "ig_mode", "ig_shape", "ig_font", "ig_border", "ig_fill", "ig_fg"].forEach(id => {
  $("#" + id).oninput = $("#" + id).onchange = () => {
    if ($("#ig_sync").checked && id === "ig_border") $("#ig_fg").value = $("#ig_border").value;
    igPreview();
  };
});
$("#ig_sync").onchange = () => { if ($("#ig_sync").checked) { $("#ig_fg").value = $("#ig_border").value; igPreview(); } };
$("#ig_reset").onclick = () => { IG_ONSAVE({}, ""); $("#iconGen").close(); };
$("#ig_cancel").onclick = () => $("#iconGen").close();
$("#ig_use").onclick = () => {
  const st = igStyle(), out = {};
  for (const k of STYLE_KEYS) if (st[k] !== undefined && st[k] !== IG_BASE[k]) out[k] = st[k];
  IG_ONSAVE(out, $("#ig_text").value.trim());
  $("#iconGen").close();
};

// ---- icon editor (parametric composed icons) ---------------
const C = { all: null, name: null, spec: null, t: null, url: null, openLayer: -1 };
const C_FIELDS = {
  arrow: [["at", "vec"], ["dir", "dir"], ["len", "n"], ["head", "n"], ["w", "n"]],
  arc: [["at", "vec"], ["r", "n"], ["deg", "deg"], ["arrow", "end"], ["w", "n"], ["head", "n"]],
  line: [["from", "vec"], ["to", "vec"], ["w", "n"]],
  tick: [["at", "vec"], ["dir", "dir"], ["len", "n"], ["w", "n"]],
};
const C_NEW = {
  arrow: { type: "arrow", at: [0.5, 0.5], dir: "up", len: 0.3, head: 0.12, w: 0.05 },
  arc: { type: "arc", at: [0.5, 0.5], r: 0.16, deg: [0, 270], arrow: "end", w: 0.04, head: 0.07 },
  line: { type: "line", from: [0.1, 0.9], to: [0.9, 0.9], w: 0.045 },
  tick: { type: "tick", at: [0.4, 0.5], dir: "up", len: 0.06, w: 0.035 },
};
async function openCompose(pick) {
  C.all = await api("compose");
  const sel = $("#c_name"); sel.innerHTML = "";
  for (const n of Object.keys(C.all).sort())
    sel.append(el("option", { value: n, textContent: n + (C.all[n].customised ? "  ✓" : "") }));
  const bsel = $("#c_base"); bsel.innerHTML = ""; bsel.append(el("option", { value: "", textContent: "(none)" }));
  try { const g = await api("glyphs"); for (const b of (g.bases || [])) bsel.append(el("option", { value: b, textContent: b })); } catch (e) { }
  cLoad(pick && C.all[pick] ? pick : sel.value);
  $("#composeDlg").showModal();
}
function cLoad(name) {
  C.name = name; C.openLayer = -1;
  $("#c_name").value = name;
  C.spec = JSON.parse(JSON.stringify(C.all[name].spec || {}));
  if (!Array.isArray(C.spec.layers)) C.spec.layers = [];
  $("#c_base").value = C.spec.base || "";
  $("#c_scale").value = C.spec.base_scale ?? 1;
  const at = C.spec.base_at || [0.5, 0.5];
  $("#c_bx").value = at[0]; $("#c_by").value = at[1];
  cLayers(); cPreview(); cState();
}
function cState() {
  const cz = C.all[C.name] && C.all[C.name].customised;
  $("#c_state").textContent = cz ? "customised — overrides the built-in" : "built-in default";
  $("#c_reset").disabled = !cz;
}
function cPreview() {
  const j = $("#c_json"); if (j) j.value = JSON.stringify(C.spec, null, 2);
  clearTimeout(C.t);
  C.t = setTimeout(async () => {
    try {
      const r = await fetch("api/compose/preview", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ spec: C.spec }) });
      if (!r.ok) return;
      const u = URL.createObjectURL(await r.blob());
      $("#c_prev_d").src = u; $("#c_prev_l").src = u;
      if (C.url) URL.revokeObjectURL(C.url);
      C.url = u;
    } catch (e) { }
  }, 120);
}
function cLayers() {
  const box = $("#c_layers"); box.innerHTML = "";
  if (!C.spec.layers.length) box.append(el("div", { class: "hint", textContent: "no overlay layers" }));
  C.spec.layers.forEach((ly, i) => {
    const d = el("details", { style: "border:1px solid var(--line);border-radius:6px;padding:.25rem .45rem" });
    d.open = (C.openLayer === i);
    const sum = el("summary", { textContent: ly.type + (ly.dir != null ? " · " + ly.dir : (ly.arrow ? " · " + ly.arrow : "")), style: "cursor:pointer;font-size:12px" });
    const del = el("button", { class: "ghost", textContent: "✕", title: "remove", style: "float:right;padding:0 .35rem" });
    del.onclick = ev => { ev.preventDefault(); C.spec.layers.splice(i, 1); C.openLayer = -1; cLayers(); cPreview(); };
    const up = el("button", { class: "ghost", textContent: "↑", title: "move up", style: "float:right;padding:0 .35rem" });
    up.onclick = ev => { ev.preventDefault(); if (i > 0) { const L = C.spec.layers;[L[i - 1], L[i]] = [L[i], L[i - 1]]; C.openLayer = i - 1; cLayers(); cPreview(); } };
    sum.append(del, up); d.append(sum);
    const body = el("div", { style: "padding:.35rem 0 .15rem;display:flex;flex-direction:column;gap:.3rem" });
    for (const [key, kind] of C_FIELDS[ly.type]) body.append(cField(ly, key, kind));
    d.append(body);
    d.ontoggle = () => { if (d.open) C.openLayer = i; };
    box.append(d);
  });
}
function cField(ly, key, kind) {
  const w = el("label", { style: "display:flex;gap:.4rem;align-items:center;font-size:12px" }, [el("span", { textContent: key, style: "width:3rem;color:var(--text-dim)" })]);
  const num = (get, set, step) => {
    const inp = el("input", { type: "number", step: step || "0.01", value: get(), style: "width:4.5rem" });
    inp.oninput = () => { set(+inp.value); cPreview(); };
    return inp;
  };
  if (kind === "vec") {
    const a = ly[key] || [0.5, 0.5]; ly[key] = a;
    w.append(num(() => a[0], v => a[0] = v), num(() => a[1], v => a[1] = v));
  } else if (kind === "deg") {
    const a = ly.deg || [0, 270]; ly.deg = a;
    w.append(num(() => a[0], v => a[0] = v, "5"), num(() => a[1], v => a[1] = v, "5"));
  } else if (kind === "dir") {
    const inp = el("input", { type: "text", value: ly.dir ?? "up", style: "width:6rem" });
    inp.oninput = () => { const v = inp.value.trim(); ly.dir = (v !== "" && !isNaN(+v)) ? +v : v; cPreview(); };
    w.append(inp, el("span", { class: "hint", textContent: "up/down/left/right or °" }));
  } else if (kind === "end") {
    const sel = el("select", {}, ["none", "start", "end"].map(o => el("option", { value: o, textContent: o })));
    sel.value = ly.arrow || "none";
    sel.onchange = () => { if (sel.value === "none") delete ly.arrow; else ly.arrow = sel.value; cPreview(); };
    w.append(sel);
  } else {
    w.append(num(() => ly[key] ?? 0.1, v => ly[key] = v));
  }
  return w;
}
$("#c_base").onchange = () => { const v = $("#c_base").value; if (v) C.spec.base = v; else delete C.spec.base; cPreview(); };
$("#c_scale").oninput = () => { C.spec.base_scale = +$("#c_scale").value; cPreview(); };
const cAt = () => { C.spec.base_at = [+$("#c_bx").value, +$("#c_by").value]; cPreview(); };
$("#c_bx").oninput = cAt; $("#c_by").oninput = cAt;
$("#c_name").onchange = () => cLoad($("#c_name").value);
document.querySelectorAll("#composeDlg [data-add]").forEach(btn => btn.onclick = ev => {
  ev.preventDefault();
  C.spec.layers.push(JSON.parse(JSON.stringify(C_NEW[btn.dataset.add])));
  C.openLayer = C.spec.layers.length - 1;
  cLayers(); cPreview();
});
$("#c_copy").onclick = ev => { ev.preventDefault(); navigator.clipboard?.writeText($("#c_json").value); };
$("#c_cancel").onclick = () => $("#composeDlg").close();
$("#c_save").onclick = async () => {
  try {
    await api("compose/" + encodeURIComponent(C.name), { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ spec: C.spec }) });
    C.all[C.name] = { spec: JSON.parse(JSON.stringify(C.spec)), builtin: (C.all[C.name] || {}).builtin !== false, customised: true };
    for (const o of $("#c_name").options) if (o.value === C.name && !o.textContent.endsWith("✓")) o.textContent = C.name + "  ✓";
    cState(); bumpIcons(); renderDeck();
  } catch (e) { alert("Save failed: " + e); }
};
$("#c_reset").onclick = async () => {
  if (!confirm("Discard your changes to " + C.name + " and revert to the built-in icon?")) return;
  try {
    await api("compose/" + encodeURIComponent(C.name), { method: "DELETE" });
    C.all = await api("compose");
    for (const o of $("#c_name").options) if (o.value === C.name) o.textContent = C.name + (C.all[C.name] && C.all[C.name].customised ? "  ✓" : "");
    bumpIcons(); cLoad(C.name); renderDeck();
  } catch (e) { alert("Reset failed: " + e); }
};

// ---- header wiring -----------------------------------------
$("#saveBtn").onclick = save;
$("#settingsBtn").onclick = openSettings;
$("#iconsBtn").onclick = () => openCompose();
$("#importBtn").onclick = openImport;
$("#pageGear").onclick = openPageStyle;
$("#listenBtn").onclick = () => {
  S.listening = !S.listening;
  $("#listenBtn").classList.toggle("on", S.listening);
  $("#listenBtn").textContent = S.listening ? "Listening…" : "Listen";
};
$("#profileSel").onchange = async e => {
  await api("activate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ profile: e.target.value }) });
  await loadProfile(e.target.value);
};
$("#addPage").onclick = () => {
  const newPage = { name: "", style: {}, keys: {}, knobs: {} };
  // 1 -> 2 pages: the aux buttons become page nav (automatic). Move anything
  // explicitly bound on them onto the new page's first free keys.
  if (pages().length === 1) {
    let slot = 0;
    for (const aux of [AUX_L, AUX_R]) {
      const b = pages()[0].keys[aux];
      if (b && !b.role) {
        while (newPage.keys[slot]) slot++;
        newPage.keys[slot++] = b;
        delete pages()[0].keys[aux];
      }
    }
  }
  pages().push(newPage); S.page = pages().length - 1; render(); touched();
};

document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
});
window.onbeforeunload = e => { if (S.dirty) { save(); } };

boot().catch(e => {
  console.error(e);
  $("#editor").innerHTML = '<p class="emptyhint">Cannot reach the daemon API. Is <code>d200x-buttonboxd</code> running?</p>';
});
