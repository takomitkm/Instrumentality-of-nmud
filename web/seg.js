/* seg.js -- the segmenter for the browser build.
 *
 * A port of jieba 0.42.1's dictionary segmentation (the DAG + the route
 * maximisation in jieba/__init__.py), so that the browser cuts the text
 * at the same word boundaries the Python generator does.
 *
 * Two deliberate differences:
 *   - jieba's HMM (finalseg) is not here. It only ever runs on a run of
 *     single characters that the dictionary does not know, and those are
 *     yielded one by one instead.
 *   - the part of speech is not read. The fitted style weights for the
 *     part of speech are both zero, so the tag never changes a decision.
 *
 * The dictionary is jieba's dict.txt with the tag column dropped.
 */
(function (global) {
  "use strict";

  // The same class of characters jieba keeps together: CJK, latin,
  // digits and a handful of symbols that belong to a token.
  var RE_HAN_SPLIT = /([\u4E00-\u9FD5a-zA-Z0-9+#&._%\-]+)/;
  var RE_HAN_TEST = /^[\u4E00-\u9FD5a-zA-Z0-9+#&._%\-]+/;
  var RE_SKIP_SPLIT = /(\r\n|\s)/;
  var RE_SKIP_TEST = /^(\r\n|\s)$/;

  var FREQ = null;
  var TOTAL = 0;

  function loadDict(text) {
    FREQ = new Map();
    TOTAL = 0;
    var lines = text.split("\n");
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (!line) { continue; }
      var sp = line.lastIndexOf(" ");
      if (sp <= 0) { continue; }
      var word = line.slice(0, sp);
      var freq = parseInt(line.slice(sp + 1), 10);
      if (!word || !isFinite(freq)) { continue; }
      FREQ.set(word, freq);
      TOTAL += freq;
    }
    return { words: FREQ.size, total: TOTAL };
  }

  function getDAG(sentence) {
    var N = sentence.length;
    var DAG = new Array(N);
    for (var k = 0; k < N; k++) {
      var tmp = [];
      var i = k;
      var frag = sentence[k];
      while (i < N && FREQ.has(frag)) {
        if (FREQ.get(frag)) { tmp.push(i); }
        i++;
        frag = sentence.slice(k, i + 1);
      }
      if (!tmp.length) { tmp.push(k); }
      DAG[k] = tmp;
    }
    return DAG;
  }

  function calc(sentence, DAG) {
    var N = sentence.length;
    var route = new Array(N + 1);
    route[N] = [0, 0];
    var logtotal = Math.log(TOTAL);
    for (var idx = N - 1; idx >= 0; idx--) {
      var bestVal = -Infinity;
      var bestX = idx;
      var ends = DAG[idx];
      for (var t = 0; t < ends.length; t++) {
        var x = ends[t];
        var f = FREQ.get(sentence.slice(idx, x + 1)) || 1;
        var val = Math.log(f) - logtotal + route[x + 1][0];
        if (val > bestVal) { bestVal = val; bestX = x; }
      }
      route[idx] = [bestVal, bestX];
    }
    return route;
  }

  function cutBlock(sentence) {
    var DAG = getDAG(sentence);
    var route = calc(sentence, DAG);
    var out = [];
    var x = 0;
    var buf = "";
    var N = sentence.length;
    while (x < N) {
      var y = route[x][1] + 1;
      var lWord = sentence.slice(x, y);
      if (y - x === 1) {
        buf += lWord;
      } else {
        if (buf) {
          if (buf.length === 1) {
            out.push(buf);
          } else {
            // jieba would run its HMM over this run of single characters;
            // the dictionary build yields them one by one.
            for (var c = 0; c < buf.length; c++) { out.push(buf[c]); }
          }
          buf = "";
        }
        out.push(lWord);
      }
      x = y;
    }
    if (buf) {
      if (buf.length === 1) {
        out.push(buf);
      } else {
        for (var d = 0; d < buf.length; d++) { out.push(buf[d]); }
      }
    }
    return out;
  }

  function cut(sentence) {
    var out = [];
    var blocks = sentence.split(RE_HAN_SPLIT);
    for (var i = 0; i < blocks.length; i++) {
      var blk = blocks[i];
      if (!blk) { continue; }
      if (RE_HAN_TEST.test(blk)) {
        var words = cutBlock(blk);
        for (var w = 0; w < words.length; w++) { out.push(words[w]); }
      } else {
        var tmp = blk.split(RE_SKIP_SPLIT);
        for (var t = 0; t < tmp.length; t++) {
          var x = tmp[t];
          if (!x) { continue; }
          if (RE_SKIP_TEST.test(x)) {
            out.push(x);
          } else {
            for (var c = 0; c < x.length; c++) { out.push(x[c]); }
          }
        }
      }
    }
    return out;
  }

  global.NmudSeg = { loadDict: loadDict, cut: cut };
})(typeof window !== "undefined" ? window : globalThis);
