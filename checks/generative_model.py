"""A generative model of the author's spacing, fitted and tested out-of-sample.

The descriptive findings are solid: the author's whitespace falls on a word
boundary 95-98% of the time (four independent segmenters, each verified to
reproduce the input exactly), against a 55% random baseline.

This script asks the harder question: can a RULE generate the segmentation?

Model
  Walk the segmenter's word list left to right and cut the text into units.
  A unit must be between MIN_LEN and MAX_LEN characters (hard constraint).
  Cutting earns:
    +w_func    the next word starts with a character the author often starts
               a unit with (a function word / pronoun / demonstrative), or the
               author's own name token
    +w_content the unit ends with a content word rather than a function word
  The segmentation with the highest total score is chosen by dynamic
  programming.

  The opener character set is DERIVED FROM THE DATA, but only from the
  training half, so the held-out half is a genuine test.

Honesty guard
  The grid search rejects all-zero weights (they would let the DP fall back to
  an arbitrary tie-breaking segmentation) and always reports the baseline
  "cut at every segmenter boundary" next to the model, so the model's value
  is visible rather than asserted.
"""
import json
from collections import Counter

import jieba

import nlp_paths

jieba.setLogLevel(60)

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
OUT = (nlp_paths.arg("--out")
       or nlp_paths.locate_out("result file", "generative_model.json", "out"))

WS = (" ", "\u2009")
NAME = "nmud"

raw = open(CORPUS, "rb").read()
text = raw.decode("utf-8")
phys = text.replace("\r\n", "\n").split("\n")
if phys and phys[-1] == "":
    phys = phys[:-1]

paragraphs = []
cur = []
for l in phys:
    if l.strip():
        cur.append(l)
    else:
        if cur:
            paragraphs.append(cur); cur = []
if cur:
    paragraphs.append(cur)


def para_data(lines):
    stream = []
    ws_cuts = set()
    units = []
    for l in lines:
        seg = None
        for ch in l:
            if ch in WS:
                if seg is not None:
                    units.append((seg, len(stream)))
                    ws_cuts.add(len(stream)); seg = None
            else:
                if seg is None:
                    seg = len(stream)
                stream.append(ch)
        if seg is not None:
            units.append((seg, len(stream)))
    s = "".join(stream)
    spans = []
    acc = 0
    for w in jieba.cut(s):
        spans.append((acc, acc + len(w), w))
        acc += len(w)
    return {"stream": s, "ws_cuts": ws_cuts, "units": units, "spans": spans}


paras = [para_data(p) for p in paragraphs]

# Function words the author starts units with. Chosen from the linguistics,
# not fitted.
FUNC_CHARS = set("的不也很也就这有没好只什没那说要真又点太还为然到在会里样次个么了是被把从跟给让向对用吧呢啊吗嘛呀哦嗯们你我他她它谁其此该并却则所因如若且或虽即亦")


def derive_openers(train_paras, min_count=3, min_lift=2.0):
    """Characters that unusually often START a unit, measured on the
    training paragraphs only."""
    hits = Counter()
    tot = Counter()
    for p in train_paras:
        s = p["stream"]
        for i in range(1, len(s)):
            tot[s[i]] += 1
            if i in p["ws_cuts"]:
                hits[s[i]] += 1
    base = sum(hits.values()) / max(1, sum(tot.values()) - len(train_paras))
    out = set()
    stats = []
    for c, n in tot.items():
        if n < min_count:
            continue
        exp = n * base
        lift = hits[c] / exp if exp else 0
        stats.append((c, hits[c], n, round(lift, 2)))
        if lift >= min_lift and hits[c] >= 2:
            out.add(c)
    stats.sort(key=lambda t: -t[3])
    return out, stats


def dp_segment(para, openers, w_func, w_content, min_len, max_len):
    spans = para["spans"]
    n = len(spans)
    plen = [0] * (n + 1)
    for i, (a, b, w) in enumerate(spans):
        plen[i + 1] = plen[i] + len(w)
    NEG = float("-inf")
    best = [NEG] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for i in range(n):
        if best[i] == NEG:
            continue
        unit_start = plen[i]
        for j in range(i + 1, n + 1):
            ulen = plen[j] - unit_start
            if ulen > max_len:
                break
            if ulen < min_len and j < n:
                continue
            score = best[i]
            if j < n:
                last_w = spans[j - 1][2]
                next_w = spans[j][2]
                if next_w and (next_w[0] in openers or next_w == NAME):
                    score += w_func
                if last_w and last_w != NAME and not all(c in FUNC_CHARS for c in last_w):
                    score += w_content
            if score > best[j]:
                best[j] = score
                back[j] = i
    cuts = []
    j = n
    while j > 0:
        i = back[j]
        cuts.append(plen[i])
        j = i
    return set(cuts)


def evaluate(subset, openers, w_func, w_content, min_len, max_len):
    tp = pn = tn = 0
    for p in subset:
        c = dp_segment(p, openers, w_func, w_content, min_len, max_len)
        pn += len(c)
        tn += len(p["ws_cuts"])
        tp += len(c & p["ws_cuts"])
    pr = round(tp / pn, 4) if pn else 0
    rc = round(tp / tn, 4) if tn else 0
    f1 = round(2 * pr * rc / (pr + rc), 4) if (pr + rc) else 0
    return {"precision": pr, "recall": rc, "f1": f1, "tp": tp,
            "predicted": pn, "truth": tn}


