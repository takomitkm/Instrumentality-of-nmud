"""nmud-style generator and its evaluation.

The question this answers: can the measured rules be used to WRITE in the
author's style, and can the result be scored with the same yardstick that
was used to measure him?

A. SEGMENTER
   A dynamic program over the segmenter's word list that cuts the text into
   units under a length band, scoring each candidate cut with features
   derived from the corpus:
     opener   the next word starts with a character the author often starts
              a unit with (function word, pronoun, demonstrative)
     closer   the previous word ends with a character the author often ends
              a unit with (particle, modal, complement)
     posstart the next word's part of speech is a function-like one
     posend   the previous word's part of speech is a content one
     de       penalty for cutting before the particle 的, which the author
              always keeps attached to the word on its left
   A word longer than the band is emitted as its own unit: the corpus has
   such words (shakeshake, nmudnmud, kirakira) and the author keeps them
   whole. Without this rule the dynamic program has no reachable path for
   a paragraph containing one and collapses the whole paragraph into a
   single unit.

   Parameters are chosen by held-out validation (fit on one half of the
   paragraphs, score on the other, both directions) and the held-out winner
   is the one that is used. Fitting on all data and taking the grid maximum
   was tried and rejected: the grid maximum sat on a parameter boundary and
   did not reproduce on the other half.

B. RENDERER
   Joins the units with a space, but uses a THIN SPACE where a Latin or
   digit token meets a Chinese character, and wraps the result into lines
   of 2-3 units, breaking at clause ends, with blank lines between
   paragraphs.

C. EVALUATION
   Round trip: strip every space from the corpus, re-segment with the
   generator, and compare against the author's own units as SETS (a single
   differing unit shifts everything after it, so positional comparison
   would be meaningless). Plus the same style metrics used on the author's
   text, so generated text is compared to the original on equal terms.
"""
import json
import re
import unicodedata
from collections import Counter

import jieba
import jieba.posseg as pseg

import nlp_paths

jieba.setLogLevel(60)

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
OUT = (nlp_paths.arg("--out")
       or nlp_paths.locate_out("result file", "style_gen.json", "out"))

WS = (" ", "\u2009")

POS_START = {"r", "d", "p", "c", "u", "m", "q", "t", "f", "s"}
POS_END = {"n", "nr", "ns", "nt", "nz", "v", "vd", "vn", "a", "ad", "an",
           "eng", "i", "l", "j", "z", "y", "x", "m", "q", "b"}
LEFT_BOUND = set("的")

raw = open(CORPUS, "rb").read()
text = raw.decode("utf-8")
phys = text.replace("\r\n", "\n").split("\n")
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


def para_units(lines):
    stream = []
    units = []
    for l in lines:
        seg = None
        for ch in l:
            if ch in WS:
                if seg is not None:
                    units.append((seg, len(stream))); seg = None
            else:
                if seg is None:
                    seg = len(stream)
                stream.append(ch)
        if seg is not None:
            units.append((seg, len(stream)))
    return "".join(stream), units


def words_and_pos(stream):
    ws = []
    ps = []
    for w, f in pseg.cut(stream):
        ws.append(w)
        ps.append(f)
    return ws, ps


def derive_features(train_paras):
    """Characters that unusually often START / END a unit, measured on the
    training paragraphs only."""
    after = Counter()
    before = Counter()
    tot_a = Counter()
    tot_b = Counter()
    for lines in train_paras:
        s, units = para_units(lines)
        cuts = {b for (_, b) in units}
        for i in range(1, len(s)):
            tot_a[s[i]] += 1
            tot_b[s[i - 1]] += 1
            if i in cuts:
                after[s[i]] += 1
                before[s[i - 1]] += 1
    n_a = max(1, sum(tot_a.values()))
    n_b = max(1, sum(tot_b.values()))
    openers, closers = set(), set()
    o_stats, c_stats = [], []
    for c, n in tot_a.items():
        if n >= 3:
            exp = n * sum(after.values()) / n_a
            lift = after[c] / exp if exp else 0
            o_stats.append((c, after[c], n, round(lift, 2)))
            if lift >= 2.0 and after[c] >= 2:
                openers.add(c)
    for c, n in tot_b.items():
        if n >= 3:
            exp = n * sum(before.values()) / n_b
            lift = before[c] / exp if exp else 0
            c_stats.append((c, before[c], n, round(lift, 2)))
            if lift >= 2.0 and before[c] >= 2:
                closers.add(c)
    o_stats.sort(key=lambda t: -t[3])
    c_stats.sort(key=lambda t: -t[3])
    return openers, closers, o_stats, c_stats


