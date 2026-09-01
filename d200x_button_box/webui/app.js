// D200x Button Box — web UI (organised vanilla, no build step).
// Phase 1 of the frontend overhaul: tokens + hero deck + docked editor +
// sim/box registers + autosave-by-default. Dialogs still <dialog> (phase 3).

const KEY_ROWS = [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11, 12, 13]];
const AUX_L = 15, AUX_R = 16, STATUS = 13, KNOBS = [17, 18, 19];
const ACTIONS = ["none", "gamepad", "nav", "key", "command", "profile", "page"];
const ACTION_LABEL = { nav: "navigate" };
const ACTION_HINT = {
  gamepad: "virtual joystick button the game binds",
  nav: "jump home or flip pages — like the aux buttons, but on a screen key",
  key: "keystroke (ydotool/xdotool)",
  command: "shell command on the daemon host",
  profile: "switch profile — or auto / next / prev / home",
  page: "switch page in this profile",
};
const NAV_FNS = [["home", "Home"], ["prev_page", "Previous page"], ["next_page", "Next page"]];
const NAV_FN_LABEL = Object.fromEntries(NAV_FNS);
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
const bumpIcons = () => { ICONV++; };

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

function isNav(b) { return b.role === "nav" || "page" in b || "profile" in b || "nav" in b; }
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
  TELLTALE_SET = new Set(GLYPHS.telltales || []);
  S.bindGame = Object.entries(GAMES).find(([, g]) => g.can_write && g.path)?.[0] || null;
  await loadProfile(S.name);
  connectSSE();
  maybeIntro();
}
function maybeIntro() {
  let seen;
  try { seen = localStorage.getItem("d200x_intro"); } catch (e) { seen = "1"; }
  if (seen) return;
  const card = el("div", { class: "introcard" }, [
    el("h2", { textContent: "This is your deck" }),
    el("p", { textContent: "13 LCD keys, 2 round aux buttons, 3 encoders. Click a control to bind it — or read your bindings straight from a game." }),
    el("div", { class: "introacts" }, [
      Object.assign(el("button", { class: "primary", textContent: "Got it" }), {
        onclick: () => { try { localStorage.setItem("d200x_intro", "1"); } catch (e) {} ov.remove(); },
      }),
      Object.assign(el("button", { class: "ghost", textContent: "Import from a game…" }), {
        onclick: () => { try { localStorage.setItem("d200x_intro", "1"); } catch (e) {} ov.remove(); openDrawer("import"); },
      }),
    ]),
  ]);
  const ov = el("div", { class: "introov" }, [card]);
  ov.onclick = e => { if (e.target === ov) { try { localStorage.setItem("d200x_intro", "1"); } catch (e2) {} ov.remove(); } };
  document.body.append(ov);
}
async function loadProfile(name) {
  S.name = name; S.page = 0; S.sel = null; S.dirty = false;
  S.profile = normalize(name, await api("profiles/" + name));
  DECK_IMG.clear();
  UNDO = []; UNDO_BASE = JSON.stringify(serialize()); UNDO_AT = 0;
  render();
}

// ---- undo (profile edits only) ----------------------------------
let UNDO = [], UNDO_BASE = null, UNDO_AT = 0;
function touched() {
  if (UNDO_BASE !== null) {
    // coalesce a burst of edits (e.g. typing) into one undo step
    if (Date.now() - UNDO_AT > 600) { UNDO.push(UNDO_BASE); if (UNDO.length > 50) UNDO.shift(); }
    UNDO_BASE = JSON.stringify(serialize());
  }
  UNDO_AT = Date.now();
  S.dirty = true; renderStatus(); scheduleSave();
}
function undo() {
  if (!UNDO.length) { toast("Nothing to undo"); return; }
  const snap = UNDO.pop();
  S.profile = normalize(S.name, JSON.parse(snap));
  UNDO_BASE = snap; UNDO_AT = 0;
  S.sel = null; S.dirty = true;
  render(); renderStatus(); scheduleSave();
  toast("Undone");
}
let TOAST_T = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(TOAST_T);
  TOAST_T = setTimeout(() => t.classList.remove("show"), 1800);
}
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
function render() { renderChrome(); renderDeck(); renderEditor(); renderStatus(); }
// chrome = everything outside the deck/editor that follows the profile list
function renderChrome() {
  syncProfileSel(); renderPageStrip(); renderRail();
  if (DRAWER_PANEL === "profiles" && $("#drawer").classList.contains("open")) {
    const b = $("#drawer_body"); b.innerHTML = ""; buildProfiles(b);
  }
}
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
function gotoPage(i) {
  S.page = i; S.sel = null; render();
  api("page", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ page: i }) });
}
function renderPageStrip() {
  const strip = $("#pagestrip"); strip.innerHTML = "";
  const multi = pages().length > 1;
  pages().forEach((pg, i) => {
    const tab = el("div", { class: "ptab" + (i === S.page ? " on" : "") });
    const name = el("span", { class: "pname", textContent: pg.name || ("page " + (i + 1)) });
    name.onclick = () => {
      if (i !== S.page) { gotoPage(i); return; }
      const inp = el("input", { value: pg.name || "", placeholder: "page " + (i + 1) });
      inp.onblur = inp.onchange = () => { pg.name = inp.value.trim() || undefined; renderPageStrip(); renderDeck(); touched(); };
      inp.onkeydown = e => { if (e.key === "Enter") inp.blur(); };
      tab.replaceChild(inp, name); inp.focus(); inp.select();
    };
    tab.append(name);
    if (multi) {
      const x = el("button", { class: "x", textContent: "✕", title: "delete this page" });
      x.onclick = () => {
        if (!confirm("Delete " + (pg.name || "page " + (i + 1)) + "?")) return;
        pages().splice(i, 1);
        S.page = Math.min(S.page, pages().length - 1); S.sel = null;
        render(); touched();
      };
      tab.append(x);
    }
    strip.append(tab);
  });
  const add = el("button", { class: "addpage", textContent: "＋ page" });
  add.onclick = addPage;
  strip.append(add);
  const gear = el("button", { class: "addpage", textContent: "⚙ default look", title: "the frame + colour every auto icon on this page starts from" });
  gear.onclick = openPageStyle;
  strip.append(gear);
  if (multi)
    strip.append(el("div", { class: "auxnote", textContent: "the two round aux buttons flip pages — hold the left one for home" }));
}
function addPage() {
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
  pages().push(newPage); S.page = pages().length - 1; S.sel = null; render(); touched();
}

