"""Exercise the interactive helpers of nlp_paths.

Run it with the answers on stdin:

    printf 'my answer\\nC:/path/to/nmud.txt\\n' | python -X utf8 test_nlp_paths.py
    python -X utf8 test_nlp_paths.py < /dev/null      # EOF: every question gives up

A subprocess with pipes is not an option here (the sandbox blocks it), so the
answers come from the shell instead.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nlp_paths

print("ask        ->", repr(nlp_paths.ask("question: ", "default")))
p = nlp_paths.locate_file("corpus", "no_such_file.txt")
print("located    ->", p)
o = nlp_paths.locate_out("result", "probe_out.json")
print("out        ->", o, "dir exists:", os.path.isdir(os.path.dirname(o)))
