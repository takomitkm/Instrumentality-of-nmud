# Consistency check for the report.
#
# 1. every quoted corpus line must appear verbatim in nmud.txt
# 2. every number the report attributes to a script must match the JSON
# 3. no stale strings from the earlier version of the report
# 4. LF line endings, no BOM
#
# A fenced block is a corpus quote only if it sits in sections 1-6 (section
# 7 shows GENERATED output, which by definition is not in the corpus) and
# does not look like a shell command, a parameter dump or a frequency
# display.

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXAMPLES = os.path.join(ROOT, "examples")

REPORT = os.path.join(ROOT, "nmud_corpus_report.md")
CORPUS = os.path.join(ROOT, "nmud_style", "data", "nmud.txt")
for i, a in enumerate(sys.argv):
    if a == "--corpus" and i + 1 < len(sys.argv):
        CORPUS = sys.argv[i + 1]

rules = json.load(open(os.path.join(HERE, "nmud_rules.json"), encoding="utf-8"))
gen = json.load(open(os.path.join(HERE, "generative_model.json"), encoding="utf-8"))
sty = json.load(open(os.path.join(HERE, "nmud_style.json"), encoding="utf-8"))

raw = open(CORPUS, encoding="utf-8").read()
corpus_all = "\n".join(l.replace("\u2009", " ").strip() for l in raw.split("\n"))

rep = open(REPORT, encoding="utf-8", newline="").read()
fails, oks = [], []


def check(name, cond, detail=""):
    (oks if cond else fails).append(f"{name}{(': ' + detail) if detail else ''}")


def is_display(bl):
    """A data display (character frequency table) or a shell/parameter line."""
    if re.match(r"^[A-Za-z0-9_./\\:<>=\"'|, \[\]{}=+-]+$", bl):
        return True
    if re.match(r"^python ", bl):
        return True
    if bl.startswith("w_"):
        return True
    # frequency display: "n 30   的 12   很 10"  (single chars with counts)
    if re.match(r"^[A-Za-z的很也一不这有好就只说自日要没蜂太什又是不为然人在会样里次点用但于还而因所]{1,3} \d+(\s+|$)", bl):
        return True
    return False


# --------------------------------------------------------------- 1. quotes
head, sep, tail = rep.partition("## 7. ")
quote_region = head
quoted = 0
for b in re.findall(r"```\n(.*?)```", quote_region, re.S):
    for bl in b.split("\n"):
        bl = bl.strip()
        if not bl or is_display(bl):
            continue
        # strip a "L26   " line-number prefix
        m_ln = re.match(r"^L(\d+)\s+(.*)$", bl)
        if m_ln:
            bl = m_ln.group(2).strip()
            if not bl:
                continue
        norm = bl.replace("<THIN>", "\u2009").replace("\u2009", " ")
        norm = norm.replace("　", " ")
        if norm in corpus_all:
            quoted += 1
            continue
        # a segmentation display: units separated by " | "
        parts = [p.strip() for p in norm.split("|")]
        if len(parts) > 1 and all(p in corpus_all for p in parts if p):
            quoted += 1
            continue
        # a prefixed comparison line: the author's side must be in the
        # corpus, the model's side is the point of the comparison and is
        # expected to differ
        m = re.match(r"^(作者|模型|plain|units|styled)\s*[:：]\s*(.*)$", norm)
        if m:
            pp = [p.strip() for p in m.group(2).split("|")]
            if m.group(1) == "模型":
                continue
            if all(p in corpus_all for p in pp if p):
                quoted += 1
                continue
        fails.append(f"quote not in corpus: {bl[:70]!r}")
check("corpus quotes found", quoted >= 12, f"{quoted} matched")

# ------------------------------------------------------- 2. numbers vs JSON
segs = {s["segmenter"]: s for s in rules["segmenters"]}
pooled = sty["pooled_out_of_sample"]
foldA, foldB = sty["folds"]["A"], sty["folds"]["B"]
ma, mg = sty["metrics_author"], sty["metrics_generated"]
rt, rt2 = sty["round_trip_corpus"], sty["round_trip_no_glued_latin"]