// ---- deck ------------------------------------------------------
// One <img> per key id, kept across re-renders. When the icon URL changes the
// old pixels stay on screen until the new image has decoded — no blank flash.
const DECK_IMG = new Map();
function deckIcon(id, url) {
  let im = DECK_IMG.get(id);
  if (!im) { im = el("img", { src: url, alt: "" }); im.dataset.src = url; DECK_IMG.set(id, im); return im; }
  if (im.dataset.src !== url) {
    im.dataset.src = url;
    const probe = new Image();
    probe.onload = () => { if (im.dataset.src === url) im.src = url; };
    probe.src = url;
  }
  return im;
}
function labelFor(id) {
  return keyName(KNOBS.includes(id) ? "knob" : "key", id, null);
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
      if (b.label) return `auto — from the label (a matching symbol, else initials)`;
      return "auto — add a label or pick a symbol";
    }
  }
}

const NAV_ACT = fn => fn === "home" ? { profile: "home" }
  : fn === "prev_page" ? { page: "prev" }
    : fn === "next_page" ? { page: "next" } : null;
function navBindingFor(id) {
  const cfg = S.settings?.nav?.binds?.[id];
  if (!cfg) return null;
  const tap = NAV_ACT(cfg.tap), hold = NAV_ACT(cfg.hold);
  if (!tap && !hold) return null;
  const b = Object.assign({ role: "nav" }, tap || {});
  if (hold) b.hold = hold;
  return b;
}
function cellFor(id, cls) {
  const explicit = curPage().keys[id];
  const b = explicit || navBindingFor(id) || {};
  const reg = registerOf(b);
  const c = el("div", { class: `cell reg-${reg} ${cls || ""}`, tabIndex: 0 });
  c.dataset.id = id;
  c.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); c.click(); } };
  if (!explicit && !b.role && id !== STATUS) c.classList.add("empty");
  if (S.sel && S.sel.kind === "key" && S.sel.index === id) c.classList.add("sel");
  const navCfg = S.settings?.nav?.binds?.[id];
  if (navCfg?.tap === "home" || navCfg?.hold === "home") c.append(el("span", { class: "badge", textContent: "HOME" }));
  const sMode = id === STATUS ? (b.status || (b.clock === false ? "load" : "clock")) : null;
  if (id === STATUS && sMode !== "off") {
    c.append(el("div", { class: "lbl", textContent: sMode === "load" ? "▤ system load" : "🕐 clock" }));
  } else if (id === STATUS) {
    let u = previewURL(b);
    if (u) { u += "&w=458&h=196"; const im = deckIcon(id, u); im.className = "statwide"; c.append(im); }
    else c.append(el("div", { class: "lbl", textContent: b.label || labelFor(id) }));
  } else {
    const u = previewURL(b);
    if (u) { const im = deckIcon(id, u); im.className = ""; c.append(im); }
    else c.append(el("div", { class: "lbl", textContent: b.label || labelFor(id), title: b.label || "" }));
  }
  let v = explicit ? shortVal(b) : (navCfg ? navRoleText(navCfg) : "");
  if (!v && (id === AUX_L || id === AUX_R)) v = "round button · set in Navigation";
  if (v) c.append(el("div", { class: "v", textContent: v, title: v }));
  c.onclick = () => selectControl("key", id);
  if (DRAG_OK(id)) makeDraggable(c, id);
  return c;
}
// drag a binding from one LCD key to another (swap if the target is taken)
const DRAG_OK = id => KEY_ROWS.flat().includes(id) && id !== STATUS;
function makeDraggable(c, id) {
  if (curPage().keys[id]) {
    c.draggable = true;
    c.ondragstart = e => { e.dataTransfer.setData("text/plain", String(id)); e.dataTransfer.effectAllowed = "move"; c.classList.add("dragging"); };
    c.ondragend = () => c.classList.remove("dragging");
  }
  c.ondragover = e => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; c.classList.add("dragover"); };
  c.ondragleave = () => c.classList.remove("dragover");
  c.ondrop = e => {
    e.preventDefault(); c.classList.remove("dragover");
    const from = Number(e.dataTransfer.getData("text/plain"));
    if (!Number.isInteger(from) || from === id || !DRAG_OK(from)) return;
    const k = curPage().keys, a = k[from], b = k[id];
    if (!a) return;
    if (b) k[from] = b; else delete k[from];
    k[id] = a;
    S.sel = { kind: "key", index: id };
    render(); touched();
    toast(b ? "Swapped" : "Moved");
  };
}
function renderDeck() {
  const d = $("#deck"); d.innerHTML = "";
  for (const row of KEY_ROWS) for (const id of row) d.append(cellFor(id, id === STATUS ? "wide" : ""));
  // bottom row on the real D200x: the two round aux buttons, then the 3 encoders
  d.append(cellFor(AUX_L, "round"));
  d.append(cellFor(AUX_R, "round"));
  for (const k of KNOBS) {
    const kb = curPage().knobs[k] || {};
    const c = el("div", { class: "cell knob reg-box", tabIndex: 0 });
    c.dataset.id = k;
    c.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); c.click(); } };
    if (S.sel && S.sel.kind === "knob" && S.sel.index === k) c.classList.add("sel");
    if (k === (S.settings?.home?.key)) c.append(el("span", { class: "badge", textContent: "HOME" }));
    c.append(el("div", { class: "lbl", textContent: "⟳ " + labelFor(k) }));
    const parts = ["left", "right", "press"].filter(s => kb[s] && actOf(kb[s]) !== "none")
      .map(s => kb[s].label || (s + " " + shortVal(kb[s])));
    c.append(parts.length
      ? el("div", { class: "v", textContent: parts.join(" · "), title: parts.join(" · ") })
      : el("div", { class: "v hinttext", textContent: "turn · click" }));
    c.onclick = () => selectControl("knob", k);
    d.append(c);
  }
}
function selectControl(kind, index) {
  S.sel = { kind, index }; renderDeck(); renderEditor();
  document.querySelector(`.cell[data-id="${index}"]`)?.focus();
}

