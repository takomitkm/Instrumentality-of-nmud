/* check.js -- measure the browser build against the author's own cuts.
 *
 *   node web/check.js [corpus.txt] [params.json] [--units <file>]
 *
 * The yardstick is the one the report uses: for every paragraph, the
 * character offsets where the generator starts a unit, compared with the
 * offsets where the author started one. The score is a unit level F1.
 *
 * The browser build is measured with the shipped parameters, so the
 * number can be compared with checks/eval_shipped.py, which measures the
 * Python generator the same way.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const zlib = require("zlib");

const ROOT = path.join(__dirname, "..");
const sandbox = { console };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
for (const f of ["web/seg.js", "web/style.js"]) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, f), "utf8"), sandbox, { filename: f });
}

let corpusPath = path.join(ROOT, "nmud_style", "data", "nmud.txt");
let paramsPath = path.join(ROOT, "nmud_style", "data", "nmud_style_params.json");
let unitsOut = "";
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--units" && args[i + 1]) { unitsOut = args[++i]; }
  else if (!args[i].startsWith("--")) {
    if (i === 0) { corpusPath = args[0]; } else { paramsPath = args[1]; }
  }
}

const dictText = zlib.gunzipSync(
  fs.readFileSync(path.join(ROOT, "web", "dict.txt.gz"))).toString("utf8");
const dictInfo = sandbox.NmudSeg.loadDict(dictText);

const model = JSON.parse(fs.readFileSync(paramsPath, "utf8"));
const params = model.params;
const openers = new Set(model.openers);
const closers = new Set(model.closers);
const lbParams = model.line_break ? model.line_break.params : null;

const raw = fs.readFileSync(corpusPath, "utf8").replace(/\r\n/g, "\n");

// The paragraphs, as the line arrays the engine works on.
const paras = [];
let cur = [];
for (const line of raw.split("\n")) {
  if (line.trim()) { cur.push(line); }
  else if (cur.length) { paras.push(cur); cur = []; }
}
if (cur.length) { paras.push(cur); }

let tp = 0, pn = 0, tn = 0;
const unitLines = [];
const lbCases = [];   // the author's own units and break positions
for (const lines of paras) {
  // The author's own units: the stream without the whitespace, and the
  // offsets where each unit starts.
  let stream = "";
  const truth = [];
  const lbUnits = [];
  for (const l of lines) {
    let seg = null;
    for (const ch of l) {
      if (ch === " " || ch === " ") {
        if (seg !== null) { truth.push(seg); lbUnits.push(stream.slice(seg)); seg = null; }
      } else {
        if (seg === null) { seg = stream.length; }
        stream += ch;
      }
    }
    if (seg !== null) { truth.push(seg); lbUnits.push(stream.slice(seg)); }
  }
  // The author breaks between the last unit of a line and the first unit
  // of the next one, so the break index is the running count of the
  // units minus one.
  const lbWant = new Set();
  {
    let n = 0;
    for (let i = 0; i < lines.length; i++) {
      const c = lines[i].split(/[  ]+/).filter((x) => x).length;
      if (i < lines.length - 1) { lbWant.add(n + c - 1); }
      n += c;
    }
    if (lbUnits.length > 1) { lbCases.push({ units: lbUnits, want: lbWant }); }
  }

  const words = sandbox.NmudStyle.wordsAndSegs(stream);
  const spans = sandbox.NmudStyle.dpSegment(words, openers, closers, params);
  const pred = new Set(spans.map((s) => s[0]));
  const truthSet = new Set(truth);
  pn += pred.size;
  tn += truthSet.size;
  for (const p of pred) { if (truthSet.has(p)) { tp++; } }
  for (const s of spans) { unitLines.push(stream.slice(s[0], s[1])); }
}

const precision = pn ? tp / pn : 0;
const recall = tn ? tp / tn : 0;
const f1 = (precision + recall) ? 2 * precision * recall / (precision + recall) : 0;

console.log("dictionary words :", dictInfo.words);
console.log("paragraphs       :", paras.length);
console.log("precision        :", precision.toFixed(4));
console.log("recall           :", recall.toFixed(4));
console.log("f1               :", f1.toFixed(4));
console.log("tp/pred/truth    :", tp, "/", pn, "/", tn);

// ------------------------------------------------------------------
// the line break model, measured the same way as the Python build
// ------------------------------------------------------------------
if (lbParams) {
  let ltp = 0, lpn = 0, ltn = 0, exact = 0;
  for (const c of lbCases) {
    const units = c.units.map((u) => [u, " "]);
    const lines = sandbox.NmudStyle.wrapDp(units, openers, closers, lbParams);
    const got = new Set();
    let acc = 0;
    for (const ln of lines.slice(0, -1)) { acc += ln.length; got.add(acc - 1); }
    lpn += got.size;
    ltn += c.want.size;
    for (const g of got) { if (c.want.has(g)) { ltp++; } }
    if (got.size === c.want.size && [...got].every((g) => c.want.has(g))) { exact++; }
  }
  const lp = lpn ? ltp / lpn : 0;
  const lr = ltn ? ltp / ltn : 0;
  const lf = (lp + lr) ? 2 * lp * lr / (lp + lr) : 0;
  console.log("");
  console.log("line break precision :", lp.toFixed(4));
  console.log("line break recall    :", lr.toFixed(4));
  console.log("line break f1        :", lf.toFixed(4));
  console.log("line break tp/pred/truth :", ltp, "/", lpn, "/", ltn);
  console.log("paragraphs exact     :", exact, "/", lbCases.length);
}

if (unitsOut) {
  fs.writeFileSync(unitsOut, unitLines.join("\n") + "\n", "utf8");
  console.log("units written    :", unitsOut);
}
