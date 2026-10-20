"""Where the nmud tools look for their files, and how they ask for them.

No absolute path is written down anywhere. Every file is looked up next to
the script that needs it (or in the tools/ and out/ folders beside it), and
anything that is not there is asked for interactively.

    corpus        <here>/nmud.txt  or  <here>/tools/nmud.txt
                  or  <parent>/nmud.txt  or  <parent>/tools/nmud.txt
    results       <here>/out/<name>  or  <parent>/out/<name>
    hanlp models  <here>/hanlp_models  or  <parent>/tools/hanlp_models

Command line flags win over everything:

    python nmud_style.py --corpus my.txt --out my.json
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)


def arg(flag, default=None):
    """Read "--flag VALUE" off the command line."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def candidates(name, *subdirs):
    """Places a file may live, in priority order."""
    out = []
    for base in (HERE, PARENT):
        for sub in ("",) + subdirs:
            out.append(os.path.join(base, sub, name))
    return out


def find(name, *subdirs):
    """The first existing candidate, else the first one as a default."""
    c = candidates(name, *subdirs)
    for p in c:
        if os.path.isfile(p):
            return p
    return c[0]


def ask(prompt, default=""):
    """Ask a question. Returns None when there is no console to ask."""
    try:
        s = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("  (no console input)")
        return None
    return s or default


def locate_file(prompt, name, *subdirs):
    """An existing file: found next to the script, or asked for."""
    p = find(name, *subdirs)
    if os.path.isfile(p):
        return p
    while True:
        q = ask("%s (not found) [%s]: " % (prompt, p), p)
        if q is None:
            raise SystemExit("cannot find %s" % name)
        if os.path.isfile(q):
            return q
        print("  not found: %s" % q)


def locate_dir(prompt, name, *subdirs):
    """A directory: found next to the script, or asked for."""
    c = candidates(name, *subdirs)
    for p in c:
        if os.path.isdir(p):
            return p
    while True:
        q = ask("%s (not found) [%s]: " % (prompt, c[0]), c[0])
        if q is None:
            return c[0]
        if os.path.isdir(q):
            return q
        print("  not found: %s" % q)


def locate_out(prompt, name, *subdirs):
    """A path to write to. The folder is created if it is missing."""
    p = find(name, *subdirs)
    folder = os.path.dirname(os.path.abspath(p))
    if folder and not os.path.isdir(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            q = ask("%s (cannot create %s) [%s]: " % (prompt, folder, p), p)
            if q is None:
                raise SystemExit("cannot create %s" % folder)
            p = q
    return p
