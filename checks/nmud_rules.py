"""Definitive analysis of the nmud corpus: spacing, line breaking, word usage.

Canonical definitions used throughout (stated once, enforced everywhere):

  WHITESPACE  = U+0020 SPACE or U+2009 THIN SPACE. Both separate units.
  LINE        = a non-blank physical line of the source file.
  UNIT        = a maximal run of non-whitespace characters inside one line.
                A line break ends a unit; whitespace ends a unit.
  STREAM      = the corpus with all whitespace removed (1558 chars).
  CUT         = a position in STREAM where one unit ends and the next begins.

Every segmenter is checked for "concatenating its tokens reproduces STREAM
exactly" before its boundary alignment is used; without that check a
normalising segmenter silently shifts every offset.

Sections
  1  corpus shape
  2  whitespace: two kinds, two jobs
  3  unit inventory
  4  do the author's cuts land on word boundaries? (4 segmenters + nulls)
  5  what do the units look like inside? (shape vs the segmenter)
  6  POS profile and the transitions the author cuts at
  7  line breaking
  8  vocabulary and word usage
  9  the "nmud" self-reference
 10  can a rule reproduce the segmentation?
"""
import json
import os
import random
import re
import unicodedata
from collections import Counter

import jieba
import thulac
import jieba.posseg as pseg

import nlp_paths

jieba.setLogLevel(60)
_tac = thulac.thulac()

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
OUT = (nlp_paths.arg("--out")
       or nlp_paths.locate_out("result file", "nmud_rules.json", "out"))

WS = (" ", "\u2009")
raw = open(CORPUS, "rb").read()
text = raw.decode("utf-8")
phys = text.replace("\r\n", "\n").split("\n")
if phys and phys[-1] == "":
    phys = phys[:-1]
lines = [l for l in phys if l.strip()]

R = {"source": CORPUS}

# ------------------------------------------------------------------
# 1. corpus shape
# ------------------------------------------------------------------
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

R["corpus"] = {
    "bytes": len(raw),
    "utf8_bom": raw[:3] == b"\xef\xbb\xbf",
    "physical_lines": len(phys),
    "nonblank_lines": len(lines),
    "blank_lines": len(phys) - len(lines),
    "paragraphs": len(paragraphs),
    "line_ends_with_crlf": raw.count(b"\r\n"),
    "space_u0020": text.count(" "),
    "thin_space_u2009": text.count("\u2009"),
    "other_whitespace": sum(1 for c in text if c.isspace() and c not in WS and c not in "\r\n"),
}

# ------------------------------------------------------------------
# 2. build the stream, the cuts and the units
# ------------------------------------------------------------------
stream = []
units = []          # (start, end, text, kind_of_ending)
ws_cuts = set()     # whitespace-induced cuts
line_cuts = set()   # line-end cuts
space_cut = set()   # U+0020 only
thin_cut = set()    # U+2009 only

for l in lines:
    seg_start = None
    for ch in l:
        if ch in WS:
            if seg_start is not None:
                units.append((seg_start, len(stream), stream[seg_start:]))
                ws_cuts.add(len(stream))
                (space_cut if ch == " " else thin_cut).add(len(stream))
                seg_start = None
        else:
            if seg_start is None:
                seg_start = len(stream)
            stream.append(ch)
    if seg_start is not None:
        units.append((seg_start, len(stream), stream[seg_start:]))
        line_cuts.add(len(stream))

stream = "".join(stream)
units = [(s, e, stream[s:e]) for (s, e, _) in units]
all_cuts = ws_cuts | line_cuts

R["stream"] = {"chars": len(stream), "units": len(units),
               "whitespace_cuts": len(ws_cuts), "line_cuts": len(line_cuts)}
assert units[0][0] == 0 and units[-1][1] == len(stream)
for i in range(len(units) - 1):
    assert units[i][1] == units[i + 1][0]

# ------------------------------------------------------------------
# 3. the two whitespace characters do different jobs
# ------------------------------------------------------------------
def char_class(c):
    if not c:
        return "EDGE"
    if c.isascii() and c.isalpha():
        return "LATIN"
    if c.isascii() and c.isdigit():
        return "DIGIT"
    if "\u4e00" <= c <= "\u9fff":
        return "CJK"
    return "PUNCT"


