# Punctuation and particle inventory: the marks that survive into any
# sentence written in his voice.

import re
from collections import Counter
import nlp_paths

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
raw = open(CORPUS, encoding="utf-8").read()
text = raw.replace("\r\n", "\n").replace("\r", "\n")

print("=" * 74)
print("PUNCTUATION INVENTORY")
print("=" * 74)
punct = Counter()
for ch in text:
    cat = __import__("unicodedata").category(ch)
    if cat.startswith("P") or cat.startswith("S"):
        punct[ch] += 1
for k, v in punct.most_common():
    print("%3d  U+%04X  %s  (%s)" % (v, ord(k), k, __import__("unicodedata").name(k, "?")))
print()

print("=" * 74)
print("SENTENCE-FINAL PARTICLES (the last word of a paragraph)")
print("=" * 74)
paras = [p for p in text.split("\n\n") if p.strip()]
particles = Counter()
for p in paras:
    tail = p.replace("\n", " ").split()
    if tail:
        w = tail[-1]
        for pa in ("吗", "呀", "啦", "呢", "吧", "哦", "喔", "咯", "嘛"):
            if w.endswith(pa):
                particles[pa] += 1
                break
print(dict(particles))
print()

print("=" * 74)
print("QUESTION-FORM PARAGRAPHS: do they carry a question mark?")
print("=" * 74)
QM = ("吗", "呀", "为什么", "怎么", "什么", "有没有", "是不是")
q = 0
q_with_mark = 0
for p in paras:
    body = p.replace("\n", " ").strip()
    if any(m in body for m in QM):
        q += 1
        if "？" in body:
            q_with_mark += 1
print("paragraphs that read as a question: %d" % q)
print("of which carry U+FF1F (fullwidth question mark): %d" % q_with_mark)
print()

print("=" * 74)
print("ELLIPSIS")
print("=" * 74)
n_ell = text.count("…")
n_line_ell = len(re.findall(r"^…", text, re.M))
print("total U+2026: %d" % n_ell)
print("paragraphs that OPEN with a lone ellipsis: %d" % n_line_ell)
print()

print("=" * 74)
print("HOW THE AUTHOR REPLACES THE FIRST PERSON PRONOUN")
print("=" * 74)
for w in ("我", "我们", "咱", "俺", "本人", "在下"):
    n = text.count(w)
    if n:
        print("%3d  %s" % (n, w))
print("%3d  nmud" % text.count("nmud"))