num_checks = [
    ("pooled P", "0.7992", pooled["precision"]),
    ("pooled R", "0.8200", pooled["recall"]),
    ("pooled F1", "0.8095", pooled["f1"]),
    ("foldA F1", "0.8133", foldA["test"]["f1"]),
    ("foldB F1", "0.8061", foldB["test"]["f1"]),
    ("foldA P", "0.8133", foldA["test"]["precision"]),
    ("foldA R", "0.8133", foldA["test"]["recall"]),
    ("foldB P", "0.7868", foldB["test"]["precision"]),
    ("foldB R", "0.8263", foldB["test"]["recall"]),
    ("author mean len", "3.116", ma["unit_len_mean"]),
    ("gen mean len", "3.055", mg["unit_len_mean"]),
    ("author 2-4 frac", "95.8%", round(ma["frac_units_2_to_4"] * 100, 1)),
    ("gen 2-4 frac", "98.0%", round(mg["frac_units_2_to_4"] * 100, 1)),
    ("gen units", "510", mg["n_units"]),
    ("author width med", "16", ma["width_median"]),
    ("gen width med", "15", mg["width_median"]),
    ("round trip identical", "367", rt["identical_units_set"]),
    ("round trip clean identical", "356", rt2["identical_units_set"]),
    ("round trip clean author", "484", rt2["n_author"]),
    ("jieba ws", "97.67%", round(segs["jieba"]["ws_cuts_on_boundary"] * 100, 2)),
    ("jieba line", "98.49%", round(segs["jieba"]["line_cuts_on_boundary"] * 100, 2)),
    ("thulac ws", "95.02%", round(segs["thulac"]["ws_cuts_on_boundary"] * 100, 2)),
    ("pkuseg ws", "95.02%", round(segs["pkuseg"]["ws_cuts_on_boundary"] * 100, 2)),
    ("hanlp ws", "98.01%", round(segs["hanlp"]["ws_cuts_on_boundary"] * 100, 2)),
    ("hanlp line", "98.99%", round(segs["hanlp"]["line_cuts_on_boundary"] * 100, 2)),
    ("jieba density", "55.13%", round(segs["jieba"]["boundary_density"] * 100, 2)),
    ("thulac density", "62.32%", round(segs["thulac"]["boundary_density"] * 100, 2)),
    ("pkuseg density", "60.27%", round(segs["pkuseg"]["boundary_density"] * 100, 2)),
    ("hanlp density", "57.45%", round(segs["hanlp"]["boundary_density"] * 100, 2)),
    ("random mean", "55.15%", round(rules["null_model_random_cuts"]["mean"] * 100, 2)),
    ("old model F1", "0.5074", 0.5074),
    ("baseline F1", "0.5065", 0.5065),
]
def _as_number(text):
    """The report writes 0.8095 and 95.8%; the JSON stores 0.8095 and 0.958."""
    return float(text.rstrip("%"))


for name, text, value in num_checks:
    # the string must be in the report AND it must still be what the JSON
    # says: a refit that moves a number fails here until the report follows
    in_report = text in rep
    # the table above stores the value in the same unit the report writes
    # it: percentages as percentages, ratios as ratios
    agrees = abs(value - _as_number(text)) < 0.051 if text.endswith("%") \
        else abs(value - _as_number(text)) < 5e-4
    check(name, in_report and agrees,
          f"{text!r} missing (json={value})" if not in_report
          else f"json={value} disagrees with the report")

# the baseline row of the first model must still be in the report
check("baseline row present", "0.3419" in rep and "0.9767" in rep)

# ------------------------------------------------------- 3. stale strings
stale = [
    "两种空白字符分工不同",
    "拉丁/数字与汉字之间用细空格",
    "细空格只用在拉丁/数字与汉字的交界处",
    "汉字之间的语义停顿一律用普通空格",
    "无法用简单规则复刻切分",
    "规则模型留出 F1 0.507，与",
    "描述性规律强，但生成性规则不足",
]
for s in stale:
    check(f"stale gone: {s[:26]}", s not in rep)

check("old negative result kept but reframed",
      "两者持平" in rep and "这个结论后来被推翻了" in rep)

# the "de" counts must be recomputed from the corpus, not trusted
units = []
for line in raw.split("\n"):
    for u in re.split("[ \u2009]", line.replace("\r", "")):
        if u:
            units.append(u)
n_end = sum(1 for u in units if u.endswith("\u7684"))
n_start = sum(1 for u in units if u.startswith("\u7684"))
n_alone = sum(1 for u in units if u == "\u7684")
check("units total 500", len(units) == 500, str(len(units)))
check("de-at-end count", f"| {n_end} |" in rep, f"{n_end}")
check("de-at-start count", f"| {n_start} |" in rep, f"{n_start}")
check("de never standalone", n_alone == 0 and "从不单独成一个单元（0 次）" in rep)