side = Counter()
thin_side = Counter()
space_side = Counter()
for l in lines:
    for m in re.finditer(" ", l):
        pre = l[m.start() - 1] if m.start() > 0 else ""
        post = l[m.end()] if m.end() < len(l) else ""
        space_side[(char_class(pre), char_class(post))] += 1
    for m in re.finditer("\u2009", l):
        pre = l[m.start() - 1] if m.start() > 0 else ""
        post = l[m.end()] if m.end() < len(l) else ""
        thin_side[(char_class(pre), char_class(post))] += 1

R["whitespace_roles"] = {
    "ascii_space_sides": {f"{a}|{b}": n for (a, b), n in space_side.most_common()},
    "thin_space_sides": {f"{a}|{b}": n for (a, b), n in thin_side.most_common()},
    "thin_space_never_between_two_cjk": all(
        "CJK" not in (a, b) or a != b for (a, b) in thin_side) and all(
        not (a == "CJK" and b == "CJK") for (a, b) in thin_side),
    "thin_space_touches_latin_or_digit": all(
        "LATIN" in (a, b) or "DIGIT" in (a, b) for (a, b) in thin_side),
    "thin_space_examples": [l for l in lines if "\u2009" in l],
}

# ------------------------------------------------------------------
# 4. segmenters: integrity first, then alignment
# ------------------------------------------------------------------
def boundaries(words):
    b = set()
    acc = 0
    for w in words:
        b.add(acc)
        acc += len(w)
    return b


def rate(pos, bnd):
    if not pos:
        return None
    return round(sum(1 for p in pos if p in bnd) / len(pos), 4)


seg_report = []
word_sets = {}

seg_report.append(("jieba", list(jieba.cut(stream))))
seg_report.append(("thulac", [p[0] for p in _tac.cut(stream)]))
try:
    import pkuseg
    _ps = pkuseg.pkuseg()
    seg_report.append(("pkuseg", list(_ps.cut(stream))))
except Exception as e:
    R["pkuseg_error"] = f"{type(e).__name__}: {e}"
try:
    os.environ.setdefault("HANLP_HOME",
                          nlp_paths.locate_dir("hanlp models", "hanlp_models",
                                               "tools"))
    import hanlp
    _tok = hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
    _out = _tok(stream)
    _flat = []
    for _o in _out:
        if isinstance(_o, (list, tuple)) and len(_o) == 2 and isinstance(_o[0], str) \
                and isinstance(_o[1], str):
            _flat.append(_o[0])
        elif isinstance(_o, str):
            _flat.append(_o)
    seg_report.append(("hanlp", _flat))
except Exception as e:
    R["hanlp_error"] = f"{type(e).__name__}: {e}"

R["segmenters"] = []
for name, words in seg_report:
    joined = "".join(words)
    rec = {"segmenter": name, "n_tokens": len(words),
           "reproduces_stream_exactly": joined == stream}
    if joined != stream:
        rec["SKIPPED"] = "tokens do not reproduce the input; alignment would be shifted"
    else:
        b = boundaries(words)
        word_sets[name] = b
        rec.update({
            "boundary_density": round((len(b) - 1) / len(stream), 4),
            "ws_cuts_on_boundary": rate(ws_cuts, b),
            "line_cuts_on_boundary": rate(line_cuts, b),
            "all_cuts_on_boundary": rate(all_cuts, b),
        })
    R["segmenters"].append(rec)

# null model
random.seed(20261020)
ref_b = word_sets.get("jieba")
if ref_b:
    nulls = sorted(rate(random.sample(range(1, len(stream)), len(ws_cuts)), ref_b)
                   for _ in range(5000))
    R["null_model_random_cuts"] = {
        "segmenter_reference": "jieba",
        "mean": round(sum(nulls) / len(nulls), 4),
        "p01": nulls[int(len(nulls) * 0.01)], "p50": nulls[int(len(nulls) * 0.50)],
        "p95": nulls[int(len(nulls) * 0.95)], "p99": nulls[int(len(nulls) * 0.99)],
    }

