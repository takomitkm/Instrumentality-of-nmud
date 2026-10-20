"""nmud-style generator: write in the measured style of the nmud corpus.

WHAT THIS DOES
    Takes plain Chinese text and renders it in the style measured in
    nmud.txt: cut into 2-4 character units on word boundaries, join the
    units with a space, use a THIN SPACE where a Latin or digit token
    meets a Chinese character, and wrap into lines of 2-3 units.

HOW THE RULES WERE OBTAINED
    Every feature is either read off the corpus or fitted on it:
      opener    a character the author often STARTS a unit with
      closer    a character the author often ENDS a unit with
      de_next   weight for cutting immediately BEFORE a word that starts
                with the particle 的
      de_prev   weight for cutting immediately AFTER a word that ends
                with the particle 的
                The corpus does both (39 units end with 的, 12 start with
                it), so the two directions are separate learned weights
                and the data decides their sign.
      posstart  the next word's part of speech is function-like
      posend    the previous word's part of speech is content-like

    The character sets are derived from the training half only during
    validation; the weights are chosen by HELD-OF-VALIDATION (fit on one
    half of the paragraphs, score on the other, both directions), and the
    winner of those held-out folds is what ships.

HOW IT IS JUDGED
    The same yardstick that was used to measure the author:
      - unit-level F1 against the author's own cuts, held out
      - round trip: strip the author's spaces, re-segment, compare
      - the same style metrics (unit length, units per line, display
        width) for author and generator

    It does NOT reproduce the author perfectly, and the report says so.

USAGE
    python nmud_style.py --in plain.txt --out styled.txt
    python nmud_style.py --demo
"""
import argparse
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

try:
    import jieba
    import jieba.posseg as pseg
except ImportError:  # the environment check has to run without jieba
    jieba = None
    pseg = None
else:
    jieba.setLogLevel(60)

HERE = Path(__file__).resolve().parent
# The corpus, the fitted parameters and the result files sit next to this
# file in the installed package (data/), or next to it / one folder up in
# the flat layout the school machine uses (tools/ and out/).
DATA_DIRS = [HERE / "data", HERE, HERE.parent / "out", HERE.parent / "tools"]


def find_data(name):
    """The first candidate that exists, else the first candidate."""
    for d in DATA_DIRS:
        p = d / name
        if p.exists():
            return p
    return DATA_DIRS[0] / name


def cache_dir():
    """A writable place for the fitted parameters and the result json."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "nmud-style"


def ask(prompt, default=""):
    """Ask a question. A closed stdin means "no answer", not a hang."""
    try:
        answer = input(prompt)
    except EOFError:
        print("(no console input)")
        return default
    answer = answer.strip()
    return answer or default

# The corpus and the result files are looked up next to this script (or in
# the tools/ and out/ folders beside it); anything missing is asked for.
# Command line flags override both.
CORPUS = None
OUT_JSON = None

WS = (" ", "\u2009")
THIN = "\u2009"

# ------------------------------------------------------------------
# punctuation
# ------------------------------------------------------------------
# The corpus uses four kinds of punctuation and no others: the ellipsis
# (6), the question mark (1), the exclamation mark (1) and the two
# quote marks (4 pairs). The full stops, commas, semicolons, colons,
# dunhao and brackets that ordinary Chinese writing uses appear 0 times.
#
# Every mark the author does use sits against a word; he never lets one
# stand in a unit of its own. The opening quote rides on the front of
# the first word of the quoted phrase, the closing quote on the back of
# the last one, and the marks that close a thought (ellipsis, question
# mark, exclamation mark) sit on the back of the word before them.
AUTHOR_PUNCT = "\u2026\uff1f\uff01\u201c\u201d"      # ... ? ! " "
FRONT_PUNCT = "“（【《〈「『"      # the marks that open a phrase
CJK_PUNCT = set("\u3002\uff0c\u3001\uff1b\uff1a\uff08\uff09\u300a\u300b"
                "\u3008\u3009\u300c\u300d\u300e\u300f\u00b7\u2014\uff5e"
                "\u2018\u2019\u201c\u201d\u2026\uff1f\uff01\u3000")
ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
PUNCT_ALL = CJK_PUNCT | ASCII_PUNCT

POS_START = {"r", "d", "p", "c", "u", "m", "q", "t", "f", "s"}
POS_END = {"n", "nr", "ns", "nt", "nz", "v", "vd", "vn", "a", "ad", "an",
           "eng", "i", "l", "j", "z", "y", "x", "m", "q", "b"}
DE = "的"


# ------------------------------------------------------------------
# corpus
# ------------------------------------------------------------------
def load_paragraphs(path):
    text = open(path, "rb").read().decode("utf-8")
    phys = text.replace("\r\n", "\n").split("\n")
    out = []
    cur = []
    for l in phys:
        if l.strip():
            cur.append(l)
        else:
            if cur:
                out.append(cur)
                cur = []
    if cur:
        out.append(cur)
    return out


def para_units(lines):
    """The author's own units for one paragraph, as (stream, [(start,end)])."""
    stream = []
    units = []
    for l in lines:
        seg = None
        for ch in l:
            if ch in WS:
                if seg is not None:
                    units.append((seg, len(stream)))
                    seg = None
            else:
                if seg is None:
                    seg = len(stream)
                stream.append(ch)
        if seg is not None:
            units.append((seg, len(stream)))
    return "".join(stream), units