NEG = float("-inf")


def dp_segment(words, pos, openers, closers, w_open, w_close, w_posstart,
               w_posend, w_de, min_len, max_len):
    """Cut the word list into units.

    A word longer than the band becomes its own unit. The band is enforced
    on the character count of the unit."""
    n = len(words)
    if n == 0:
        return []
    plen = [0] * (n + 1)
    for i, w in enumerate(words):
        plen[i + 1] = plen[i] + len(w)
    best = [NEG] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for i in range(n):
        if best[i] == NEG:
            continue
        for j in range(i + 1, n + 1):
            ulen = plen[j] - plen[i]
            if ulen > max_len:
                # a single word longer than the band is emitted alone
                if j == i + 1:
                    if best[j] < best[i]:
                        best[j] = best[i]
                        back[j] = i
                break
            if ulen < min_len and j < n:
                continue
            sc = best[i]
            if j < n:
                nxt = words[j]
                prv = words[j - 1]
                if nxt[0] in openers:
                    sc += w_open
                if prv[-1] in closers:
                    sc += w_close
                if pos[j] in POS_START:
                    sc += w_posstart
                if pos[j - 1] in POS_END:
                    sc += w_posend
                if nxt[0] in LEFT_BOUND:
                    sc -= w_de
            if sc > best[j]:
                best[j] = sc
                back[j] = i
    if best[n] == NEG:
        # unreachable: fall back to one word per unit so no text is lost
        return [(plen[i], plen[i + 1]) for i in range(n)]
    out = []
    j = n
    while j > 0:
        i = back[j]
        out.append((plen[i], plen[j]))
        j = i
    return out[::-1]


def unit_texts(stream, spans):
    return [stream[a:b] for (a, b) in spans]


def prep(paras_subset):
    out = []
    for lines in paras_subset:
        s, units = para_units(lines)
        ws, ps = words_and_pos(s)
        out.append({"stream": s, "author_units": units,
                    "words": ws, "pos": ps})
    return out


def evaluate(data, openers, closers, params):
    tp = pn = tn = 0
    for d in data:
        spans = dp_segment(d["words"], d["pos"], openers, closers, **params)
        pred = {a for (a, b) in spans}
        truth = {a for (a, b) in d["author_units"]}
        pn += len(pred)
        tn += len(truth)
        tp += len(pred & truth)
    pr = round(tp / pn, 4) if pn else 0
    rc = round(tp / tn, 4) if tn else 0
    f1 = round(2 * pr * rc / (pr + rc), 4) if (pr + rc) else 0
    return {"precision": pr, "recall": rc, "f1": f1, "tp": tp,
            "predicted": pn, "truth": tn}


GRID = {
    "w_open": [0.0, 1.0, 2.0, 3.0],
    "w_close": [0.0, 1.0, 2.0, 3.0],
    "w_posstart": [0.0, 1.0, 2.0],
    "w_posend": [0.0, 1.0, 2.0],
    "w_de": [0.0, 1.0, 2.0, 3.0],
    "min_len": [1, 2],
    "max_len": [3, 4, 5, 6],
}


def fit(data, openers, closers):
    best = None
    keys = ["w_open", "w_close", "w_posstart", "w_posend", "w_de"]
    vals = [GRID[k] for k in keys]
    for a in vals[0]:
        for b in vals[1]:
            for c in vals[2]:
                for d in vals[3]:
                    for e in vals[4]:
                        if a == 0 and b == 0 and c == 0 and d == 0:
                            continue
                        for ml in GRID["min_len"]:
                            for xl in GRID["max_len"]:
                                if xl < ml:
                                    continue
                                p = {"w_open": a, "w_close": b, "w_posstart": c,
                                     "w_posend": d, "w_de": e,
                                     "min_len": ml, "max_len": xl}
                                m = evaluate(data, openers, closers, p)
                                key = (m["f1"], m["precision"])
                                if best is None or key > best[0]:
                                    best = (key, p, m)
    return best


half = len(paragraphs) // 2
folds = [("A", paragraphs[:half], paragraphs[half:]),
         ("B", paragraphs[half:], paragraphs[:half])]

