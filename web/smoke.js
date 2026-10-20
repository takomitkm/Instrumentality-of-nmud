/* Smoke test for the page wiring: stub the DOM, load app.js, press the
 * button, and see whether the output box gets nmud text. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const zlib = require("zlib");

const ROOT = path.join(__dirname, "..");

function makeEl(id) {
  return {
    id, value: "", textContent: "", disabled: false,
    handlers: {},
    addEventListener(name, fn) { (this.handlers[name] = this.handlers[name] || []).push(fn); },
    select() {},
    click() { (this.handlers.click || []).forEach((f) => f()); }
  };
}

const els = {};
["in", "out", "go", "sample", "copy", "status"].forEach((id) => { els[id] = makeEl(id); });

const dictText = zlib.gunzipSync(
  fs.readFileSync(path.join(ROOT, "web", "dict.txt.gz"))).toString("utf8");

const sandbox = {
  console,
  performance: { now: () => Date.now() },
  Blob, Response, DecompressionStream,
  document: {
    getElementById: (id) => els[id],
    execCommand: () => true
  },
  fetch: async (url) => {
    if (String(url).endsWith("dict.txt.gz")) {
      return { ok: true, arrayBuffer: async () => fs.readFileSync(path.join(ROOT, "web", "dict.txt.gz")) };
    }
    if (String(url).endsWith("nmud_style_params.json")) {
      return { ok: true, json: async () => JSON.parse(
        fs.readFileSync(path.join(ROOT, "nmud_style", "data", "nmud_style_params.json"), "utf8")) };
    }
    return { ok: false, status: 404 };
  }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

for (const f of ["web/seg.js", "web/style.js", "web/app.js"]) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, f), "utf8"), sandbox, { filename: f });
}

(async () => {
  await new Promise((r) => setTimeout(r, 300));
  console.log("status after load :", els.status.textContent);
  console.log("button enabled    :", !els.go.disabled);

  els.in.value = "今天买了个新玩具，蓝色的，会发光。\n\n明天打算早点睡，反正也没什么人看。";
  els.go.click();
  console.log("status after click:", els.status.textContent);
  console.log("--- output ---");
  console.log(els.out.value);
  console.log("--- end ---");
  console.log("output non-empty  :", els.out.value.trim().length > 0);
})();