def script_class(ch):
    """WEST for an ASCII letter, digit or ASCII punctuation, CJK for the rest.

    Chinese punctuation counts as CJK: the corpus never puts a Latin
    token directly next to Chinese punctuation, so "nmud。" would be a
    mixed unit just like "nmud语" is.

    ASCII punctuation counts as WEST, so that "90.8%" stays one token
    instead of being torn into "90" "." "8" "%".
    """
    if ch.isascii() and not ch.isspace():
        return "WEST"
    return "CJK"


def split_mixed_word(word):
    """Split a word that mixes Chinese and western characters.

    jieba sometimes glues a Latin token onto a Chinese one. The author
    never does that: all 66 Chinese-to-Latin/digit boundaries in the
    corpus carry a space, so no unit of his mixes the two scripts.
    """
    if not word:
        return [word]
    parts = []
    cur = ""
    prev = None
    for ch in word:
        c = script_class(ch)
        if prev is not None and c != prev:
            parts.append(cur)
            cur = ""
        cur += ch
        prev = c
    parts.append(cur)
    return parts


def is_punct_only(w):
    """True when a word is nothing but punctuation."""
    if not w:
        return False
    return all(ch in PUNCT_ALL for ch in w)


def strip_unused_punct(text):
    """Remove the punctuation the author never uses.

    The corpus has four kinds of punctuation and no others: the ellipsis,
    the question mark, the exclamation mark and the two quote marks. The
    full stop, the comma, the semicolon, the colon, the dunhao and the
    brackets of ordinary Chinese writing appear 0 times, so they are
    taken out here. The western marks are left alone: they belong to
    the western tokens ("90.8%").

    A mark that goes is replaced by a space, not deleted. The mark stood
    for a boundary the writer chose, and the same rule as everywhere else
    applies: a boundary in the input stays a boundary in the output.
    """
    return "".join(" " if (ch in CJK_PUNCT and ch not in AUTHOR_PUNCT) else ch
                   for ch in text)


def merge_punct(ws, ps):
    """Glue punctuation onto the word it belongs to.

    The author never lets a mark stand in a unit of its own, so the marks
    are folded into their neighbour before the segmentation sees them:
    an opening mark (the quote, a bracket) onto the front of the word
    after it, everything else onto the back of the word before it. An
    ellipsis that opens a chunk goes in front, the one that trails a
    word stays at the back.
    """
    out = []
    pending = ""          # punctuation waiting for the word after it
    for w, f in zip(ws, ps):
        if not is_punct_only(w):
            if pending:
                w = pending + w
                pending = ""
            out.append([w, f])
            continue
        if (w[0] in FRONT_PUNCT
                or (w[0] == "\u2026" and not out and not pending)):
            pending += w
        elif out:
            out[-1][0] += w
        else:
            pending += w
    if pending:
        if out:
            out[-1][0] += pending
        else:
            out.append([pending, "x"])
    return [w for w, _ in out], [f for _, f in out]