// ---- editor: action block ------------------------------------
function actionBlock(binding, onChange) {
  const wrap = el("div");
  const sel = el("select");
  ACTIONS.forEach(a => sel.append(el("option", { value: a, textContent: ACTION_LABEL[a] || a, selected: a === actOf(binding) })));
  const valFld = el("div", { class: "fld" });
  const rebuild = () => {
    valFld.innerHTML = "";
    const a = sel.value;
    if (a === "none") return;
    let input;
    if (a === "gamepad") input = el("input", { type: "number", min: 1, value: binding.gamepad || 1 });
    else if (a === "nav") { input = el("select"); NAV_FNS.forEach(([v, t]) => input.append(el("option", { value: v, textContent: t, selected: v === (binding.nav || "home") }))); }
    else if (a === "profile") { input = el("select"); [...S.profiles, "auto", "next", "prev", "home"].forEach(o => input.append(el("option", { value: o, textContent: o, selected: o === binding.profile }))); }
    else if (a === "page") { input = el("select"); ["next", "prev", "0", "1", "2", "3", "4"].forEach(o => input.append(el("option", { value: o, textContent: o, selected: String(binding.page) === o }))); }
    else input = el("input", { type: "text", value: binding[a] || "", placeholder: a === "key" ? "F13" : "e.g. sh -c 'crew-chief …'" });
    if (a === "nav" && !binding.nav) binding.nav = input.value;   // seed the default
    input.oninput = input.onchange = () => { setAct(binding, a, input.value); onChange(); };
    valFld.append(el("label", { textContent: "value" }), input);
    if (a === "gamepad") {
      const m = el("input", { type: "checkbox", checked: !!binding.momentary });
      m.onchange = () => { binding.momentary = m.checked || undefined; onChange(); };
      valFld.append(el("span"), el("label", { style: "display:flex;gap:.4rem;align-items:center" }, [m, "pulse (tap, not hold)"]));
    }
    if (ACTION_HINT[a]) valFld.append(el("div", { class: "hint", textContent: ACTION_HINT[a] }));
    if (a === "gamepad" && S.bindGame) valFld.append(gameBindRow(Number(binding.gamepad) || 1));
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
// "frame" = draws on a circle/square frame; "colour" = frameless tell-tale
// (only its colour is adjustable); null = image (no colour controls).
function frameKind(m, kb) {
  if (m === "image") return null;
  const g = m === "symbol" ? kb.glyph : m === "auto" ? derivedGlyph(kb) : null;
  return (g && TELLTALE_SET.has(g)) ? "colour" : "frame";
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
    if (mode === "symbol" && !kb.glyph) return "showing auto — Choose a symbol to override";
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
      // adopt the current effective symbol; never auto-open the picker
      // (the "Choose…" button does that when the user wants it)
      if (!kb.glyph) { const g = SYMBOL_MEM[memk] || derivedGlyph(kb); if (g) kb.glyph = g; }
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

    const fk = frameKind(mode, kb);
    if (fk) {
      const noun = fk === "colour" ? "Colour" : "Frame & colour";
      const frame = el("div", { class: "lookframe" });
      frame.append(document.createTextNode(noun + (kb.icon_style ? " — custom  " : " — page default  ")));
      frame.append(linkBtn("edit", () => openFrame(kb, mode)));
      if (kb.icon_style) frame.append(linkBtn("reset", () => { delete kb.icon_style; paint(); commit(); }));
      body.append(frame);
    }
    body.append(cap);
    draw();
  }

  lab.oninput = () => {
    kb.label = lab.value || undefined;
    const h = document.querySelector("#editor h2");   // keep the title in sync without losing focus
    if (h) h.textContent = keyName("key", index, kb);
    commit();
  };
  paint();
  return grp;
}
function openFrame(kb, mode) {
  const baseline = registerOf(kb) === "box"
    ? NAV_BASE
    : Object.assign({}, GAME_BASE, S.settings?.icon?.game, curPage().style);
  // preview what the key actually shows on the device
  const textMode = mode === "letters" || mode === "image";
  const glyph = textMode ? null : (kb.glyph || derivedGlyph(kb) || null);
  // no explicit/derived glyph but the label keyword-matches one server-side:
  // let the preview resolve it from the label rather than fall back to "AB"
  const label = (!textMode && !glyph && kb.label) ? kb.label : null;
  const frameless = !!(glyph && TELLTALE_SET.has(glyph));
  openIconStyle(kb, style => {
    if (Object.keys(style).length) kb.icon_style = style; else delete kb.icon_style;
    renderEditor(); renderDeck(); touched();
  }, frameless ? "Colour — this key" : "Frame & colour — this key", {
    noText: true, baseline, glyph, label, style: kb.icon_style || {},
    saveLabel: "Apply", clearLabel: "Use page default",
    note: "Overrides the page default for this key only.",
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
  const tt = (GLYPHS.telltales || []).filter(n => n.includes(q));
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

// ---- naming --------------------------------------------------
function keyName(kind, index, b) {
  if (b && b.label) return b.label;
  if (kind === "knob") return "Encoder " + (KNOBS.indexOf(index) + 1);
  if (index === STATUS) return "Status key";
  if (index === AUX_L) return "Aux left";
  if (index === AUX_R) return "Aux right";
  return "Key " + (index + 1);
}
function navRoleText(cfg) {
  const part = s => cfg[s] ? `${s}: ${NAV_FN_LABEL[cfg[s]]}` : null;
  return [part("tap"), part("hold")].filter(Boolean).join(" · ") || "unassigned";
}
function keyRole(kind, index, b) {
  if (kind === "knob") return "Rotary encoder";
  if (index === AUX_L || index === AUX_R) {
    const cfg = S.settings?.nav?.binds?.[index];
    return cfg ? "Navigation — " + navRoleText(cfg) : "Aux button — unassigned";
  }
  const a = actOf(b);
  return ({
    none: "Unassigned",
    gamepad: "Controller button " + (b.gamepad || 1) + (b.momentary ? " · pulse" : ""),
    nav: "Navigate → " + (NAV_FN_LABEL[b.nav] || "?"),
    key: "Sends a keystroke",
    command: "Runs a command",
    profile: "Switches profile → " + (b.profile || "?"),
    page: "Page " + (b.page || "?"),
  })[a] || a;
}

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

  e.append(el("div", { class: "eyebrow", textContent: keyRole(kind, index, b) }));
  e.append(el("h2", { textContent: keyName(kind, index, curPage().keys[index] || b) }));
  e.append(el("div", {
    class: "who",
    textContent: isKnob ? "rotary encoder — turn left / right / click"
      : index === STATUS ? "wide key — the firmware clock / system readout strip"
        : index === AUX_L || index === AUX_R ? "round button, no screen"
          : "LCD key",
  }));

  // keep the title + role + register accent current as the binding changes
  const syncHeader = kb => {
    const r = isKnob ? "box" : registerOf(kb);
    document.body.dataset.register = r;
    e.classList.toggle("reg-box", r === "box");
    e.querySelector(".eyebrow").textContent = keyRole(kind, index, kb);
    e.querySelector("h2").textContent = keyName(kind, index, kb);
  };

  if (kind === "key") {
    const kb = keyB(index);
    const g1 = el("div", { class: "grp" }, [el("h3", { textContent: "Action" })]);
    g1.append(actionBlock(kb, () => { syncHeader(kb); renderDeck(); touched(); }));
    e.append(g1);

    if (index === AUX_L || index === AUX_R) {
      const nb = navBindingFor(index);
      e.append(el("p", { class: "hint", style: "margin-top:1rem", textContent:
        (nb ? `Currently: ${keyRole(kind, index, b)}. ` : "") +
        "This round button has no screen. Its home / page-nav role is set in the Navigation panel." }));
      const clr0 = el("button", { class: "ghost danger", textContent: "clear this control", style: "margin-top:1rem" });
      clr0.onclick = () => { delete curPage().keys[index]; S.sel = null; render(); touched(); };
      e.append(clr0);
      return;
    }

    if (index === STATUS) {
      const cur = kb.status === "load" || kb.clock === false ? "load" : (kb.status === "off" ? "off" : "clock");
      const sel = el("select");
      [["clock", "Clock"], ["load", "System load (CPU · RAM)"], ["off", "Custom icon"]].forEach(([v, t]) =>
        sel.append(el("option", { value: v, textContent: t, selected: v === cur })));
      sel.onchange = () => {
        delete kb.clock;
        if (sel.value === "clock") delete kb.status; else kb.status = sel.value;
        renderEditor(); renderDeck(); touched();
      };
      const g = el("div", { class: "grp" }, [el("h3", { textContent: "Status strip" })]);
      g.append(el("div", { class: "fld" }, [el("label", { textContent: "shows" }), sel]));
      g.append(el("div", { class: "hint", style: "grid-column:2", textContent:
        cur === "off"
          ? "The firmware small window is set to BACKGROUND mode so this wide key shows the icon below."
          : "The firmware fills this wide key with the clock / system readout." }));
      e.append(g);
      if (cur === "off") e.append(lookField(kb, index));
    } else {
      e.append(lookField(kb, index));
    }
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

// ---- drawer (settings / profiles / import) ------------------
const PANELS = {
  profiles: { title: "Profiles", build: buildProfiles },
  settings: { title: "Settings", build: buildSettings },
  import: { title: "Import from a game", build: buildImport },
};
let DRAWER_PANEL = null;
function openDrawer(panel) {
  const key = PANELS[panel] ? panel : "settings";
  DRAWER_PANEL = key;
  $("#drawer_title").textContent = PANELS[key].title;
  const body = $("#drawer_body"); body.innerHTML = "";
  PANELS[key].build(body);
  $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("open");
}
function closeDrawer() {
  DRAWER_PANEL = null;
  $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").classList.remove("open");
}
$("#drawer_close").onclick = closeDrawer;
$("#scrim").onclick = closeDrawer;
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

function section(title, ...kids) { return el("section", {}, [el("h4", { textContent: title }), ...kids]); }
function fld(labelText, control, hint) {
  const f = el("div", { class: "fld" }, [el("label", { textContent: labelText }), control]);
  if (hint) f.append(el("div", { class: "hint", textContent: hint }));
  return f;
}

async function refreshProfiles() {
  const pl = await api("profiles");
  S.profiles = pl.profiles;
  if (!S.profiles.includes(S.name)) { S.name = pl.active; await loadProfile(S.name); }
}

// -- profile actions (shared by the rail + the drawer panel) --
const PROF = {
  async activate(n) {
    await api("activate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ profile: n }) });
    await loadProfile(n); await refreshProfiles(); renderChrome();
  },
  async rename(n, to, after) {
    if (!to || to === n) return;
    try {
      const r = await api("profiles/" + encodeURIComponent(n) + "/rename", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ to }) });
      if (S.name === n) S.name = r.name;
      await refreshProfiles(); renderChrome();
    } catch (e) { alert("Rename failed: " + e); if (after) after(); }
  },
  async duplicate(n, to) {
    try { await api("profiles/" + encodeURIComponent(n) + "/duplicate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ to }) }); await refreshProfiles(); renderChrome(); }
    catch (e) { alert("Duplicate failed: " + e); }
  },
  async create(name) {
    await api("profiles/" + encodeURIComponent(name), { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    await refreshProfiles(); renderChrome();
  },
  async remove(n) {
    await api("profiles/" + encodeURIComponent(n), { method: "DELETE" });
    await refreshProfiles(); renderChrome();
  },
  async setHome(n) {
    S.settings.home.profile = n;
    await api("settings", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(S.settings) });
    renderChrome();
  },
};
// an editable name span: click to rename in place
function nameField(n, cls) {
  const wrap = el("span", { class: cls || "" });
  const text = el("span", { textContent: n });
  text.onclick = () => {
    const inp = el("input", { value: n });
    inp.onkeydown = e => { if (e.key === "Enter") inp.blur(); if (e.key === "Escape") { inp.value = n; inp.blur(); } };
    inp.onblur = () => PROF.rename(n, inp.value.trim(), () => renderChrome());
    wrap.replaceChild(inp, text); inp.focus(); inp.select();
  };
  wrap.append(text);
  return wrap;
}
// "＋ New profile" that expands to an inline input (no browser prompt)
function newProfileButton(cls) {
  const btn = el("button", { class: cls || "ghost", textContent: "＋ New profile" });
  btn.onclick = () => {
    const inp = el("input", { placeholder: "profile name", style: "width:100%" });
    inp.onkeydown = e => { if (e.key === "Enter") inp.blur(); if (e.key === "Escape") { inp.value = ""; inp.blur(); } };
    inp.onblur = () => { const v = inp.value.trim(); if (v) PROF.create(v); else renderChrome(); };
    btn.replaceWith(inp); inp.focus();
  };
  return btn;
}

// -- Profiles drawer panel (full management) --
function buildProfiles(body) {
  body.append(el("p", { class: "concept", html:
    "A <b>profile</b> is a whole deck setup — one per game, plus a launcher. " +
    "The daemon switches profiles automatically by which game is running, or you pick one here. " +
    "<b>Pages</b> are layers inside a profile; the round aux buttons flip between them." }));

  const list = el("section", {}, [el("h4", { textContent: "Profiles" })]);
  for (const n of S.profiles) {
    const row = el("div", { class: "prow" }, [nameField(n, "pname")]);
    if (n === S.name) row.append(el("span", { class: "ptag active", textContent: "active" }));
    if (n === S.settings.home.profile) row.append(el("span", { class: "ptag home", textContent: "home" }));
    const acts = el("div", { class: "pacts" });
    const btn = (t, fn, danger) => Object.assign(el("button", { class: "ghost" + (danger ? " danger" : ""), textContent: t }), { onclick: fn });
    if (n !== S.name) acts.append(btn("use", () => PROF.activate(n)));
    acts.append(btn("duplicate", () => {
      const inp = el("input", { value: n + "-copy", style: "width:7rem" });
      inp.onkeydown = e => { if (e.key === "Enter") inp.blur(); if (e.key === "Escape") { inp.value = ""; inp.blur(); } };
      inp.onblur = () => { const v = inp.value.trim(); if (v) PROF.duplicate(n, v); else renderChrome(); };
      acts.replaceChildren(inp); inp.focus(); inp.select();
    }));
    if (n !== S.settings.home.profile) acts.append(btn("set home", () => PROF.setHome(n)));
    if (n !== S.name && n !== S.settings.home.profile && S.profiles.length > 1)
      acts.append(btn("delete", () => { if (confirm("Delete profile “" + n + "”?")) PROF.remove(n); }, true));
    row.append(acts);
    list.append(row);
  }
  list.append(el("div", { style: "margin-top:.6rem" }, [newProfileButton()]));
  body.append(list);

  if (!RAIL_MQ.matches) { const nav = el("section"); navSection(nav); body.append(nav); }

  body.append(section("Set up from a game",
    el("p", { class: "hint", textContent: "Read a game's own bindings and label the deck keys bound to the D200x controller in-game." }),
    Object.assign(el("button", { class: "ghost", textContent: "Import from a game…" }), { onclick: () => openDrawer("import") })));
}

// -- left rail (desktop): compact profile switcher --
const RAIL_MQ = window.matchMedia("(min-width: 1080px)");
function renderRail() {
  const rail = $("#rail");
  if (!RAIL_MQ.matches) { rail.hidden = true; return; }
  rail.hidden = false; rail.innerHTML = "";
  rail.append(el("h4", { class: "railhead", textContent: "Profiles" }));
  for (const n of S.profiles) {
    const row = el("div", { class: "railrow" + (n === S.name ? " on" : "") });
    if (n === S.name) row.append(nameField(n));
    else { const s = el("span", { textContent: n }); s.onclick = () => PROF.activate(n); row.append(s); }
    if (n === S.settings.home.profile) row.append(el("span", { class: "ptag home", textContent: "home" }));
    rail.append(row);
  }
  rail.append(el("div", { style: "margin-top:8px;display:flex;flex-direction:column;gap:6px" }, [
    newProfileButton("railnew"),
    Object.assign(el("button", { class: "ghost", textContent: "Manage profiles…" }), { onclick: () => openDrawer("profiles") }),
  ]));

  navSection(rail, true);
}
RAIL_MQ.addEventListener("change", () => { renderRail(); });

async function saveSettings() {
  await api("settings", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(S.settings) });
}
const NAV_TARGETS = [AUX_L, AUX_R, ...KEY_ROWS.flat().filter(i => i !== STATUS), STATUS, ...KNOBS];
const navBinds = () => (S.settings.nav.binds ||= {});
async function commitNav() {
  for (const [k, v] of Object.entries(navBinds()))
    if (!v.tap && !v.hold) delete navBinds()[k];
  await saveSettings(); renderChrome(); renderDeck();
  if (S.sel) renderEditor();
}
// per-button tap/hold navigation config — used by the rail and the mobile drawer
function navSection(host, compact) {
  host.append(el("h4", { class: compact ? "railhead" : "", style: "margin-top:16px", textContent: "Navigation" }));
  host.append(el("p", { class: "hint", textContent: "Each button can do one thing on a quick tap and another on a long hold. Applies to every profile." }));

  const keys = Object.keys(navBinds()).map(Number).sort((a, b) => a - b);
  for (const idx of keys) {
    const cfg = navBinds()[idx];
    const row = el("div", { class: "navrow" });
    const rm = el("button", { textContent: "✕", title: "unassign this button" });
    rm.onclick = () => { delete navBinds()[idx]; commitNav(); };
    row.append(el("div", { class: "navrow-key" }, [el("b", { textContent: keyName("key", idx, null) }), rm]));
    for (const slot of ["tap", "hold"]) {
      const sel = el("select");
      sel.append(el("option", { value: "", textContent: (slot === "tap" ? "tap (quick press)" : "hold (long press)") + " → —" }));
      NAV_FNS.forEach(([v, t]) => sel.append(el("option", { value: v, textContent: (slot === "tap" ? "tap → " : "hold → ") + t, selected: cfg[slot] === v })));
      sel.onchange = () => { if (sel.value) cfg[slot] = sel.value; else delete cfg[slot]; commitNav(); };
      row.append(sel);
    }
    host.append(row);
  }

  const free = NAV_TARGETS.filter(i => !(i in navBinds()));
  if (free.length) {
    const add = el("select");
    add.append(el("option", { value: "", textContent: "＋ assign a button…" }));
    free.forEach(i => add.append(el("option", { value: i, textContent: keyName("key", i, null) })));
    add.onchange = () => { if (add.value) { navBinds()[add.value] = { tap: "home" }; commitNav(); } };
    host.append(el("div", { style: "margin-top:6px" }, [add]));
  }
}

// -- Settings panel --
function buildSettings(body) {
  const s = S.settings;
  const bri = el("input", { type: "range", min: 0, max: 100, value: s.device.brightness ?? 80 });
  const briV = el("span", { textContent: bri.value });
  bri.oninput = () => briV.textContent = bri.value;
  const hb = el("input", { type: "number", step: "0.5", min: "0.5", value: s.device.heartbeat_seconds });
  const grab = el("input", { type: "checkbox", checked: s.device.grab_keyboard });

  const homeProf = el("select");
  S.profiles.forEach(n => homeProf.append(el("option", { value: n, textContent: n, selected: n === s.home.profile })));
  const revert = el("input", { type: "number", step: "1", min: "0", value: s.home.revert_seconds });

  body.append(section("Device",
    fld("Brightness", el("span", {}, [bri, " ", briV])),
    fld("Heartbeat", hb, "write interval (s) that keeps the deck awake — don't set to 0"),
    fld("Grab keyboard", grab, "swallow the deck's built-in keyboard macros")));
  body.append(section("Switching",
    el("p", { class: "hint", textContent: "The home button (set in the Navigation panel) jumps to this profile from anywhere, then returns to auto-detect after the idle timeout." }),
    fld("Home profile", homeProf),
    fld("Return after", revert, "idle seconds before going back to auto-detect (0 = stay)")));
  body.append(section("Connection",
    el("p", { class: "hint", html: "API host / port / token: edit <code>settings.yaml</code> and restart the daemon." })));

  const save = el("button", { class: "primary", textContent: "Save settings" });
  save.onclick = async () => {
    s.device.brightness = Number(bri.value);
    s.device.heartbeat_seconds = Number(hb.value);
    s.device.grab_keyboard = grab.checked;
    s.home.profile = homeProf.value;
    s.home.revert_seconds = Number(revert.value);
    await saveSettings();
    renderChrome(); renderDeck(); closeDrawer();
  };
  body.append(el("div", { style: "margin-top:1rem" }, [save]));
}

// -- Import panel --
async function buildImport(body) {
  if (!Object.keys(GAMES).length) GAMES = await api("games").catch(() => ({}));
  const game = el("select");
  Object.keys(GAMES).forEach(k => game.append(el("option", { value: k, textContent: k.toUpperCase() })));
  const path = el("input", { type: "text", placeholder: "game install folder" });
  const pathHint = el("div", { class: "hint" });
  const over = el("input", { type: "checkbox", checked: true });
  const report = el("div", { class: "report", hidden: true });
  const syncPath = () => {
    const info = GAMES[game.value] || {};
    path.value = info.path || "";
    pathHint.textContent = info.path ? "auto-detected" : "not found — enter the game's install folder";
  };
  game.onchange = syncPath; syncPath();

  body.append(el("p", { class: "concept", html: "Labels the deck keys that are bound to the <b>D200x Button Box</b> controller inside <b>" + S.name + "</b> (the active profile)." }));
  body.append(fld("Game", game));
  body.append(fld("Path", path)); body.append(el("div", { class: "fld" }, [el("span"), pathHint]));
  body.append(fld("Overwrite", over, "replace labels you set by hand too"));
  body.append(report);

  const run = el("button", { class: "primary", textContent: "Import" });
  run.onclick = async () => {
    try {
      const rep = await api("profiles/" + S.name + "/import", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ game: game.value, path: path.value || undefined, overwrite: over.checked }) });
      const lines = [`labelled ${Object.keys(rep.applied).length} button(s)`];
      if (Object.keys(rep.skipped).length) lines.push(`\nkept your labels on: ${Object.entries(rep.skipped).map(([n, v]) => `btn ${n} (${v})`).join(", ")}`);
      if (Object.keys(rep.unmatched).length) lines.push(`\nbound in-game but not on any control:\n` + Object.entries(rep.unmatched).map(([n, v]) => `  btn ${n} = ${v}`).join("\n"));
      report.textContent = lines.join("\n"); report.hidden = false;
      await loadProfile(S.name);
    } catch (e) { report.textContent = "import failed: " + e; report.hidden = false; }
  };
  body.append(el("div", { style: "margin-top:1rem" }, [run]));
}

// ---- icon "style" editor (server-rendered preview) ----------
let IG = {};   // { onsave, base, target, glyph, label, frameless }
const IG_DEFAULTS = { mode: "solid", shape: "circle", fill: "#1b1f26", border: "#4a9eff", fg: "#ffffff", font: "sans" };
function igStyle() {
  return {
    mode: $("#ig_mode").value, shape: $("#ig_shape").value, font: $("#ig_font").value,
    border: $("#ig_border").value, fill: $("#ig_fill").value, fg: $("#ig_fg").value,
  };
}
function igPreview() {
  const q = new URLSearchParams(igStyle());
  if (IG.glyph) q.set("glyph", IG.glyph);
  else if (IG.label) q.set("label", IG.label);
  else q.set("text", $("#ig_text").value || (IG.target && IG.target.label) || "AB");
  $("#ig_prev").src = "api/icon-preview?" + q;
  const symbolish = !!(IG.glyph || IG.label);
  const ring = $("#ig_mode").value === "ring";
  // a tell-tale has no frame: only its colour applies
  for (const id of ["ig_mode_fld", "ig_shape_fld", "ig_border_fld", "ig_fill_fld", "ig_sync_fld"])
    $("#" + id).style.display = IG.frameless ? "none" : "";
  $("#ig_fill_fld").style.opacity = ring ? ".45" : "";
  $("#ig_fill").disabled = ring;
  $("#ig_font_fld").style.display = symbolish ? "none" : "";
  $("#ig_fg_lbl").textContent = symbolish ? "Icon colour" : "Icon / text";
}
// opts: { style, baseline, glyph, label, noText, note, saveLabel, clearLabel }
function openIconStyle(eff, onSave, title, opts = {}) {
  IG = {
    onsave: onSave, target: eff, glyph: opts.glyph || null, label: opts.label || null,
    base: Object.assign({}, IG_DEFAULTS, opts.baseline || {}),
    frameless: !!(opts.glyph && TELLTALE_SET.has(opts.glyph)),
  };
  const cur = opts.style || eff.icon_style || eff.style || eff || {};
  const s = Object.assign({}, IG.base, cur);
  $("#ig_title").textContent = title || "Icon style";
  $("#ig_note").textContent = opts.note || "";
  $("#ig_note").style.display = opts.note ? "" : "none";
  $("#ig_text_fld").style.display = (opts.noText || IG.glyph || IG.label) ? "none" : "";
  $("#ig_text").value = eff.icon_text || "";
  $("#ig_mode").value = s.mode; $("#ig_shape").value = s.shape; $("#ig_font").value = s.font;
  $("#ig_border").value = s.border; $("#ig_fill").value = s.fill; $("#ig_fg").value = s.fg;
  $("#ig_sync").checked = false;
  $("#ig_use").textContent = opts.saveLabel || "Use this icon";
  $("#ig_reset").textContent = opts.clearLabel || "Use page default";
  $("#ig_reset").style.display = opts.clearLabel === null ? "none" : "";
  igPreview();
  $("#iconGen").showModal();
}
function openPageStyle() {
  const pg = curPage();
  openIconStyle(pg.style || {}, style => {
    if (Object.keys(style).length) pg.style = style; else delete pg.style;
    renderDeck(); touched();
  }, "Default look — page " + (S.page + 1), {
    noText: true, baseline: IG_DEFAULTS, style: pg.style || {},
    saveLabel: "Apply", clearLabel: "Reset to app default",
    note: "The frame and colours every auto-generated icon on this page starts from. Any key can still override its own look. Dashboard symbols only take the icon colour.",
  });
}
["ig_text", "ig_mode", "ig_shape", "ig_font", "ig_border", "ig_fill", "ig_fg"].forEach(id => {
  $("#" + id).oninput = $("#" + id).onchange = () => {
    if ($("#ig_sync").checked && id === "ig_border") $("#ig_fg").value = $("#ig_border").value;
    igPreview();
  };
});
$("#ig_sync").onchange = () => { if ($("#ig_sync").checked) { $("#ig_fg").value = $("#ig_border").value; igPreview(); } };
$("#ig_reset").onclick = () => { IG.onsave({}, ""); $("#iconGen").close(); };
$("#ig_cancel").onclick = () => $("#iconGen").close();
$("#ig_use").onclick = () => {
  const st = igStyle(), out = {};
  const keys = IG.frameless ? ["fg"] : STYLE_KEYS;
  for (const k of keys) if (st[k] !== undefined && st[k] !== IG.base[k]) out[k] = st[k];
  IG.onsave(out, $("#ig_text").value.trim());
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
  for (const b of (GLYPHS.telltales || [])) bsel.append(el("option", { value: b, textContent: b }));
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
$("#settingsBtn").onclick = () => openDrawer("settings");
$("#profilesBtn").onclick = () => openDrawer("profiles");
$("#iconsBtn").onclick = () => openCompose();
$("#listenBtn").onclick = () => {
  S.listening = !S.listening;
  $("#listenBtn").classList.toggle("on", S.listening);
  $("#listenBtn").textContent = S.listening ? "Listening…" : "Listen";
};
$("#profileSel").onchange = async e => {
  await api("activate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ profile: e.target.value }) });
  await loadProfile(e.target.value);
};

// deck order for arrow-key navigation
const DECK_ORDER = [...KEY_ROWS.flat(), AUX_L, AUX_R, ...KNOBS];
document.addEventListener("keydown", e => {
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) { e.preventDefault(); undo(); return; }
  if (typing || $("#drawer").classList.contains("open") || document.querySelector("dialog[open]")) return;
  if (!S.sel) return;
  const flat = DECK_ORDER;
  const cur = flat.indexOf(S.sel.index);
  if (cur < 0) return;
  let next = cur;
  if (e.key === "ArrowRight" || e.key === "ArrowDown") next = Math.min(flat.length - 1, cur + 1);
  else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = Math.max(0, cur - 1);
  else if (e.key === "Escape") { S.sel = null; renderDeck(); renderEditor(); return; }
  else return;
  e.preventDefault();
  const id = flat[next];
  selectControl(KNOBS.includes(id) ? "knob" : "key", id);
});
window.onbeforeunload = e => { if (S.dirty) { save(); } };

boot().catch(e => {
  console.error(e);
  $("#editor").innerHTML = '<p class="emptyhint">Cannot reach the daemon API. Is <code>d200x-buttonboxd</code> running?</p>';
});
