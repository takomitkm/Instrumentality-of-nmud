/* app.js -- the page wiring.
 *
 * Loads the dictionary and the fitted model, then renders whatever is in
 * the input box. Everything runs in the browser: no server, no API.
 */
(function () {
  "use strict";

  var inBox = document.getElementById("in");
  var outBox = document.getElementById("out");
  var goBtn = document.getElementById("go");
  var sampleBtn = document.getElementById("sample");
  var copyBtn = document.getElementById("copy");
  var status = document.getElementById("status");

  var model = null;

  var SAMPLE = [
    "今天买了个新玩具，蓝色的，会发光，匀速的shake shake。",
    "6月26日是国际禁毒日，大家不要乱丢东西，被举报了说是nmud带坏小朋友，其实nmud什么都没有做。",
    "明天打算早点睡，反正也没什么人看，nmud还是想试试那个新语法。"
  ];

  function say(msg) { status.textContent = msg; }

  function gunzip(buffer) {
    // The dictionary ships gzipped: 1.7 MB instead of 4.0 MB.
    if (typeof DecompressionStream === "undefined") {
      return Promise.reject(new Error("这个浏览器不支持 DecompressionStream"));
    }
    var stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Response(stream).text();
  }

  function loadModel() {
    return fetch("nmud_style/data/nmud_style_params.json")
      .then(function (r) {
        if (!r.ok) { throw new Error("参数文件读不到（HTTP " + r.status + "）"); }
        return r.json();
      })
      .then(function (blob) {
        model = {
          params: blob.params,
          openers: new Set(Array.from(blob.openers)),
          closers: new Set(Array.from(blob.closers)),
          soft: blob.soft,
          maxUnits: blob.max_units
        };
      });
  }

  function loadDict() {
    return fetch("web/dict.txt.gz")
      .then(function (r) {
        if (!r.ok) { throw new Error("词典读不到（HTTP " + r.status + "）"); }
        return r.arrayBuffer();
      })
      .then(gunzip)
      .then(function (text) {
        var info = window.NmudSeg.loadDict(text);
        return info;
      });
  }

  function generate() {
    var text = inBox.value;
    if (!text.trim()) {
      outBox.value = "";
      say("输入框是空的。");
      return;
    }
    var t0 = performance.now();
    var styled = window.NmudStyle.styleText(
      text, model.params, model.openers, model.closers,
      model.soft, model.maxUnits, true);
    outBox.value = styled;
    var ms = Math.round(performance.now() - t0);
    say("排好了，用时 " + ms + " 毫秒。");
  }

  goBtn.addEventListener("click", function () {
    try {
      generate();
    } catch (e) {
      say("出错了：" + e.message);
    }
  });

  sampleBtn.addEventListener("click", function () {
    inBox.value = SAMPLE.join("\n");
    say("例子填好了，按“生成”。");
  });

  copyBtn.addEventListener("click", function () {
    if (!outBox.value) { say("还没有结果可复制。"); return; }
    outBox.select();
    try {
      document.execCommand("copy");
      say("复制好了。");
    } catch (e) {
      say("复制失败，手动选一下吧。");
    }
  });

  inBox.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      goBtn.click();
    }
  });

  say("正在下载分词词典（约 1.7 MB）…");
  Promise.all([loadDict(), loadModel()])
    .then(function (res) {
      goBtn.disabled = false;
      say("好了，词典 " + res[0].words + " 词。贴中文，按“生成”。");
    })
    .catch(function (e) {
      say("没能准备好：" + e.message);
    });
})();
