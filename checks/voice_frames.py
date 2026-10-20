# Extract the author's sentence frames.
#
# The report shows his vocabulary cannot be reused (366 of 403 distinct
# units occur once), so a "voice" template has to be built from sentence
# SKELETONS rather than from words: what his sentences open with, how
# long they run, how they close, and which rhetorical moves he makes.

import re
from collections import Counter
import nlp_paths

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
raw = open(CORPUS, encoding="utf-8").read()
lines = [l for l in raw.replace("\r\n", "\n").split("\n")]

# paragraphs = blocks separated by blank lines
paras, cur = [], []
for l in lines:
    if l.strip() == "":
        if cur:
            paras.append(cur)
            cur = []
    else:
        cur.append(l)
if cur:
    paras.append(cur)

print("paragraphs: %d" % len(paras))
sizes = Counter(len(p) for p in paras)
print("paragraph line counts: %s" % dict(sorted(sizes.items())))
print()

# ---- sentences: split a paragraph's text on terminal punctuation ----
ENDERS = "。！？…"
sentences = []
for pi, p in enumerate(paras):
    text = "".join(p)
    # the author writes units separated by spaces; keep them, the space
    # is where his own pauses are
    buf = ""
    for ch in text:
        buf += ch
        if ch in ENDERS:
            s = buf.strip()
            if s:
                sentences.append((pi, s))
            buf = ""
    if buf.strip():
        sentences.append((pi, buf.strip()))

print("sentences: %d" % len(sentences))
lens = [len(s.replace(" ", "")) for _, s in sentences]
print("sentence length (chars, spaces removed): min %d max %d mean %.1f" %
      (min(lens), max(lens), sum(lens) / len(lens)))
print("histogram: %s" % dict(sorted(Counter(lens).items())))
print()

print("=" * 74)
print("ALL SENTENCES")
print("=" * 74)
for pi, s in sentences:
    print("P%-3d %s" % (pi + 1, s))
print()

# ---- opening frames: first 3 characters of each sentence ----
print("=" * 74)
print("OPENING FRAMES (first 3 characters, spaces kept)")
print("=" * 74)
opens3 = Counter()
opens2 = Counter()
for _, s in sentences:
    t = s.lstrip()
    opens3[t[:3]] += 1
    opens2[t[:2]] += 1
for k, v in opens3.most_common(25):
    print("%2d  %s" % (v, k))
print()

# ---- closing frames: last 3 characters before the terminal mark ----
print("=" * 74)
print("CLOSING FRAMES (last 3 characters before the terminal mark)")
print("=" * 74)
closes = Counter()
for _, s in sentences:
    t = s.rstrip()
    if t and t[-1] in ENDERS:
        t = t[:-1]
    closes[t[-3:]] += 1
for k, v in closes.most_common(25):
    print("%2d  %s" % (v, k))
print()

# ---- questions ----
print("=" * 74)
print("QUESTIONS")
print("=" * 74)
for pi, s in sentences:
    if "？" in s:
        print("P%-3d %s" % (pi + 1, s))
print()

# ---- the paragraph-final unit: how he ends a thought ----
print("=" * 74)
print("PARAGRAPH-FINAL UNIT (what each paragraph ends on)")
print("=" * 74)
lasts = Counter()
for p in paras:
    tail = p[-1].split()
    if tail:
        lasts[tail[-1]] += 1
for k, v in lasts.most_common(20):
    print("%2d  %s" % (v, k))
print()

# ---- paragraph-opening unit ----
print("=" * 74)
print("PARAGRAPH-OPENING UNIT (how each paragraph starts)")
print("=" * 74)
firsts = Counter()
for p in paras:
    head = p[0].split()
    if head:
        firsts[head[0]] += 1
for k, v in firsts.most_common(20):
    print("%2d  %s" % (v, k))
print()

# ---- discourse markers: how often a unit is a pure interjection ----
print("=" * 74)
print("UNITS THAT ARE WHOLE DISCOURSE MARKERS")
print("=" * 74)
allunits = Counter()
for p in paras:
    for line in p:
        for u in line.split():
            allunits[u] += 1
for k, v in allunits.most_common(40):
    print("%2d  %s" % (v, k))