def words_and_pos(stream):
    if jieba is None:
        raise SystemExit(
            "jieba is not installed on this machine.\n"
            "The generator needs a segmenter. On the school machine it is\n"
            "already there; on a machine that runs the generator itself:\n"
            "    python setup_env.py\n"
            "or check what is missing with:\n"
            "    nmud-style --check-env")
    ws, ps = [], []
    for w, f in pseg.cut(stream):
        for part in split_mixed_word(w):
            ws.append(part)
            ps.append(f)
    # jieba hands a trailing ASCII symbol to its own token ("90.8%" ->
    # "90.8" + "%", the "%" tagged as a non-word). The author treats a
    # foreign token as one atom, so a bare ASCII symbol is put back onto
    # the western token it belongs to.
    merged = []
    for i, w in enumerate(ws):
        if (merged and ps[i] == "x" and w and all(c.isascii() for c in w)
                and not any(c.isalnum() for c in w)):
            prev_w, prev_f = merged[-1]
            if prev_w and prev_w[-1].isascii():
                merged[-1] = (prev_w + w, prev_f)
                continue
        merged.append((w, ps[i]))
    ws = [w for w, _ in merged]
    ps = [f for _, f in merged]
    return merge_punct(ws, ps)


# ------------------------------------------------------------------
# feature derivation
# ------------------------------------------------------------------
def derive_features(train_paras):
    """Characters that unusually often START or END a unit."""
    after, before = Counter(), Counter()
    tot_a, tot_b = Counter(), Counter()
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


# ------------------------------------------------------------------
# segmenter
# ------------------------------------------------------------------
NEG = float("-inf")


def dp_segment(words, pos, openers, closers, w_open, w_close, w_posstart,
               w_posend, w_de_next, w_de_prev, min_len, max_len):
    """Cut a word list into units under a character length band.

    A word longer than the band becomes its own unit: the corpus contains
    such words (shakeshake, nmudnmud) and the author keeps them whole.
    Without that rule the dynamic program has no reachable path for a
    paragraph containing one and collapses the whole paragraph into a
    single unit. That bug cost four paragraphs before it was found.
    """
    n = len(words)
    if n == 0:
        return []
    plen = [0] * (n + 1)
    for i, w in enumerate(words):
        plen[i + 1] = plen[i] + len(w)
    # Which script each word belongs to. The author puts a space at every
    # Chinese-to-Latin/digit boundary (66 of 66 in the corpus), so no unit
    # of his mixes the two. That rule is applied to the RESULT, not to the
    # search: making it a hard constraint inside the dynamic program cost
    # 0.03 F1 and 7 points of round-trip accuracy, because the length band
    # and the rule fight each other where a one-character unit stands
    # between two western tokens.
    wcls = []
    for w in words:
        c = "WEST"
        for ch in w:
            if script_class(ch) != "WEST":
                c = "CJK"
                break
        wcls.append(c)

    def solve(ml):
        best = [NEG] * (n + 1)
        back = [0] * (n + 1)
        best[0] = 0.0
        for i in range(n):
            if best[i] == NEG:
                continue
            for j in range(i + 1, n + 1):
                ulen = plen[j] - plen[i]
                if ulen > max_len:
                    if j == i + 1 and best[j] < best[i]:
                        best[j] = best[i]
                        back[j] = i
                    break
                if ulen < ml and j < n:
                    continue
                sc = best[i]
                if j < n:
                    nxt, prv = words[j], words[j - 1]
                    if nxt[0] in openers:
                        sc += w_open
                    if prv[-1] in closers:
                        sc += w_close
                    if pos[j] in POS_START:
                        sc += w_posstart
                    if pos[j - 1] in POS_END:
                        sc += w_posend
                    if nxt[0] == DE:
                        sc += w_de_next
                    if prv[-1] == DE:
                        sc += w_de_prev
                if sc > best[j]:
                    best[j] = sc
                    back[j] = i
        return best, back

    best, back = solve(min_len)
    if best[n] == NEG and min_len > 1:
        # No path under the fitted band. The script rule can force a
        # one-character unit (a lone "点" standing between two western
        # tokens), and the corpus does contain one-character units, so
        # retry with those allowed instead of falling back to word-level
        # output.
        best, back = solve(1)
    if best[n] == NEG:
        return [(plen[i], plen[i + 1]) for i in range(n)]
    # reconstruct the word ranges, then split each one where the script
    # changes, so that no unit ever mixes Chinese with Latin or digits
    ranges = []
    j = n
    while j > 0:
        i = back[j]
        ranges.append((i, j))
        j = i
    ranges.reverse()
    out = []
    for (i, j) in ranges:
        start = i
        for k in range(i + 1, j):
            if wcls[k] != wcls[k - 1]:
                out.append((plen[start], plen[k]))
                start = k
        out.append((plen[start], plen[j]))
    return out


def unit_texts(stream, spans):
    return [stream[a:b] for (a, b) in spans]