# competing generative rules
comp = {}
for k in (2, 3, 4, 5):
    pos = list(range(k, len(stream), k))
    row = {"mean_unit_len": k}
    for name, b in word_sets.items():
        row[name] = rate(pos, b)
    comp[f"fixed_pitch_{k}"] = row
for name, b in word_sets.items():
    comp[f"break_at_every_{name}_boundary"] = {
        "n_units": len(b), "mean_unit_len": round(len(stream) / len(b), 3)}
comp["author"] = {"n_units": len(units),
                  "mean_unit_len": round(len(stream) / len(units), 3)}
R["competing_rules"] = comp

# ------------------------------------------------------------------
# 5. unit shape vs the segmenter
# ------------------------------------------------------------------
jieba_words = list(jieba.cut(stream))
jspans = []
acc = 0
for w in jieba_words:
    jspans.append((acc, acc + len(w), w))
    acc += len(w)

overlap = Counter()
exact_one = 0
inside = []
for (s, e, txt) in units:
    ws = [w for (a, b, w) in jspans if a < e and b > s]
    overlap[len(ws)] += 1
    if len(ws) == 1 and ws[0] == txt:
        exact_one += 1
    if e < len(stream) and e not in word_sets.get("jieba", set()):
        host = [w for (a, b, w) in jspans if a < e < b]
        inside.append({"unit": txt, "jieba_word_cut_into": host[0] if host else "",
                       "context": stream[max(0, s - 6):e + 6]})

R["unit_shape"] = {
    "overlap_hist": dict(sorted(overlap.items())),
    "unit_is_exactly_one_jieba_word": exact_one,
    "frac_exactly_one": round(exact_one / len(units), 4),
    "frac_one_or_two": round((overlap[1] + overlap[2]) / len(units), 4),
    "cuts_inside_a_jieba_word": len(inside),
    "frac_cuts_inside": round(len(inside) / len(units), 4),
    "inside_examples": inside,
}