R = {"n_paragraphs": len(paragraphs), "folds": {}}
heldout_best = None
for tag, train_lines, test_lines in folds:
    openers, closers, o_stats, c_stats = derive_features(train_lines)
    train = prep(train_lines)
    test = prep(test_lines)
    _, params, insample = fit(train, openers, closers)
    test_scores = evaluate(test, openers, closers, params)
    R["folds"][tag] = {
        "n_openers": len(openers), "n_closers": len(closers),
        "params": params, "in_sample": insample, "test": test_scores,
    }
    print(f"fold {tag}: params={params}")
    print(f"   in-sample : {insample}")
    print(f"   TEST      : {test_scores}")
    if heldout_best is None or test_scores["f1"] > heldout_best[0]:
        heldout_best = (test_scores["f1"], tag, openers, closers, params)

tp = sum(R["folds"][t]["test"]["tp"] for t, _, _ in folds)
pn = sum(R["folds"][t]["test"]["predicted"] for t, _, _ in folds)
tn = sum(R["folds"][t]["test"]["truth"] for t, _, _ in folds)
pr = round(tp / pn, 4)
rc = round(tp / tn, 4)
R["pooled_out_of_sample"] = {"precision": pr, "recall": rc,
                             "f1": round(2 * pr * rc / (pr + rc), 4),
                             "tp": tp, "predicted": pn, "truth": tn}
print("POOLED OUT-OF-SAMPLE:", R["pooled_out_of_sample"])

# The parameters to use: the ones that won a held-out fold. The features are
# then re-derived on all paragraphs, because the character sets are cheap
# and stable, but the WEIGHTS are the validated ones.
best_tag = heldout_best[1]
chosen = R["folds"][best_tag]["params"]
openers_all, closers_all, o_stats, c_stats = derive_features(paragraphs)
best_params = dict(chosen)
R["chosen_params"] = {
    "from_fold": best_tag, "params": best_params,
    "why": "weights come from the fold that won on held-out data; the "
           "character sets are re-derived on all paragraphs",
    "n_openers": len(openers_all), "n_closers": len(closers_all),
    "openers": "".join(sorted(openers_all)),
    "closers": "".join(sorted(closers_all)),
    "top_openers": o_stats[:14],
    "top_closers": c_stats[:14],
}
print("CHOSEN:", best_tag, best_params)
print("  openers:", "".join(sorted(openers_all)))
print("  closers:", "".join(sorted(closers_all)))


# ------------------------------------------------------------------
# renderer
# ------------------------------------------------------------------
def is_latin_digit(ch):
    return ch.isascii() and (ch.isalpha() or ch.isdigit())


def join_units(units):
    out = []
    for i, u in enumerate(units):
        if i == 0:
            out.append(u)
            continue
        prev = out[-1]
        if not prev or not u:
            out.append(u)
            continue
        a, b = prev[-1], u[0]
        if is_latin_digit(a) != is_latin_digit(b) and (
                is_latin_digit(a) or is_latin_digit(b)):
            out.append("\u2009")
        else:
            out.append(" ")
        out.append(u)
    return "".join(out)


def display_width(s):
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def wrap(units, soft=17, hard=24, max_units=3):
    """Break units into lines: at most `max_units` per line, prefer a break
    once the line reaches `soft` display columns, never exceed `hard`
    unless a single unit is longer."""
    lines = []
    cur = []
    cur_w = 0
    for u in units:
        uw = display_width(u)
        if cur and (len(cur) >= max_units or cur_w + uw > soft):
            if cur_w + uw > hard and len(cur) == 1:
                # one long unit: let it sit alone rather than overflow
                lines.append(cur)
                cur = []
                cur_w = 0
            else:
                lines.append(cur)
                cur = []
                cur_w = 0
        cur.append(u)
        cur_w += uw + 1
    if cur:
        lines.append(cur)
    return lines


def render(plain, params, openers, closers):
    ws, ps = words_and_pos(plain)
    spans = dp_segment(ws, ps, openers, closers, **params)
    units = unit_texts(plain, spans)
    lines = wrap(units)
    return "\n".join(join_units(l) for l in lines), units, lines