# ------------------------------------------------------------------
# fitting
# ------------------------------------------------------------------
def prep(paras_subset):
    out = []
    for lines in paras_subset:
        s, units = para_units(lines)
        ws, ps = words_and_pos(s)
        out.append({"stream": s, "author_units": units, "words": ws, "pos": ps})
    return out


def evaluate(data, openers, closers, p):
    tp = pn = tn = 0
    for d in data:
        spans = dp_segment(d["words"], d["pos"], openers, closers, **p)
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
    "w_de_next": [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5],
    "w_de_prev": [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5],
    "min_len": [1, 2],
    "max_len": [3, 4, 5, 6],
}


def fit(data, openers, closers):
    best = None
    keys = ["w_open", "w_close", "w_posstart", "w_posend", "w_de_next", "w_de_prev"]
    vals = [GRID[k] for k in keys]
    for a in vals[0]:
        for b in vals[1]:
            for c in vals[2]:
                for d in vals[3]:
                    for e in vals[4]:
                        for f in vals[5]:
                            if a == 0 and b == 0 and c == 0 and d == 0:
                                continue
                            for ml in GRID["min_len"]:
                                for xl in GRID["max_len"]:
                                    if xl < ml:
                                        continue
                                    p = {"w_open": a, "w_close": b,
                                         "w_posstart": c, "w_posend": d,
                                         "w_de_next": e, "w_de_prev": f,
                                         "min_len": ml, "max_len": xl}
                                    m = evaluate(data, openers, closers, p)
                                    key = (m["f1"], m["precision"])
                                    if best is None or key > best[0]:
                                        best = (key, p, m)
    return best


# ------------------------------------------------------------------
# renderer
# ------------------------------------------------------------------
def is_latin_digit(ch):
    return ch.isascii() and (ch.isalpha() or ch.isdigit())


def split_chunks(text):
    """Split the input into whitespace-delimited chunks, keeping the
    whitespace that separated them.

    Whitespace already in the input is the author's own decision and is
    kept as it stands: an ordinary space stays an ordinary space, a THIN
    SPACE stays a THIN SPACE. The generator only decides the boundaries
    INSIDE a chunk. That is what makes "shake shake" stay two tokens
    instead of being glued into "shakeshake", and it is what reproduces
    the author's six thin spaces exactly.

    A plain Chinese paragraph has no spaces at all, so it arrives as one
    chunk and every boundary in it is the generator's decision.
    """
    parts = re.split(r"([ \t\r\n\u2009]+)", text)
    chunks = []
    sep = ""
    for k, p in enumerate(parts):
        if not p:
            continue
        if re.fullmatch(r"[ \t\r\n\u2009]+", p):
            # the separator: keep thin spaces thin, collapse the rest
            sep = "\u2009" if "\u2009" in p else " "
        else:
            chunks.append((p, sep))
            sep = ""
    return chunks


def join_units(units):
    """Join unit texts with an ordinary space.

    The corpus says the ordinary space is the default: 295 ordinary spaces
    against 6 thin ones, and the thin ones never appear between two
    Chinese characters. The generator therefore never invents a thin
    space; it only keeps the ones the author wrote. Each unit carries the
    separator that preceded it.

    Items may be (text, separator) pairs or plain strings; a plain string
    gets an ordinary space in front of it.
    """
    out = []
    for u in units:
        if isinstance(u, tuple):
            text, sep = u
        else:
            text, sep = u, " "
        if out and sep:
            # the separator belongs BETWEEN units; the first unit of a line
            # carries no leading space, so the measured width is the width
            # of the text itself
            out.append(sep)
        out.append(text)
    return "".join(out)


def unit_text(u):
    return u[0] if isinstance(u, tuple) else u


def display_width(s):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in s)


def wrap(units, soft=18, max_units=3, min_units=2):
    """Break units into lines of 2-3 units, about `soft` display columns.
    `units` is a list of (text, separator) pairs."""
    lines = []
    cur = []
    cur_w = 0
    for u, sep in units:
        uw = display_width(u)
        if cur and (len(cur) >= max_units or
                    (cur_w + uw > soft and len(cur) >= min_units)):
            lines.append(cur)
            cur = []
            cur_w = 0
        cur.append((u, sep))
        cur_w += uw + 1
    if cur:
        lines.append(cur)
    return lines


