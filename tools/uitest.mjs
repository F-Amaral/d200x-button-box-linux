// Headless smoke test for the web UI. Node 21+ (global WebSocket), no deps.
//
//   d200x-buttonboxd &                       # daemon + API on :8377
//   node tools/uitest.mjs <chrome> [url] [shot.png] ["<js probe expr>"]
//
// Launches Chrome via the DevTools Protocol, loads the page, runs the probe
// expression (async is awaited), prints its value + any console/runtime errors,
// and writes a screenshot. Exit 3 if the page logged an error.
//
// A Chrome-for-Testing binary lives under ./chrome/ (gitignored); pass its path:
//   node tools/uitest.mjs chrome/linux-*/chrome-linux64/chrome

import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = process.argv[2];
const URL = process.argv[3] || "http://localhost:8377/";
const SHOT = process.argv[4] || "/tmp/d200x-ui.png";
const PROBE = process.argv[5] ||
  "({cells: document.querySelectorAll('.cell').length, " +
  "editor: document.querySelector('#editor')?.innerText?.slice(0,120), " +
  "profiles: document.querySelector('#profileSel')?.length, " +
  "tabs: document.querySelector('#tabs')?.children.length})";

if (!CHROME) { console.error("usage: node tools/uitest.mjs <chrome-binary> [url] [shot] [probe]"); process.exit(1); }

const udd = mkdtempSync(join(tmpdir(), "uitest-"));
const chrome = spawn(CHROME, [
  "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
  `--user-data-dir=${udd}`, "--remote-debugging-port=9333",
  "--window-size=1400,950", "about:blank",
], { stdio: ["ignore", "ignore", "ignore"] });

const die = (msg, code = 1) => { console.error(msg); chrome.kill("SIGKILL"); process.exit(code); };
setTimeout(() => die("timeout", 2), 30000);

let wsUrl;
for (let i = 0; i < 50 && !wsUrl; i++) {
  try { wsUrl = (await (await fetch("http://localhost:9333/json/version")).json()).webSocketDebuggerUrl; }
  catch { await new Promise(r => setTimeout(r, 200)); }
}
if (!wsUrl) die("no devtools endpoint");

const ws = new WebSocket(wsUrl);
let id = 0;
const pending = new Map();
const errors = [];
const send = (method, params = {}, sessionId) =>
  new Promise((res, rej) => { const m = ++id; pending.set(m, { res, rej });
    ws.send(JSON.stringify({ id: m, method, params, sessionId })); });

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.id && pending.has(msg.id)) {
    const { res, rej } = pending.get(msg.id); pending.delete(msg.id);
    msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
  }
  if (msg.method === "Runtime.exceptionThrown")
    errors.push("EXCEPTION: " + (msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text));
  if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error")
    errors.push("console.error: " + msg.params.args.map(a => a.value ?? a.description).join(" "));
  if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error")
    errors.push("log: " + msg.params.entry.text);
};
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
const S = (m, p) => send(m, p, sessionId);

await S("Page.enable");
await S("Runtime.enable");
await S("Log.enable");
await S("Page.navigate", { url: URL });
await new Promise(r => setTimeout(r, 3500));  // SSE keeps the network busy; just wait

const probe = await S("Runtime.evaluate", { expression: PROBE, returnByValue: true, awaitPromise: true });
console.log("PROBE:", JSON.stringify(probe.result.value));
console.log("ERRORS:", errors.length ? "\n  " + errors.join("\n  ") : "none");

const shot = await S("Page.captureScreenshot", { format: "png" });
writeFileSync(SHOT, Buffer.from(shot.data, "base64"));
console.log("SHOT:", SHOT);

chrome.kill("SIGKILL");
process.exit(errors.length ? 3 : 0);
