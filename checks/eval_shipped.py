"""Measure the Python generator with the shipped parameters.

    python checks/eval_shipped.py [--units <file>]

This is the yardstick for the browser build: the same paragraphs, the
same parameters, the same unit level F1 against the author's own cuts.
checks/eval_shipped.py prints the Python number, web/check.js prints the
browser one; the two are directly comparable.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "nmud_style"))

import engine  # noqa: E402

WS = (" ", " ")


def load_paragraphs(path):
    raw = open(path, "rb").read().decode("utf-8").replace("\r\n", "\n")
    paras = []
    cur = []
    for line in raw.split("\n"):
        if line.strip():
            cur.append(line)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    return paras


def main():
    units_out = ""
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--units" and i + 1 < len(args):
            units_out = args[i + 1]

    model = json.load(
        open(os.path.join(ROOT, "nmud_style", "data", "nmud_style_params.json"),
             encoding="utf-8"))
    corpus = os.path.join(ROOT, "nmud_style", "data", "nmud.txt")
    paras = load_paragraphs(corpus)

    tp = pn = tn = 0
    unit_lines = []
    for lines in paras:
        stream, truth = engine.para_units(lines)
        words, _pos = engine.words_and_pos(stream)
        spans = engine.dp_segment(words, _pos, set(model["openers"]),
                                  set(model["closers"]), **model["params"])
        pred = {a for (a, _b) in spans}
        truth_set = {a for (a, _b) in truth}
        pn += len(pred)
        tn += len(truth_set)
        tp += len(pred & truth_set)
        unit_lines.extend(stream[a:b] for (a, b) in spans)

    precision = tp / pn if pn else 0
    recall = tp / tn if tn else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print("paragraphs       :", len(paras))
    print("precision        :", round(precision, 4))
    print("recall           :", round(recall, 4))
    print("f1               :", round(f1, 4))
    print("tp/pred/truth    :", tp, "/", pn, "/", tn)

    if units_out:
        with open(units_out, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(unit_lines) + "\n")
        print("units written    :", units_out)


if __name__ == "__main__":
    main()