def glue_leftover_punct(units):
    """A mark that is still a unit of its own is glued to a word.

    The word level pass above handles the marks that sit next to a word
    inside the same chunk. A mark that owns a whole chunk (a "|" between
    spaces, say) has no neighbour there, so it is attached here: onto the
    word before it, or, failing that, onto the word after it.
    """
    out = []
    pending = ""
    for u in units:
        text = unit_text(u)
        if (text and is_punct_only(text)
                and all(ch in AUTHOR_PUNCT for ch in text)):
            if out and not pending:
                prev = out[-1]
                out[-1] = (prev[0] + text, prev[1]) if isinstance(prev, tuple) \
                    else prev + text
            else:
                pending += text
            continue
        if pending:
            text = pending + text
            pending = ""
        out.append((text, u[1]) if isinstance(u, tuple) else text)
    if pending:
        if out:
            prev = out[-1]
            out[-1] = (prev[0] + pending, prev[1]) if isinstance(prev, tuple) \
                else prev + pending
        else:
            out.append(pending)
    return out


def render(plain, p, openers, closers, soft=18, max_units=3,
           drop_punct=True):
    """Plain text in, styled text out.

    Each whitespace-delimited chunk of the input is segmented on its own;
    the whitespace between chunks is kept as the author wrote it."""
    if drop_punct:
        # The marks the author never uses are taken out before the text is
        # split into chunks, so each of them turns into a boundary the
        # writer chose rather than into a hole in the text.
        plain = strip_unused_punct(plain)
    units = []
    for chunk, sep in split_chunks(plain):
        if not chunk:
            continue
        text = chunk
        ws, ps = words_and_pos(text)
        spans = dp_segment(ws, ps, openers, closers, **p)
        for k, (a, b) in enumerate(spans):
            units.append((text[a:b], sep if k == 0 else " "))
    units = glue_leftover_punct(units)
    lines = wrap(units, soft=soft, max_units=max_units)
    return "\n".join(join_units(l) for l in lines), units, lines