def baseline(subset):
    """Cut at every jieba boundary: recall is maximal, precision is not."""
    tp = pn = tn = 0
    for p in subset:
        cuts = {a for (a, b, w) in p["spans"]}
        pn += len(cuts)
        tn += len(p["ws_cuts"])
        tp += len(cuts & p["ws_cuts"])
    pr = round(tp / pn, 4) if pn else 0
    rc = round(tp / tn, 4) if tn else 0
    f1 = round(2 * pr * rc / (pr + rc), 4) if (pr + rc) else 0
    return {"precision": pr, "recall": rc, "f1": f1, "tp": tp,
            "predicted": pn, "truth": tn}


def fit(train, openers, grid):
    best = None
    for w_func in grid["w_func"]:
        for w_content in grid["w_content"]:
            if w_func == 0 and w_content == 0:
                continue          # reject the degenerate all-zero model
            for min_len in grid["min_len"]:
                for max_len in grid["max_len"]:
                    if max_len < min_len:
                        continue
                    m = evaluate(train, openers, w_func, w_content, min_len, max_len)
                    key = (m["f1"], m["precision"])
                    if best is None or key > best[0]:
                        best = (key, {"w_func": w_func, "w_content": w_content,
                                       "min_len": min_len, "max_len": max_len}, m)
    return best


GRID = {"w_func": [0.5, 1.0, 2.0, 3.0, 4.0], "w_content": [0.0, 0.5, 1.0, 2.0],
        "min_len": [1, 2], "max_len": [3, 4, 5, 6]}

half = len(paras) // 2
folds = [("A", paras[:half], paras[half:]), ("B", paras[half:], paras[:half])]

R = {"n_paragraphs": len(paras), "split": "paragraph halves (out-of-sample)",
     "folds": {}}

for tag, train, test in folds:
    openers, stats = derive_openers(train)
    _, params, insample = fit(train, openers, GRID)
    test_scores = evaluate(test, openers, **params)
    R["folds"][tag] = {
        "train_paragraphs": len(train), "test_paragraphs": len(test),
        "n_openers_derived_from_train": len(openers),
        "openers": "".join(sorted(openers)),
        "top_opener_lift": stats[:12],
        "params": params,
        "in_sample": insample,
        "test": test_scores,
        "baseline_cut_every_jieba_boundary": {
            "train": baseline(train), "test": baseline(test)},
    }
    print(f"fold {tag}: openers={len(openers)} params={params}")
    print(f"   in-sample : {insample}")
    print(f"   TEST      : {test_scores}")
    print(f"   baseline(test, cut every jieba boundary): {baseline(test)}")

tp = sum(R["folds"][t]["test"]["tp"] for t, _, _ in folds)
pn = sum(R["folds"][t]["test"]["predicted"] for t, _, _ in folds)
tn = sum(R["folds"][t]["test"]["truth"] for t, _, _ in folds)
pr = round(tp / pn, 4); rc = round(tp / tn, 4)
R["pooled_out_of_sample"] = {"precision": pr, "recall": rc,
                             "f1": round(2 * pr * rc / (pr + rc), 4),
                             "tp": tp, "predicted": pn, "truth": tn}
print("POOLED OUT-OF-SAMPLE:", R["pooled_out_of_sample"])

# The baseline pooled the same way, for comparison
btp = sum(R["folds"][t]["baseline_cut_every_jieba_boundary"]["test"]["tp"] for t, _, _ in folds)
bpn = sum(R["folds"][t]["baseline_cut_every_jieba_boundary"]["test"]["predicted"] for t, _, _ in folds)
btn = sum(R["folds"][t]["baseline_cut_every_jieba_boundary"]["test"]["truth"] for t, _, _ in folds)
bpr = round(btp / bpn, 4); brc = round(btp / btn, 4)
R["pooled_out_of_sample_baseline"] = {"precision": bpr, "recall": brc,
                                      "f1": round(2 * bpr * brc / (bpr + brc), 4),
                                      "tp": btp, "predicted": bpn, "truth": btn}
print("POOLED BASELINE     :", R["pooled_out_of_sample_baseline"])

# A worked example with the fold A parameters
pa = R["folds"]["A"]
openers_a, _ = derive_openers(paras[:half])
p0 = paras[0]
c0 = dp_segment(p0, openers_a, **pa["params"])


def units_from_cuts(para, cuts):
    out = []
    prev = 0
    for c in sorted(cuts) + [len(para["stream"])]:
        out.append((prev, c))
        prev = c
    return out


R["example_paragraph_1"] = {
    "author_lines": paragraphs[0],
    "author_units": [p0["stream"][a:b] for (a, b) in p0["units"]],
    "model_units": [p0["stream"][a:b] for (a, b) in units_from_cuts(p0, c0)],
}
print("example paragraph 1")
print("  author:", R["example_paragraph_1"]["author_units"])
print("  model :", R["example_paragraph_1"]["model_units"])

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1)
print("wrote", OUT)
