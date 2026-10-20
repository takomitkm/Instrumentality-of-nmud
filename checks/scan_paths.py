"""Scan the scripts for leftover absolute paths."""
import os
import re

PAT = re.compile(r"[A-Za-z]:[\\/]")

targets = [f for f in sorted(os.listdir("."))
           if f.endswith((".py", ".ps1", ".cfg"))]

for f in targets:
    hits = []
    for i, line in enumerate(open(f, encoding="utf-8"), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if PAT.search(line):
            hits.append((i, s))
    print("%-22s %d" % (f, len(hits)))
    for i, s in hits:
        print("   %4d  %s" % (i, s))