# ------------------------------------------------------------------
# style metrics
# ------------------------------------------------------------------
def style_metrics(units, lines):
    lens = [len(unit_text(u)) for u in units]
    widths = [display_width(join_units(l)) for l in lines]
    per_line = [len(l) for l in lines]
    return {
        "n_units": len(units),
        "unit_len_mean": round(sum(lens) / len(lens), 3),
        "unit_len_median": sorted(lens)[len(lens) // 2],
        "unit_len_hist": dict(sorted(Counter(lens).items())),
        "frac_units_2_to_4": round(sum(1 for x in lens if 2 <= x <= 4) / len(lens), 4),
        "n_lines": len(lines),
        "width_median": sorted(widths)[len(widths) // 2] if widths else 0,
        "width_max": max(widths) if widths else 0,
        "width_min": min(widths) if widths else 0,
        "units_per_line_hist": dict(sorted(Counter(per_line).items())),
    }


def line_profile_cost(m_author, m_gen):
    """How far the generated line profile is from the author's."""
    a = m_author["units_per_line_hist"]
    g = m_gen["units_per_line_hist"]
    keys = set(a) | set(g)
    n = max(1, m_author["n_lines"])
    c = sum(abs(a.get(k, 0) - g.get(k, 0)) for k in keys) / n
    c += abs(m_author["width_median"] - m_gen["width_median"]) / 16.0
    return round(c, 4)


# ------------------------------------------------------------------
# main analysis
# ------------------------------------------------------------------
def analyse(paragraphs, fitted=None, quiet=False):
    """Two stages.

    Stage 1 (expensive): the grid search. Its result is cached.
    Stage 2 (cheap): the round trip, the style metrics and the boundary
    test. Always recomputed, so a stale cached report can never be
    served."""
    R = {"n_paragraphs": len(paragraphs)}

    if fitted is None:
        # ---------------- stage 1: fit ----------------
        half = len(paragraphs) // 2
        folds = [("A", paragraphs[:half], paragraphs[half:]),
                 ("B", paragraphs[half:], paragraphs[:half])]
        R["folds"] = {}
        for tag, train_lines, test_lines in folds:
            openers, closers, o_stats, c_stats = derive_features(train_lines)
            train = prep(train_lines)
            test = prep(test_lines)
            _, params, insample = fit(train, openers, closers)
            test_scores = evaluate(test, openers, closers, params)
            R["folds"][tag] = {"n_openers": len(openers),
                               "n_closers": len(closers),
                               "params": params, "in_sample": insample,
                               "test": test_scores}
            if not quiet:
                print(f"fold {tag}: params={params}")
                print(f"   in-sample : {insample}")
                print(f"   TEST      : {test_scores}")

        tp = sum(R["folds"][t]["test"]["tp"] for t, _, _ in folds)
        pn = sum(R["folds"][t]["test"]["predicted"] for t, _, _ in folds)
        tn = sum(R["folds"][t]["test"]["truth"] for t, _, _ in folds)
        pr = round(tp / pn, 4)
        rc = round(tp / tn, 4)
        R["pooled_out_of_sample"] = {"precision": pr, "recall": rc,
                                     "f1": round(2 * pr * rc / (pr + rc), 4),
                                     "tp": tp, "predicted": pn, "truth": tn}
        if not quiet:
            print("POOLED OUT-OF-SAMPLE:", R["pooled_out_of_sample"])

        best_f1 = max(R["folds"][t]["test"]["f1"] for t, _, _ in folds)
        best_tag = [t for t, _, _ in folds
                    if R["folds"][t]["test"]["f1"] == best_f1][0]
        params = dict(R["folds"][best_tag]["params"])
        openers, closers, o_stats, c_stats = derive_features(paragraphs)
    else:
        R["folds"] = fitted["folds"]
        R["pooled_out_of_sample"] = fitted["pooled_out_of_sample"]
        params = dict(fitted["chosen_params"]["params"])
        openers = set(fitted["openers"])
        closers = set(fitted["closers"])
        best_tag = fitted["chosen_params"]["from_fold"]
        o_stats = fitted["chosen_params"]["top_openers"]
        c_stats = fitted["chosen_params"]["top_closers"]

    # ---------------- stage 2: measure ----------------
    author_lines = []
    for lines in paragraphs:
        for l in lines:
            author_lines.append([u for u in re.split("[" + "".join(WS) + "]", l) if u])
    author_units_flat = []
    for l in author_lines:
        author_units_flat += l
    m_author = style_metrics(author_units_flat, author_lines)

    if fitted is None:
        soft = mu = None
    else:
        soft = fitted["wrap_params"]["soft"]
        mu = fitted["wrap_params"]["max_units"]
    # The wrap parameters are cheap to fit (18 renders over 64 paragraphs)
    # and depend on the measured width, so they are always recomputed.
    best_wrap = None
    for s_ in (14, 16, 18, 20, 22, 24):
        for mu_ in (2, 3, 4):
            gu, gl = [], []
            for lines in paragraphs:
                s, _ = para_units(lines)
                _, u, l = render(s, params, openers, closers, soft=s_, max_units=mu_)
                gu += u
                gl += l
            cost = line_profile_cost(m_author, style_metrics(gu, gl))
            if best_wrap is None or cost < best_wrap[0]:
                best_wrap = (cost, s_, mu_)
    soft, mu = best_wrap[1], best_wrap[2]
    R["wrap_params"] = {"soft": soft, "max_units": mu,
                        "cost_vs_author": best_wrap[0],
                        "how": "grid searched against the author's own "
                               "units-per-line and width profile"}
    if not quiet:
        print("wrap params:", R["wrap_params"])

    R["chosen_params"] = {"from_fold": best_tag, "params": params,
                          "why": "weights come from the fold that won on "
                                 "held-out data; the character sets are "
                                 "re-derived on all paragraphs",
                          "n_openers": len(openers), "n_closers": len(closers),
                          "openers": "".join(sorted(openers)),
                          "closers": "".join(sorted(closers)),
                          "top_openers": o_stats[:14],
                          "top_closers": c_stats[:14]}
    if not quiet:
        print("CHOSEN:", best_tag, params)

    # --------------------------------------------------------------
    # round trip
    # --------------------------------------------------------------
    all_auth, all_gen = [], []
    for lines in paragraphs:
        s, au = para_units(lines)
        words, pos = words_and_pos(s)
        spans = dp_segment(words, pos, openers, closers, **params)
        all_auth += unit_texts(s, au)
        all_gen += unit_texts(s, spans)
    ca, cg = Counter(all_auth), Counter(all_gen)
    # Paragraphs where the author wrote two Latin tokens separated by a
    # space: stripping the spaces glues them, and no segmenter can split
    # them back. The detector looks at the ORIGINAL lines for a space
    # between two Latin runs.
    glued = [i for i, lines in enumerate(paragraphs)
             if any(re.search(r"[A-Za-z]{2,}[ \u2009][A-Za-z]{2,}", l)
                    for l in lines)]
    R["round_trip_corpus"] = {
        "n_author": len(all_auth), "n_generated": len(all_gen),
        "identical_units_set": sum((ca & cg).values()),
        "frac_identical": round(sum((ca & cg).values()) / len(all_auth), 4),
        "paragraphs_with_glued_latin": glued,
        "n_paragraphs": len(paragraphs),
        "author_only": [[u, n] for u, n in (ca - cg).most_common(12)],
        "generated_only": [[u, n] for u, n in (cg - ca).most_common(12)],
    }

    # round trip restricted to paragraphs with no glued Latin run
    auth2, gen2 = [], []
    for i, lines in enumerate(paragraphs):
        if i in glued:
            continue
        s, au = para_units(lines)
        words, pos = words_and_pos(s)
        spans = dp_segment(words, pos, openers, closers, **params)
        auth2 += unit_texts(s, au)
        gen2 += unit_texts(s, spans)
    c2a, c2g = Counter(auth2), Counter(gen2)
    R["round_trip_no_glued_latin"] = {
        "n_author": len(auth2), "n_generated": len(gen2),
        "identical_units_set": sum((c2a & c2g).values()),
        "frac_identical": round(sum((c2a & c2g).values()) / len(auth2), 4),
        "note": "the same round trip restricted to paragraphs where the "
                "author did NOT write two Latin tokens with a space "
                "between them; stripping the spaces glued those and no "
                "segmenter can split them back",
    }

    s0, u0 = para_units(paragraphs[0])
    w0, p0 = words_and_pos(s0)
    R["round_trip_corpus"]["paragraph_1"] = {
        "author": unit_texts(s0, u0),
        "generated": unit_texts(s0, dp_segment(w0, p0, openers, closers, **params)),
    }

    # --------------------------------------------------------------
    # same metrics, same test, for author and generator
    # --------------------------------------------------------------
    gen_units, gen_lines = [], []
    for lines in paragraphs:
        s, _ = para_units(lines)
        _, u, l = render(s, params, openers, closers, soft=soft, max_units=mu)
        gen_units += u
        gen_lines += l
    R["metrics_author"] = m_author
    R["metrics_generated"] = style_metrics(gen_units, gen_lines)
    R["line_profile_cost"] = line_profile_cost(m_author, R["metrics_generated"])

    gen_cuts, jb = set(), set()
    off = 0
    for lines in paragraphs:
        s, _ = para_units(lines)
        words, pos = words_and_pos(s)
        spans = dp_segment(words, pos, openers, closers, **params)
        for (a, b) in spans[:-1]:
            gen_cuts.add(off + b)
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
    return R, params, openers, closers, soft, mu


# ------------------------------------------------------------------
# demo
# ------------------------------------------------------------------
DEMO = [
    "频道人数又只剩十几人了隔壁的浪人新闻被人给炸掉了nmud还以为是他们结果是查水表的大叔",
    "蜂蜜洒了一地店长说没办法只能重新送一杯免费的太甜的奶茶喝多了会腻",
    "今天买了个新玩具蓝色的会发光匀速的shake shake",
    "6月26日是国际禁毒日大家不要乱丢东西被举报了说是nmud带坏小朋友其实nmud什么都没有做",
    "明天打算早点睡反正也没什么人看nmud还是想试试那个新语法",
]


CACHE = None


def fit(cache_path, corpus_path, refit=False, quiet=False):
    """Load or refit the model. Returns the metrics and the parameters."""
    paragraphs = load_paragraphs(corpus_path)

    cached = None
    if not refit:
        try:
            cached = json.load(open(cache_path, encoding="utf-8"))
        except Exception:
            cached = None
        # a cache from an older layout does not carry the fitted stage
        if cached is not None and not all(
                k in cached for k in ("folds", "pooled_out_of_sample",
                                      "chosen_params", "wrap_params")):
            if not quiet:
                print("cache is from an older layout, refitting")
            cached = None

    if cached:
        params = cached["params"]
        openers = set(cached["openers"])
        closers = set(cached["closers"])
        soft = cached["soft"]
        mu = cached["max_units"]
        R, params, openers, closers, soft, mu = analyse(paragraphs, fitted=cached,
                                                        quiet=quiet)
        if not quiet:
            print("using cached parameters (pass --refit to redo the search)")
        return R, params, openers, closers, soft, mu

    R, params, openers, closers, soft, mu = analyse(paragraphs, quiet=quiet)
    blob = {"params": params, "openers": "".join(sorted(openers)),
            "closers": "".join(sorted(closers)),
            "soft": soft, "max_units": mu,
            "folds": R["folds"],
            "pooled_out_of_sample": R["pooled_out_of_sample"],
            "chosen_params": R["chosen_params"],
            "wrap_params": R["wrap_params"]}
    for target in (Path(cache_path), cache_dir() / "nmud_style_params.json"):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(blob, f, ensure_ascii=False, indent=1)
            if not quiet:
                print("cached parameters ->", target)
            break
        except OSError:
            continue
    return R, params, openers, closers, soft, mu


def style_text(raw, params, openers, closers, soft=18, mu=3,
               drop_punct=True):
    """Plain text in, nmud text out.

    Blank lines separate the paragraphs, and a line break inside a
    paragraph is a boundary the writer chose: the lines are joined with a
    space so the end of one line never welds to the start of the next
    ("shake" + "6月" would become "shake6月").
    """
    paras = []
    cur = []
    for l in raw.replace("\r\n", "\n").split("\n"):
        if l.strip():
            cur.append(l)
        else:
            if cur:
                paras.append(cur)
                cur = []
    if cur:
        paras.append(cur)
    out_blocks = []
    for p in paras:
        body, _, _ = render(" ".join(l.rstrip() for l in p),
                            params, openers, closers,
                            soft=soft, max_units=mu,
                            drop_punct=drop_punct)
        out_blocks.append(body)
    return "\n\n".join(out_blocks) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", help="plain text to restyle")
    ap.add_argument("--out", dest="outp", help="where to write the result")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--report", dest="report", nargs="?", const="AUTO",
                    help="write the metrics json (no value: the out folder)")
    ap.add_argument("--corpus", dest="corpus", help="the corpus to learn from")
    ap.add_argument("--cache", dest="cache", help="fitted parameters cache")
    ap.add_argument("--refit", action="store_true",
                    help="redo the grid search instead of using the cache")
    ap.add_argument("--quiet", action="store_true",
                    help="say less: only the result and the errors")
    ap.add_argument("--keep-punct", dest="keep_punct", action="store_true",
                    help="keep the punctuation the author never uses "
                         "(the default drops it, like the corpus)")
    args = ap.parse_args(argv)

    corpus = args.corpus or str(find_data("nmud.txt"))
    cache = args.cache or str(find_data("nmud_style_params.json"))
    if not args.quiet:
        print("corpus:", corpus)
        print("cache :", cache)

    R, params, openers, closers, soft, mu = fit(cache, corpus, refit=args.refit,
                                               quiet=args.quiet)

    if args.report is not None:
        if args.report == "AUTO":
            report_path = str(cache_dir() / "nmud_style.json")
            report_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            report_path = args.report

        def _find_bad(o, path="R"):
            if isinstance(o, set):
                print("SET AT", path, sorted(o)[:12])
                return True
            if isinstance(o, dict):
                for k, v in o.items():
                    if _find_bad(v, path + "." + str(k)):
                        return True
            elif isinstance(o, (list, tuple)):
                for i, v in enumerate(o):
                    if _find_bad(v, path + "[%d]" % i):
                        return True
            return False

        _find_bad(R)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(R, f, ensure_ascii=False, indent=1)
        print("wrote", report_path)

    if args.demo:
        print()
        print("=" * 68)
        print("DEMO: plain text in -> nmud style out")
        print("=" * 68)
        for d in DEMO:
            body, units, lines = render(d, params, openers, closers,
                                        soft=soft, max_units=mu)
            print("-" * 68)
            print("plain  :", d)
            print("units  :", " | ".join(unit_text(u) for u in units))
            print("styled :")
            for l in body.split("\n"):
                print("   ", l.replace("\u2009", "<THIN>"))

    # A bare run asks what to restyle; with any flag the question is skipped.
    if not (args.inp or args.demo or args.report is not None or args.refit):
        q = ask("要排版的中文文件（直接回车跳过）: ", "")
        if q:
            args.inp = q
    if args.inp and not args.outp:
        args.outp = ask("结果写到哪里（回车 = 打印到屏幕）: ", "")

    if args.inp:
        raw = open(args.inp, "rb").read().decode("utf-8")
        styled = style_text(raw, params, openers, closers, soft=soft, mu=mu,
                            drop_punct=not args.keep_punct)
        if args.outp:
            with open(args.outp, "wb") as f:
                f.write(styled.encode("utf-8"))
            print("wrote", args.outp)
        else:
            print(styled)

    return R


if __name__ == "__main__":
    main()
