# Test the "pangu spacing" hypothesis for the 6 thin spaces.
#
# Pangu spacing (pan gu zhi bai) = a space between Chinese characters and
# Latin letters / digits. If a tool applied it mechanically, EVERY such
# boundary would carry a space. This script lists every CJK-to-Latin /
# CJK-to-digit boundary in the corpus with its context, and separates the
# ones that got an ordinary space from the ones that got a thin space.

import unicodedata
import nlp_paths

CORPUS = (nlp_paths.arg("--corpus")
          or nlp_paths.locate_file("corpus", "nmud.txt", "tools"))
THIN = "\u2009"

raw = open(CORPUS, encoding="utf-8").read()
lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def cls(ch):
    if ch.isascii() and ch.isalpha():
        return "LAT"
    if ch.isascii() and ch.isdigit():
        return "DIG"
    if ch in (" ", THIN):
        return "WS"
    if "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ":
        return "CJK"
    return "OTH"


rows = []
uns = []
for ln, line in enumerate(lines, 1):
    i = 0
    while i < len(line):
        if line[i] not in (" ", THIN):
            i += 1
            continue
        # line[i] is whitespace; left is the run before it, right the run after
        j = i
        while j > 0 and line[j - 1] not in (" ", THIN):
            j -= 1
        k = i + 1
        while k < len(line) and line[k] not in (" ", THIN):
            k += 1
        left_run, right_run = line[j:i], line[i + 1:k]
        if left_run and right_run:
            lc, rc = cls(left_run[-1]), cls(right_run[0])
            if (lc == "CJK" and rc in ("LAT", "DIG")) or \
               (lc in ("LAT", "DIG") and rc == "CJK"):
                rows.append({
                    "line": ln,
                    "space": "THIN" if line[i] == THIN else "ASCII",
                    "left": lc, "right": rc,
                    "left_run": left_run, "right_run": right_run,
                    "before": line[max(0, j - 8):j],
                    "after": line[k:k + 8],
                    "full": line,
                })
        # skip to the end of the right run
        i = k

thin = [r for r in rows if r["space"] == "THIN"]
ascii_ = [r for r in rows if r["space"] == "ASCII"]

print("total CJK<->LAT/DIG boundaries carrying a space: %d" % len(rows))
print("  ASCII space : %d" % len(ascii_))
print("  THIN space  : %d" % len(thin))
print()

# any boundary with NO space at all?
for ln, line in enumerate(lines, 1):
    for i in range(len(line) - 1):
        a, b = cls(line[i]), cls(line[i + 1])
        if (a == "CJK" and b in ("LAT", "DIG")) or \
           (a in ("LAT", "DIG") and b == "CJK"):
            uns.append((ln, line))
print("boundaries with NO space at all: %d" % len(uns))
for ln, line in uns:
    print("   line %d: %s" % (ln, line))
print()

print("=" * 74)
print("THE %d THIN SPACES" % len(thin))
print("=" * 74)
for r in thin:
    print("L%-4d %-10s  ...%-8s[[%s]]%-8s..." % (r["line"], r["left"] + "|" + r["right"],
                                                r["before"], r["space"], r["after"]))
    print("       %s" % r["full"])
print()

print("=" * 74)
print("ALL ASCII-SPACE BOUNDARIES")
print("=" * 74)
for r in ascii_:
    print("L%-4d %-10s  ...%-8s[[%s]]%-8s..." % (r["line"], r["left"] + "|" + r["right"],
                                                r["before"], r["space"], r["after"]))
print()


def tally(rs):
    d = {}
    for r in rs:
        k = r["left"] + "|" + r["right"]
        d[k] = d.get(k, 0) + 1
    return d


print("ASCII side combos:", tally(ascii_))
print("THIN  side combos:", tally(thin))
print("ASCII on %d distinct lines; THIN on %d distinct lines" %
      (len(set(r["line"] for r in ascii_)), len(set(r["line"] for r in thin))))
print()
print("every distinct line that carries a thin space:")
for ln in sorted(set(r["line"] for r in thin)):
    print("   L%d  %s" % (ln, lines[ln - 1]))