# --------------------------------------------------------- 4. file hygiene
b = open(REPORT, "rb").read()
check("no BOM", b[:3] != b"\xef\xbb\xbf")
check("no CRLF", b"\r\n" not in b)
check("exactly one H1", rep.count("\n# ") + rep.startswith("# ") == 1)
check("all sections present", all(h in rep for h in [
    "## 0. 一句话结论", "## 1. 语料与切分口径", "## 2. 空格规律",
    "## 3. 换行规律", "## 4. 用词与排列规律",
    "## 5. 能不能用规则复刻？（留出验证）", "## 6. 结论与边界",
    "## 7. 复现：用这套规律写出同样的句子", "## 附：工具链"]))
check("no raw U+2009 in report", "\u2009" not in rep,
      "count=%d" % rep.count("\u2009"))

# the Latin/digit boundary count must be recomputed from the corpus
LAT_DIG = 0
ASCII_S = 0
THIN_S = 0
for line in raw.replace("\r\n", "\n").split("\n"):
    i = 0
    while i < len(line):
        if line[i] not in (" ", "\u2009"):
            i += 1
            continue
        j = i
        while j > 0 and line[j - 1] not in (" ", "\u2009"):
            j -= 1
        k = i + 1
        while k < len(line) and line[k] not in (" ", "\u2009"):
            k += 1
        if j < i and k > i + 1:
            a, b2 = line[i - 1], line[i + 1]
            a_l = a.isascii() and (a.isalpha() or a.isdigit())
            b_l = b2.isascii() and (b2.isalpha() or b2.isdigit())
            a_c = "\u4e00" <= a <= "\u9fff"
            b_c = "\u4e00" <= b2 <= "\u9fff"
            if (a_c and b_l) or (a_l and b_c):
                LAT_DIG += 1
                if line[i] == "\u2009":
                    THIN_S += 1
                else:
                    ASCII_S += 1
        i = k
check("Latin/digit boundary count is 66", LAT_DIG == 66, str(LAT_DIG))
check("thin space count is 6", THIN_S == 6, str(THIN_S))
check("ordinary space count is 60", ASCII_S == 60, str(ASCII_S))
check("report states 66", "66 处" in rep and "65 处" not in rep)

# ---- the voice layer (7.6): every claim recomputed from the corpus ----
txt = raw.replace("\r\n", "\n")
for name, ch, want in [("period", "\u3002", 0), ("comma", "\uff0c", 0),
                        ("enumeration comma", "\u3001", 0),
                        ("semicolon", "\uff1b", 0), ("colon", "\uff1a", 0),
                        ("question mark", "\uff1f", 1),
                        ("exclamation", "\uff01", 1),
                        ("ellipsis", "\u2026", 6),
                        ("left quote", "\u201c", 4),
                        ("right quote", "\u201d", 4)]:
    check("voice: %s count is %d" % (name, want), txt.count(ch) == want,
          "got %d" % txt.count(ch))

paras = [p for p in txt.split("\n\n") if p.strip()]
check("voice: 64 paragraphs", len(paras) == 64, str(len(paras)))

QM = ("\u5417", "\u5440", "\u4e3a\u4ec0\u4e48", "\u600e\u4e48", "\u4ec0\u4e48",
      "\u6709\u6ca1\u6709", "\u662f\u4e0d\u662f")
q = sum(1 for p in paras if any(m in p for m in QM))
q_mark = sum(1 for p in paras if any(m in p for m in QM) and "\uff1f" in p)
check("voice: 19 question paragraphs", q == 19, str(q))
check("voice: no question mark on them", q_mark == 0, str(q_mark))

check("voice: nmud 46 times", txt.count("nmud") == 46, str(txt.count("nmud")))
check("voice: wo 2 times", txt.count("\u6211") == 2, str(txt.count("\u6211")))
check("voice: women 2 times", txt.count("\u6211\u4eec") == 2,
      str(txt.count("\u6211\u4eec")))

heads = [p.replace("\n", " ").split()[0] for p in paras]
CONN = ("为什么", "而且", "虽然", "于是",
        "因为", "但是", "但", "然后", "不过",
        "所以", "也就是说")
conn = sum(1 for h in heads if h.startswith(CONN))
nm = sum(1 for h in heads if h.startswith("nmud"))
check("voice: 27 connective-opened paragraphs", conn == 27, str(conn))
check("voice: 8 nmud-opened paragraphs", nm == 8, str(nm))
check("voice: 47 distinct paragraph heads", len(set(heads)) == 47, str(len(set(heads))))

