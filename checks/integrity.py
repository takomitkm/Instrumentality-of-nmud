"""Integrity check for the segmenter alignment measurement.

The HanLP number (64%) contradicted its own sample output, which was
identical to pkuseg's for the first 25 tokens. A plausible cause: a
segmenter that does not reproduce the input string exactly (normalisation,
dropped characters) shifts every boundary offset, which silently corrupts
the alignment rate.

This script asserts, for every segmenter, that the concatenation of its
tokens equals the input. Only then is the boundary alignment meaningful.
"""
import json
import os
import re

import jieba
import thulac

import nlp_paths

jieba.setLogLevel(60)
_tac = thulac.thulac()

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
OUT = (nlp_paths.arg("--out")
       or nlp_paths.locate_out("result file", "integrity_report.json", "out"))

raw = open(CORPUS, "rb").read()
text = raw.decode("utf-8")
lines = [l for l in text.replace("\r\n", "\n").split("\n") if l.strip()]

stripped = []
space_cuts = set()
line_cuts = set()
for l in lines:
    ss = None
    for ch in l:
        if ch == " ":
            if ss is not None:
                space_cuts.add(len(stripped)); ss = None
        else:
            if ss is None: ss = len(stripped)
            stripped.append(ch)
    if ss is not None:
        line_cuts.add(len(stripped))
stripped = "".join(stripped)

R = {"n_chars": len(stripped), "n_space_cuts": len(space_cuts),
     "n_line_cuts": len(line_cuts), "segmenters": []}


def check(label, words):
    """words: list of strings, or list of (word, pos) tuples."""
    plain = []
    for w in words:
        if isinstance(w, (list, tuple)) and len(w) >= 1 and isinstance(w[0], str):
            plain.append(w[0])
        else:
            plain.append(w)
    joined = "".join(plain)
    exact = joined == stripped
    rec = {"segmenter": label, "n_tokens": len(plain),
           "reproduces_input_exactly": exact,
           "joined_len": len(joined), "input_len": len(stripped)}
    if not exact:
        # find the first divergence
        for i, (a, b) in enumerate(zip(joined, stripped)):
            if a != b:
                rec["first_divergence_at"] = i
                rec["joined_around"] = joined[max(0, i - 10):i + 10]
                rec["input_around"] = stripped[max(0, i - 10):i + 10]
                break
        else:
            rec["first_divergence_at"] = min(len(joined), len(stripped))
        rec["chars_in_joined_not_in_input"] = len(
            re.findall(r"[^\u4e00-\u9fff0-9a-zA-Z]", joined))
    if exact:
        b = set()
        acc = 0
        for w in plain:
            b.add(acc); acc += len(w)
        rec["boundary_density"] = round((len(b) - 1) / len(stripped), 4)
        rec["space_cuts_on_boundary"] = round(
            sum(1 for p in space_cuts if p in b) / len(space_cuts), 4)
        rec["line_cuts_on_boundary"] = round(
            sum(1 for p in line_cuts if p in b) / len(line_cuts), 4)
    R["segmenters"].append(rec)
    return rec


check("jieba", list(jieba.cut(stripped)))
check("thulac", [p[0] for p in _tac.cut(stripped)])

try:
    import pkuseg
    seg = pkuseg.pkuseg()
    check("pkuseg", seg.cut(stripped))
except Exception as e:
    R["pkuseg_error"] = f"{type(e).__name__}: {e}"

try:
    os.environ.setdefault("HANLP_HOME",
                          nlp_paths.locate_dir("hanlp models", "hanlp_models",
                                               "tools"))
    import hanlp
    tok_name = None
    tok_ns = getattr(hanlp.pretrained, "tok", None)
    if tok_ns is not None and not isinstance(tok_ns, str):
        for cand in ("COARSE_ELECTRA_SMALL_ZH", "FINE_ELECTRA_SMALL_ZH"):
            if hasattr(tok_ns, cand):
                tok_name = getattr(tok_ns, cand); break
    tok = hanlp.load(tok_name)
    # HanLP returns a nested structure for a long input: the tokenizer emits
    # (word, pos) pairs, and a long text can come back as a list of lists.
    # The earlier flatten() collapsed the whole thing into ONE token, which
    # shifted every boundary offset and produced a bogus 64% alignment rate.
    raw_out = tok(stripped)
    flat = []

    def walk(o, depth=0):
        if depth > 6:
            return
        if isinstance(o, (list, tuple)):
            if not o:
                return
            # A (word, pos) pair: exactly two elements, first is a string.
            # A bare string element is a plain token.
            if isinstance(o[0], str) and len(o) == 2 and isinstance(o[1], str):
                flat.append(o)
                return
            if isinstance(o[0], str) and len(o) == 1:
                flat.append(o[0])
                return
            for x in o:
                walk(x, depth + 1)
        elif isinstance(o, str):
            flat.append(o)

    walk(raw_out)
    check("hanlp", flat)
    R["hanlp_n_flat"] = len(flat)
    R["hanlp_raw_type"] = type(raw_out).__name__
    R["hanlp_raw_head"] = str(raw_out)[:200]
except Exception as e:
    R["hanlp_error"] = f"{type(e).__name__}: {e}"

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1)

for s in R["segmenters"]:
    print(json.dumps(s, ensure_ascii=False)[:400])
print("errors:", {k: v for k, v in R.items() if k.endswith("_error")})
print("wrote", OUT)
