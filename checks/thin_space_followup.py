# Follow-up on the pangu-spacing question.
#
# 1. show the context around the 4 lines that carry a thin space
# 2. check whether the thin spacing is CONSISTENT within each phrase
# 3. check Latin/digit next to Chinese punctuation (a pangu plugin would
#    not touch those, but the author's own spacing might)

import re
import unicodedata
import nlp_paths

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
THIN = "\u2009"

raw = open(CORPUS, encoding="utf-8").read()
lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def show(s):
    return s.replace(THIN, "<THIN>")


print("=" * 74)
print("CONTEXT AROUND THE 4 THIN-SPACE LINES")
print("=" * 74)
for target in (26, 46, 186, 235):
    for ln in range(max(1, target - 3), min(len(lines), target + 3) + 1):
        mark = ">>" if ln == target else "  "
        print("%s L%-4d %s" % (mark, ln, show(lines[ln - 1])))
    print("-" * 74)

print()
print("=" * 74)
print("IS THE THIN SPACING CONSISTENT WITHIN EACH PHRASE?")
print("=" * 74)

whole = "\n".join(lines)
for phrase in ("nmud", "xyn", "kira", "shake"):
    # every occurrence of the token, with the 6 characters around it
    for m in re.finditer(re.escape(phrase), whole):
        s = max(0, m.start() - 6)
        e = min(len(whole), m.end() + 6)
        seg = whole[s:e].replace("\n", "\\n")
        before = whole[m.start() - 1] if m.start() > 0 else "^"
        after = whole[m.end()] if m.end() < len(whole) else "$"
        tag = "THIN" if before == THIN else ("ASCII" if before == " " else before)
        tag2 = "THIN" if after == THIN else ("ASCII" if after == " " else after)
        if tag in ("THIN", "ASCII") or tag2 in ("THIN", "ASCII"):
            print("%-6s before=%-5s after=%-5s   %s" % (phrase, tag, tag2, show(seg)))
    print("-" * 74)

print()
print("=" * 74)
print("DIGIT / LATIN NEXT TO CHINESE PUNCTUATION")
print("=" * 74)
PUNCT = set("，。！？、；：""''（）《》「」【】…—～,.!?;:'\"()[]")
for ln, line in enumerate(lines, 1):
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        a_lat = a.isascii() and (a.isalpha() or a.isdigit())
        b_lat = b.isascii() and (b.isalpha() or b.isdigit())
        if (a_lat and b in PUNCT) or (b_lat and a in PUNCT):
            print("L%-4d %r   between %r and %r" % (ln, line, a, b))
print("(no output above = Latin/digit never touches Chinese punctuation directly)")

print()
print("=" * 74)
print("BYTE-LEVEL CONFIRMATION OF THE 6 THIN SPACES")
print("=" * 74)
for ln, line in enumerate(lines, 1):
    if THIN in line:
        print("L%d  %r" % (ln, show(line)))
        for i, ch in enumerate(line):
            if ch == THIN:
                print("      offset %d: U+%04X  between %r and %r"
                      % (i, ord(ch), line[i - 1], line[i + 1]))