tails = [p.replace("\n", " ").split()[-1] for p in paras]
check("voice: 64 distinct paragraph closings", len(set(tails)) == 64,
      str(len(set(tails))))

ENDERS = "\u3002\uff01\uff1f\u2026"
sents = []
for p in paras:
    buf = ""
    for ch in p.replace("\n", ""):
        buf += ch
        if ch in ENDERS:
            sents.append(buf.strip())
            buf = ""
    if buf.strip():
        sents.append(buf.strip())
lens = [len(s.replace(" ", "")) for s in sents]
check("voice: mean sentence length 22.3",
      abs(sum(lens) / len(lens) - 22.3) < 0.05,
      "%.1f" % (sum(lens) / len(lens)))
check("voice: longest sentence 39", max(lens) == 39, str(max(lens)))

# the generated demo must not glue Chinese to Latin/digits
for demo in ("demo_styled.txt", "demo2_styled.txt", "demo3_styled.txt", "demo4_styled.txt"):
    d = open(os.path.join(EXAMPLES, demo), encoding="utf-8").read()
    bad = 0
    for i in range(len(d) - 1):
        a, b = d[i], d[i + 1]
        if a.isspace() or b.isspace():
            continue
        aw = a.isascii() and (a.isalpha() or a.isdigit())
        bw = b.isascii() and (b.isalpha() or b.isdigit())
        ac = "\u4e00" <= a <= "\u9fff"
        bc = "\u4e00" <= b <= "\u9fff"
        if (ac and bw) or (aw and bc):
            bad += 1
    check("%s has no glued CJK/Latin" % demo, bad == 0, "violations=%d" % bad)

# a percent sign belongs to the number it follows: the author treats a
# foreign token as one atom, so 90.8% must stay one unit
for demo in ("demo3_styled.txt", "demo4_styled.txt"):
    d = open(os.path.join(EXAMPLES, demo), encoding="utf-8").read()
    check("%s keeps 90.8%% together" % demo, "90.8%" in d and "90.8 %" not in d)

# ------------------------------------------- 5. the punctuation rule
# The author uses four kinds of punctuation and no others, and never lets
# a mark stand in a unit of its own.
CJK_PUNCT = set("。，；：（）《》"
                "〈〉「」『』·—"
                "～‘’“”…？！")
check("corpus: 句号 0", "。" not in raw, str(raw.count("。")))
check("corpus: 逗号 0", "，" not in raw, str(raw.count("，")))
check("corpus: 顿号 0", "、" not in raw, str(raw.count("、")))
check("corpus: 分号 0", "；" not in raw, str(raw.count("；")))
check("corpus: 冒号 0", "：" not in raw, str(raw.count("：")))
check("corpus: 括号 0", "（" not in raw and "）" not in raw)
check("corpus: 省略号 6", raw.count("…") == 6, str(raw.count("…")))
check("corpus: 问号 1", raw.count("？") == 1, str(raw.count("？")))
check("corpus: 感叹号 1", raw.count("！") == 1, str(raw.count("！")))
check("corpus: 引号 4 对", raw.count("“") == 4 and raw.count("”") == 4,
      "%d/%d" % (raw.count("“"), raw.count("”")))

# no unit of the author is nothing but punctuation
punct_units = [u for u in units
               if u and all(ch in CJK_PUNCT for ch in u)]
check("corpus: no punctuation-only unit", not punct_units, str(punct_units[:5]))

# and the generator must not produce one either
for demo in ("demo_styled.txt", "demo2_styled.txt", "demo3_styled.txt",
             "demo4_styled.txt", "demo3_keep.txt"):
    d = open(os.path.join(EXAMPLES, demo), encoding="utf-8").read()
    toks = [t for t in d.replace(chr(10), " ").split() if t]
    bad = [t for t in toks if all(ch in CJK_PUNCT for ch in t)]
    check("%s has no standalone punctuation unit" % demo, not bad, str(bad[:5]))

# the default run must reproduce the hand-typed punctuation-free version
d3 = open(os.path.join(EXAMPLES, "demo3_styled.txt"), encoding="utf-8").read()
d4 = open(os.path.join(EXAMPLES, "demo4_styled.txt"), encoding="utf-8").read()
check("demo3 default == the hand-typed punctuation-free run", d3 == d4)

# the report has to state the rule
check("report: the punctuation rule is stated",
      "标点按作者自己的用法处理" in rep and "从不独立成单元" in rep)
check("report: --keep-punct is documented", "--keep-punct" in rep)

print("PASS %d" % len(oks))
print("FAIL %d" % len(fails))
for f in fails:
    print("  -", f)