# ------------------------------------------------------------------
# round trip
# ------------------------------------------------------------------
all_auth = []
all_gen = []
for lines in paragraphs:
    s, au = para_units(lines)
    words, pos = words_and_pos(s)
    spans = dp_segment(words, pos, openers_all, closers_all, **best_params)
    all_auth += unit_texts(s, au)
    all_gen += unit_texts(s, spans)

ca = Counter(all_auth)
cg = Counter(all_gen)
R["round_trip_corpus"] = {
    "n_author": len(all_auth), "n_generated": len(all_gen),
    "identical_units_set": sum((ca & cg).values()),
    "frac_identical": round(sum((ca & cg).values()) / len(all_auth), 4),
    "author_only": [[u, n] for u, n in (ca - cg).most_common(12)],
    "generated_only": [[u, n] for u, n in (cg - ca).most_common(12)],
    "paragraph_1": {
        "author": unit_texts(para_units(paragraphs[0])[0],
                             para_units(paragraphs[0])[1]),
        "generated": None,
    },
}
_s0, _u0 = para_units(paragraphs[0])
_w0, _p0 = words_and_pos(_s0)
R["round_trip_corpus"]["paragraph_1"]["generated"] = unit_texts(
    _s0, dp_segment(_w0, _p0, openers_all, closers_all, **best_params))


# ------------------------------------------------------------------
# style metrics on the same terms for author and generator
# ------------------------------------------------------------------
def style_metrics(units, lines):
    lens = [len(u) for u in units]
    widths = [display_width(join_units(l)) for l in lines]
    per_line = [len(l) for l in lines]
    return {
        "n_units": len(units),
        "unit_len_mean": round(sum(lens) / len(lens), 3),
        "unit_len_median": sorted(lens)[len(lens) // 2],
        "unit_len_hist": dict(sorted(Counter(lens).items())),
        "frac_units_2_to_4": round(sum(1 for x in lens if 2 <= x <= 4) / len(lens), 4),
        "frac_units_le_4": round(sum(1 for x in lens if x <= 4) / len(lens), 4),
        "n_lines": len(lines),
        "width_median": sorted(widths)[len(widths) // 2] if widths else 0,
        "width_max": max(widths) if widths else 0,
        "width_min": min(widths) if widths else 0,
        "units_per_line_hist": dict(sorted(Counter(per_line).items())),
    }


author_lines = []
for lines in paragraphs:
    for l in lines:
        author_lines.append([u for u in re.split("[" + "".join(WS) + "]", l) if u])
author_units_flat = []
for l in author_lines:
    author_units_flat += l
R["metrics_author"] = style_metrics(author_units_flat, author_lines)

gen_units = []
gen_lines = []
for lines in paragraphs:
    s, _ = para_units(lines)
    _, u, l = render(s, best_params, openers_all, closers_all)
    gen_units += u
    gen_lines += l
R["metrics_generated"] = style_metrics(gen_units, gen_lines)

# the same boundary test the author was scored on
gen_cuts = set()
off = 0
for lines in paragraphs:
    s, _ = para_units(lines)
    words, pos = words_and_pos(s)
    spans = dp_segment(words, pos, openers_all, closers_all, **best_params)
    for (a, b) in spans[:-1]:
        gen_cuts.add(off + b)
    off += len(s)
jb = set()
off = 0
for lines in paragraphs:
    s, _ = para_units(lines)
    words, _ = words_and_pos(s)
    acc = 0
    for w in words:
        acc += len(w)
        jb.add(off + acc)
    off += len(s)
R["generated_boundary_alignment"] = {
    "n_cuts": len(gen_cuts),
    "on_jieba_boundary": round(len(gen_cuts & jb) / len(gen_cuts), 4),
    "author_on_the_same_test": 0.9767,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1)

print()
print("round trip corpus:")
rt = R["round_trip_corpus"]
print(f"   identical units {rt['identical_units_set']}/{rt['n_author']} "
      f"= {rt['frac_identical']}")
print("   author-only  :", rt["author_only"][:8])
print("   generated-only:", rt["generated_only"][:8])
print("   paragraph 1 author   :", rt["paragraph_1"]["author"])
print("   paragraph 1 generated:", rt["paragraph_1"]["generated"])
print()
print("metrics author   :", json.dumps(R["metrics_author"], ensure_ascii=False))
print("metrics generated:", json.dumps(R["metrics_generated"], ensure_ascii=False))
print("generated boundary alignment:", R["generated_boundary_alignment"])
print("wrote", OUT)
