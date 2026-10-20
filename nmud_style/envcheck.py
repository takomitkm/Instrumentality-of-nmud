"""What does this device need, and what does it have?

The same list drives two things:
  * `nmud-style --check-env` reports the state of the device
  * setup_env.py installs whatever is missing

The generator itself only needs jieba (the segmenter) and pyperclip (the
clipboard). The cross checkers in checks/ need more, and are optional.
"""
import importlib
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name, what it is for
REQUIRED = [
    ("jieba", "the segmenter that finds the word boundaries"),
    ("pyperclip", "reading and writing the clipboard"),
]
OPTIONAL = [
    ("thulac", "a second segmenter, to cross check the analysis"),
    ("pkuseg", "a third segmenter, to cross check the analysis"),
    ("hanlp", "a fourth segmenter, to cross check the analysis"),
]
DATA_FILES = ["nmud.txt", "nmud_style_params.json"]


def module_state(names):
    """(present, missing) for a list of module names."""
    present, missing = [], []
    for name, _ in names:
        try:
            importlib.import_module(name)
            present.append(name)
        except Exception:
            missing.append(name)
    return present, missing


def data_state():
    """(present, missing) for the data files inside the package."""
    present, missing = [], []
    for name in DATA_FILES:
        if (ROOT / "nmud_style" / "data" / name).exists():
            present.append(name)
        else:
            missing.append(name)
    return present, missing


def report(stream=sys.stdout):
    """Print the state of this device. Returns True when it is ready."""
    out = stream.write
    out("python    : %s (%s)\n"
        % (platform.python_version(), sys.executable))
    out("platform  : %s\n" % platform.platform())
    out("repo      : %s\n" % ROOT)

    present, missing = module_state(REQUIRED)
    for name, why in REQUIRED:
        mark = "ok" if name in present else "MISSING"
        out("need      : %-10s %s   (%s)\n" % (name, mark, why))
    for name, why in OPTIONAL:
        try:
            importlib.import_module(name)
            mark = "ok"
        except Exception:
            mark = "not installed"
        out("optional  : %-10s %s   (%s)\n" % (name, mark, why))

    present, missing = data_state()
    for name in DATA_FILES:
        mark = "ok" if name in present else "MISSING"
        out("data      : %-22s %s\n" % (name, mark))

    ready = not module_state(REQUIRED)[1] and not data_state()[1]
    out("result    : %s\n"
        % ("ready, run nmud-style --clip" if ready
           else "not ready, run setup (setup.bat / setup.sh / setup_env.py)"))
    return ready


def missing_packages():
    """The pip names of the modules this device still needs."""
    names = {"jieba": "jieba", "pyperclip": "pyperclip"}
    return [names[m] for m in module_state(REQUIRED)[1] if m in names]
