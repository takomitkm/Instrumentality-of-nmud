"""One shot: show what the segmentation does with punctuation."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nmud_style as ns

# the fitted parameters ship with the repository; NLP_CACHE overrides
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get(
    "NLP_CACHE",
    os.path.join(HERE, os.pardir, "nmud_style", "data", "nmud_style_params.json"))
cache = json.load(open(CACHE, encoding="utf-8"))
params = cache["params"]
openers = set(cache["openers"])
closers = set(cache["closers"])

TEXTS = [
    "下一个nmud，何必是nmud",
    "复现不了的词汇：500单元403个不同，366个只出现一次（90.8%生词）",
    "又有点…害怕",
    "那…好像也不完全是坏事？",
    "突然灵机一动…！",
    "排在那个很火的“象语”后面",
]

for text in TEXTS:
    print("=" * 60)
    print("TEXT", text)
    for chunk, sep in ns.split_chunks(text):
        print("  CHUNK %r sep=%r" % (chunk, sep))
        ws, ps = ns.words_and_pos(chunk)
        print("    WORDS", ws)
        spans = ns.dp_segment(ws, ps, openers, closers, **params)
        print("    SPANS", spans)
        for k, (a, b) in enumerate(spans):
            print("      unit %d %r" % (k, "".join(ws[a:b])))