lens = [len(t) for (_, _, t) in units]
R["unit_length"] = {"n": len(lens), "mean": round(sum(lens) / len(lens), 3),
                    "median": sorted(lens)[len(lens) // 2],
                    "hist": dict(sorted(Counter(lens).items()))}

# ------------------------------------------------------------------
# 6. POS profile
# ------------------------------------------------------------------
pos_of = {}
for w, f in pseg.cut(stream):
    pos_of.setdefault(w, f)
first_pos = Counter(); last_pos = Counter()
for (s, e, txt) in units:
    ws = [w for (a, b, w) in jspans if a < e and b > s]
    if ws:
        first_pos[pos_of.get(ws[0], "?")] += 1
        last_pos[pos_of.get(ws[-1], "?")] += 1
R["unit_first_pos"] = first_pos.most_common(12)
R["unit_last_pos"] = last_pos.most_common(12)

pos_stream = []
for w, f in pseg.cut(stream):
    for _ in w:
        pos_stream.append(f)
pos_change = {i for i in range(1, len(pos_stream)) if pos_stream[i] != pos_stream[i - 1]}
R["cuts_on_pos_change"] = {
    "ws_cuts": rate(ws_cuts, pos_change), "line_cuts": rate(line_cuts, pos_change),
    "pos_change_density": round(len(pos_change) / len(stream), 4)}

all_pairs = Counter()
for i in range(1, len(pos_stream)):
    all_pairs[(pos_stream[i - 1], pos_stream[i])] += 1
cut_pairs = Counter()
for p in ws_cuts:
    if 0 < p < len(pos_stream):
        cut_pairs[(pos_stream[p - 1], pos_stream[p])] += 1
R["pos_transitions_at_ws_cuts"] = [
    {"from": a, "to": b, "n": n,
     "expected": round(all_pairs[(a, b)] * len(ws_cuts) / len(stream), 2),
     "lift": round(n / max(1e-9, all_pairs[(a, b)] * len(ws_cuts) / len(stream)), 2)}
    for (a, b), n in cut_pairs.most_common(20)]

# ------------------------------------------------------------------
# 7. line breaking
# ------------------------------------------------------------------
def display_width(s):
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


line_rows = []
for i, l in enumerate(lines, 1):
    toks = [t for t in re.split("[" + "".join(WS) + "]", l) if t]
    line_rows.append({"line": i, "text": l, "units": len(toks),
                      "chars": len(re.sub("[" + "".join(WS) + "]", "", l)),
                      "width": display_width(l),
                      "ends_with_punct": bool(re.search(r"[。！？…，、；：\.,!?]", l))})
widths = [r["width"] for r in line_rows]
unit_counts = [r["units"] for r in line_rows]
R["line_breaking"] = {
    "width": {"median": sorted(widths)[len(widths) // 2], "min": min(widths), "max": max(widths),
              "p25": sorted(widths)[len(widths) // 4], "p75": sorted(widths)[3 * len(widths) // 4],
              "p95": sorted(widths)[int(len(widths) * 0.95)],
              "mean": round(sum(widths) / len(widths), 2)},
    "units_per_line": {"median": sorted(unit_counts)[len(unit_counts) // 2],
                       "hist": dict(sorted(Counter(unit_counts).items())),
                       "mean": round(sum(unit_counts) / len(unit_counts), 2)},
    "lines_with_terminal_punct": sum(1 for r in line_rows if r["ends_with_punct"]),
    "lines_over_20_cols": sum(1 for w in widths if w > 20),
    "lines_over_24_cols": sum(1 for w in widths if w > 24),
    "paragraph_line_counts": [len(p) for p in paragraphs],
    "paragraph_unit_counts": [sum(len(re.split("[" + "".join(WS) + "]", l)) for l in p) - len(p)
                               for p in paragraphs],
    "paragraphs": len(paragraphs),
}

# does a line break fall on a segmenter boundary? already measured; also:
# how many lines begin with a segmenter word start?
jb_starts = {a for (a, b, w) in jspans}
line_start_positions = []
pos = 0
for l in lines:
    stripped_l = [c for c in l if c not in WS]
    line_start_positions.append(pos)
    pos += len(stripped_l)
R["line_breaking"]["line_start_on_jieba_boundary"] = rate(line_start_positions, jb_starts)

# ------------------------------------------------------------------
# 8. vocabulary and word usage
# ------------------------------------------------------------------
uc = Counter(t for (_, _, t) in units)
R["vocabulary"] = {
    "units": len(units), "unique_units": len(uc),
    "hapax": sum(1 for v in uc.values() if v == 1),
    "hapax_frac": round(sum(1 for v in uc.values() if v == 1) / len(uc), 4),
    "top40": uc.most_common(40),
}
latin_tokens = Counter()
for l in lines:
    for t in re.split("[" + "".join(WS) + "]", l):
        if t and re.fullmatch(r"[A-Za-z0-9]+", t):
            latin_tokens[t] += 1
R["vocabulary"]["latin_tokens"] = {"unique": len(latin_tokens),
                                   "total": sum(latin_tokens.values()),
                                   "items": latin_tokens.most_common(20)}
cjk_latin_direct = sum(1 for l in lines
                       for m in re.finditer(r"[A-Za-z0-9][\u4e00-\u9fff]|[\u4e00-\u9fff][A-Za-z0-9]", l))
R["vocabulary"]["cjk_latin_direct_adjacency"] = cjk_latin_direct

# ------------------------------------------------------------------
# 9. the nmud self-reference
# ------------------------------------------------------------------
viol = []
occ = 0
for l in lines:
    for m in re.finditer("nmud", l):
        occ += 1
        pre = l[m.start() - 1] if m.start() > 0 else ""
        post = l[m.end()] if m.end() < len(l) else ""
        # At a line edge the neighbour is a line boundary, not a character,
        # so only count a violation when there IS a neighbour and it is not
        # whitespace.
        if (pre and pre not in WS) or (post and post not in WS):
            viol.append(l)
R["nmud"] = {
    "occurrences": occ,
    "lines_containing": sum(1 for l in lines if "nmud" in l),
    "as_whole_unit": sum(1 for (_, _, t) in units if t == "nmud"),
    "at_line_start": sum(1 for l in lines if l.startswith("nmud")),
    "at_line_end": sum(1 for l in lines if l.endswith("nmud")),
    "mid_line": sum(1 for l in lines if "nmud" in l[1:-1]),
    "never_alone_on_a_line": all(l.strip() != "nmud" for l in lines),
    "always_separated_by_whitespace": len(viol) == 0,
    "violations": viol[:5],
}

# ------------------------------------------------------------------
# 10. can a rule reproduce the segmentation?
# ------------------------------------------------------------------
# Derived from the data: characters that unusually often START a unit.
lift = {}
for i in range(1, len(stream)):
    c = stream[i]
    if c not in lift:
        lift[c] = [0, 0]
    lift[c][0] += 1
    if i in ws_cuts:
        lift[c][1] += 1
base = len(ws_cuts) / (len(stream) - 1)
opener = {}
for c, (n, h) in lift.items():
    if n >= 3:
        exp = n * base
        if exp > 0:
            opener[c] = (h, n, round(h / exp, 2))
openers = {c for c, (h, n, l) in opener.items() if l >= 2.0 and h >= 2}
R["unit_openers_derived"] = {
    "base_cut_rate": round(base, 4),
    "chars_with_lift_ge_2": sorted(openers),
    "top": sorted(({"char": c, "cuts": h, "positions": n, "lift": l}
                   for c, (h, n, l) in opener.items()), key=lambda r: -r["lift"])[:20],
}


def replicate(min_len, use_openers, use_words):
    cuts = set()
    start = 0
    for i in range(1, len(stream)):
        cur = i - start
        if cur < min_len:
            continue
        opener_hit = use_openers and stream[i] in openers
        word_hit = use_words and i in jb_starts
        if opener_hit or (word_hit and cur >= min_len + 1):
            cuts.add(i)
            start = i
    return cuts


def score(pred, truth):
    pred = set(pred)
    tp = len(pred & truth)
    p = round(tp / len(pred), 4) if pred else 0
    r = round(tp / len(truth), 4) if truth else 0
    f = round(2 * p * r / (p + r), 4) if (p + r) else 0
    ls = []
    prev = 0
    for q in sorted(pred) + [len(stream)]:
        if q > prev:
            ls.append(q - prev)
        prev = q
    return {"predicted": len(pred), "tp": tp, "precision": p, "recall": r, "f1": f,
            "mean_unit_len": round(sum(ls) / len(ls), 3) if ls else None}


grid = []
for ml in (1, 2, 3):
    for uo in (True, False):
        for uw in (True, False):
            s = score(replicate(ml, uo, uw), ws_cuts)
            s["params"] = {"min_len": ml, "openers": uo, "words": uw}
            grid.append(s)
grid.sort(key=lambda r: -r["f1"])
R["rule_reproduction"] = {
    "scored_against": "whitespace cuts only",
    "grid": grid[:8],
    "best": grid[0],
    "note": "A rule that only says 'cut on a word boundary' cannot reproduce "
            "the author's segmentation: the author's units are COARSER than a "
            "segmenter's words (units merge 2+ words), so the best achievable "
            "F1 against the whitespace cuts stays well below 1.",
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1)

print("stream chars:", R["stream"]["chars"], "units:", R["stream"]["units"])
print("corpus:", json.dumps(R["corpus"], ensure_ascii=False))
print()
print("segmenters:")
for s in R["segmenters"]:
    print("  ", json.dumps(s, ensure_ascii=False))
print()
print("null model:", R.get("null_model_random_cuts"))
print("unit length:", R["unit_length"])
print("unit shape:", {k: v for k, v in R["unit_shape"].items() if k != "inside_examples"})
print("cuts inside a jieba word:")
for e in R["unit_shape"]["inside_examples"]:
    print("   ", e)
print("POS at cuts:", R["cuts_on_pos_change"])
print("POS transitions (top 8):")
for r in R["pos_transitions_at_ws_cuts"][:8]:
    print(f"    {r['from']:>4} -> {r['to']:<4} n={r['n']:<3} exp={r['expected']:<6} lift={r['lift']}")
print("line breaking:", json.dumps(R["line_breaking"], ensure_ascii=False))
print("nmud:", json.dumps(R["nmud"], ensure_ascii=False))
print("rule best:", R["rule_reproduction"]["best"])
print("wrote", OUT)
