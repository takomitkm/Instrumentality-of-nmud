/* style.js -- the nmud style rules in the browser.
 *
 * A port of the rendering half of nmud_style/engine.py: the punctuation
 * rules, the dynamic program that cuts the word list into units, and the
 * line wrapper. The measured parameters (the weights, the opener and
 * closer characters, the wrap widths) come from the fitted model in
 * nmud_style/data/nmud_style_params.json, the same file the Python
 * generator uses.
 *
 * The part of speech is not read here. Both part-of-speech weights in the
 * shipped model are zero, so the tag never changes a decision; a model
 * refitted with a non-zero part-of-speech weight would need the tags and
 * therefore the Python generator.
 */
(function (global) {
  "use strict";

  var WS = [" ", " "];
  var THIN = " ";

  // The marks the author uses, and the ones he never uses.
  var AUTHOR_PUNCT = "…？！“”";
  var FRONT_PUNCT = "“（【《〈「『";
  var CJK_PUNCT = new Set(
    "。，、；：（）【】《》〈〉「」『』·—～‘’“”…？！　".split("")
  );
  var ASCII_PUNCT = new Set(
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~".split("")
  );
  var PUNCT_ALL = new Set([].concat(Array.from(CJK_PUNCT), Array.from(ASCII_PUNCT)));
  var DE = "的";

  function isAscii(ch) { return ch.charCodeAt(0) < 128; }
  function isAlnum(ch) { return /[0-9A-Za-z]/.test(ch); }

  function scriptClass(ch) {
    // WEST for an ASCII letter, digit or ASCII punctuation, CJK for the rest.
    if (isAscii(ch) && !/\s/.test(ch)) { return "WEST"; }
    return "CJK";
  }

  function splitMixedWord(word) {
    // The author never lets a unit mix Chinese with latin or digits.
    if (!word) { return [word]; }
    var parts = [];
    var cur = "";
    var prev = null;
    for (var i = 0; i < word.length; i++) {
      var ch = word[i];
      var c = scriptClass(ch);
      if (prev !== null && c !== prev) { parts.push(cur); cur = ""; }
      cur += ch;
      prev = c;
    }
    parts.push(cur);
    return parts;
  }

  function isPunctOnly(w) {
    if (!w) { return false; }
    for (var i = 0; i < w.length; i++) {
      if (!PUNCT_ALL.has(w[i])) { return false; }
    }
    return true;
  }

  function stripUnusedPunct(text) {
    // A mark the author never uses becomes a space, not a hole: the mark
    // stood for a boundary the writer chose.
    var out = "";
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      out += (CJK_PUNCT.has(ch) && AUTHOR_PUNCT.indexOf(ch) < 0) ? " " : ch;
    }
    return out;
  }

  function mergePunct(ws) {
    // Fold the marks onto the word they belong to. An opening mark goes
    // in front of the word after it, everything else behind the word
    // before it.
    var out = [];
    var pending = "";
    for (var i = 0; i < ws.length; i++) {
      var w = ws[i];
      if (!isPunctOnly(w)) {
        if (pending) { w = pending + w; pending = ""; }
        out.push(w);
        continue;
      }
      if (FRONT_PUNCT.indexOf(w[0]) >= 0 ||
          (w[0] === "…" && !out.length && !pending)) {
        pending += w;
      } else if (out.length) {
        out[out.length - 1] += w;
      } else {
        pending += w;
      }
    }
    if (pending) {
      if (out.length) { out[out.length - 1] += pending; }
      else { out.push(pending); }
    }
    return out;
  }

  function wordsAndSegs(stream) {
    var raw = global.NmudSeg.cut(stream);
    var parts = [];
    for (var i = 0; i < raw.length; i++) {
      var split = splitMixedWord(raw[i]);
      for (var k = 0; k < split.length; k++) { parts.push(split[k]); }
    }
    // jieba hands a trailing ASCII symbol to its own token ("90.8%" ->
    // "90.8" + "%"). The author treats a foreign token as one atom, so a
    // bare ASCII symbol goes back onto the western token it belongs to.
    var merged = [];
    for (var j = 0; j < parts.length; j++) {
      var w = parts[j];
      var bare = w.length > 0;
      for (var c = 0; c < w.length; c++) {
        if (!isAscii(w[c]) || isAlnum(w[c])) { bare = false; break; }
      }
      if (merged.length && bare) {
        var prev = merged[merged.length - 1];
        if (prev.length && isAscii(prev[prev.length - 1])) {
          merged[merged.length - 1] = prev + w;
          continue;
        }
      }
      merged.push(w);
    }
    return mergePunct(merged);
  }

  function dpSegment(words, openers, closers, p) {
    // Cut a word list into units under a character length band. A word
    // longer than the band becomes its own unit.
    var n = words.length;
    if (n === 0) { return []; }
    var plen = new Array(n + 1);
    plen[0] = 0;
    for (var i = 0; i < n; i++) { plen[i + 1] = plen[i] + words[i].length; }
    var wcls = [];
    for (var w = 0; w < words.length; w++) {
      var c = "WEST";
      for (var k = 0; k < words[w].length; k++) {
        if (scriptClass(words[w][k]) !== "WEST") { c = "CJK"; break; }
      }
      wcls.push(c);
    }

    function solve(ml) {
      var NEG = -Infinity;
      var best = new Array(n + 1);
      var back = new Array(n + 1);
      for (var q = 0; q <= n; q++) { best[q] = NEG; back[q] = 0; }
      best[0] = 0.0;
      for (var a = 0; a < n; a++) {
        if (best[a] === NEG) { continue; }
        for (var b = a + 1; b <= n; b++) {
          var ulen = plen[b] - plen[a];
          if (ulen > p.max_len) {
            if (b === a + 1 && best[b] < best[a]) {
              best[b] = best[a];
              back[b] = a;
            }
            break;
          }
          if (ulen < ml && b < n) { continue; }
          var sc = best[a];
          if (b < n) {
            var nxt = words[b];
            var prv = words[b - 1];
            if (openers.has(nxt[0])) { sc += p.w_open; }
            if (closers.has(prv[prv.length - 1])) { sc += p.w_close; }
            if (nxt[0] === DE) { sc += p.w_de_next; }
            if (prv[prv.length - 1] === DE) { sc += p.w_de_prev; }
          }
          if (sc > best[b]) { best[b] = sc; back[b] = a; }
        }
      }
      return { best: best, back: back };
    }

    var sol = solve(p.min_len);
    if (sol.best[n] === -Infinity && p.min_len > 1) {
      // No path under the fitted band: allow the one character units the
      // corpus also contains instead of falling back to word level output.
      sol = solve(1);
    }
    if (sol.best[n] === -Infinity) {
      var flat = [];
      for (var z = 0; z < n; z++) { flat.push([plen[z], plen[z + 1]]); }
      return flat;
    }
    var ranges = [];
    var j = n;
    while (j > 0) {
      var i2 = sol.back[j];
      ranges.push([i2, j]);
      j = i2;
    }
    ranges.reverse();
    var out = [];
    for (var r = 0; r < ranges.length; r++) {
      var start = ranges[r][0];
      for (var k2 = ranges[r][0] + 1; k2 < ranges[r][1]; k2++) {
        if (wcls[k2] !== wcls[k2 - 1]) {
          out.push([plen[start], plen[k2]]);
          start = k2;
        }
      }
      out.push([plen[start], plen[ranges[r][1]]]);
    }
    return out;
  }

  function splitChunks(text) {
    // The whitespace in the input is the writer's own decision and stays
    // as it is: an ordinary space stays ordinary, a thin space stays thin.
    var chunks = [];
    var sep = "";
    var parts = text.split(/([ \t\r\n ]+)/);
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      if (!p) { continue; }
      if (/^[ \t\r\n ]+$/.test(p)) {
        sep = p.indexOf(" ") >= 0 ? THIN : " ";
      } else {
        chunks.push([p, sep]);
        sep = "";
      }
    }
    return chunks;
  }

  function joinUnits(units) {
    var out = "";
    for (var i = 0; i < units.length; i++) {
      var u = units[i];
      var text = u[0];
      var sep = u[1];
      if (out.length && sep) { out += sep; }
      out += text;
    }
    return out;
  }

  function displayWidth(s) {
    var w = 0;
    for (var i = 0; i < s.length; i++) { w += isWide(s[i]) ? 2 : 1; }
    return w;
  }

  function isWide(ch) {
    var c = ch.codePointAt(0);
    return (c >= 0x1100 && c <= 0x115f) ||
           (c >= 0x2e80 && c <= 0x303e) ||
           (c >= 0x3041 && c <= 0x33ff) ||
           (c >= 0x3400 && c <= 0x4dbf) ||
           (c >= 0x4e00 && c <= 0x9fff) ||
           (c >= 0xa000 && c <= 0xa4cf) ||
           (c >= 0xac00 && c <= 0xd7a3) ||
           (c >= 0xf900 && c <= 0xfaff) ||
           (c >= 0xfe10 && c <= 0xfe19) ||
           (c >= 0xfe30 && c <= 0xfe6f) ||
           (c >= 0xff00 && c <= 0xff60) ||
           (c >= 0xffe0 && c <= 0xffe6) ||
           (c >= 0x1f300 && c <= 0x1f64f) ||
           (c >= 0x20000 && c <= 0x3fffd);
  }

  function wrap(units, soft, maxUnits, minUnits) {
    var lines = [];
    var cur = [];
    var curW = 0;
    for (var i = 0; i < units.length; i++) {
      var u = units[i];
      var uw = displayWidth(u[0]);
      if (cur.length && (cur.length >= maxUnits ||
          (curW + uw > soft && cur.length >= minUnits))) {
        lines.push(cur);
        cur = [];
        curW = 0;
      }
      cur.push(u);
      curW += uw + 1;
    }
    if (cur.length) { lines.push(cur); }
    return lines;
  }

  function glueLeftoverPunct(units) {
    // A mark that is still a unit of its own is glued to a word.
    var out = [];
    var pending = "";
    for (var i = 0; i < units.length; i++) {
      var u = units[i];
      var text = u[0];
      var onlyAuthor = text.length > 0;
      for (var c = 0; c < text.length; c++) {
        if (AUTHOR_PUNCT.indexOf(text[c]) < 0) { onlyAuthor = false; break; }
      }
      if (onlyAuthor && isPunctOnly(text)) {
        if (out.length && !pending) {
          out[out.length - 1][0] += text;
        } else {
          pending += text;
        }
        continue;
      }
      if (pending) { text = pending + text; pending = ""; }
      out.push([text, u[1]]);
    }
    if (pending) {
      if (out.length) { out[out.length - 1][0] += pending; }
      else { out.push([pending, " "]); }
    }
    return out;
  }

  function render(plain, p, openers, closers, soft, maxUnits, dropPunct) {
    var units = [];
    var chunks = splitChunks(dropPunct ? stripUnusedPunct(plain) : plain);
    for (var c = 0; c < chunks.length; c++) {
      var text = chunks[c][0];
      var sep = chunks[c][1];
      if (!text) { continue; }
      var ws = wordsAndSegs(text);
      var spans = dpSegment(ws, openers, closers, p);
      for (var k = 0; k < spans.length; k++) {
        units.push([text.slice(spans[k][0], spans[k][1]), k === 0 ? sep : " "]);
      }
    }
    units = glueLeftoverPunct(units);
    var lines = wrap(units, soft, maxUnits, 2);
    var bodies = [];
    for (var l = 0; l < lines.length; l++) { bodies.push(joinUnits(lines[l])); }
    return { text: bodies.join("\n"), units: units, lines: lines };
  }

  function styleText(raw, p, openers, closers, soft, maxUnits, dropPunct) {
    // Blank lines separate the paragraphs; a line break inside a
    // paragraph is a boundary the writer chose, so the lines are joined
    // with a space.
    var paras = [];
    var cur = [];
    var lines = raw.replace(/\r\n/g, "\n").split("\n");
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim()) {
        cur.push(lines[i]);
      } else {
        if (cur.length) { paras.push(cur); cur = []; }
      }
    }
    if (cur.length) { paras.push(cur); }
    var blocks = [];
    for (var q = 0; q < paras.length; q++) {
      var body = paras[q].map(function (l) { return l.replace(/\s+$/, ""); }).join(" ");
      blocks.push(render(body, p, openers, closers,
                         soft, maxUnits, dropPunct).text);
    }
    return blocks.join("\n\n") + "\n";
  }

  global.NmudStyle = {
    render: render,
    styleText: styleText,
    stripUnusedPunct: stripUnusedPunct,
    scriptClass: scriptClass,
    wordsAndSegs: wordsAndSegs,
    dpSegment: dpSegment,
    displayWidth: displayWidth
  };
})(typeof window !== "undefined" ? window : globalThis);
