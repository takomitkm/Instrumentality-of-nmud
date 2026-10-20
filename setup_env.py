"""Check this device, install what is missing, prove it works.

    python setup_env.py             check, install into .venv, self test
    python setup_env.py --check     only report, install nothing
    python setup_env.py --system    install into the running interpreter
    python setup_env.py --proxy 127.0.0.1:7897

The generator needs jieba (the segmenter) and pyperclip (the clipboard).
Everything else in checks/ is optional and only needed to redo the
corpus analysis.

Nothing outside this repository is touched: the environment lives in
.venv/ next to the code.
"""
import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
sys.path.insert(0, str(ROOT))

from nmud_style import envcheck  # noqa: E402

# The mirrors are tried in this order when the plain PyPI index is not
# reachable. The last one is the local proxy, which is what this network
# usually needs.
MIRRORS = [
    ("PyPI", None, None),
    ("Tsinghua", "https://pypi.tuna.tsinghua.edu.cn/simple", None),
    ("Aliyun", "https://mirrors.aliyun.com/pypi/simple/", None),
    ("PyPI via proxy", None, "http://127.0.0.1:7897"),
]


def venv_python(base=None):
    base = base or VENV
    if os.name == "nt":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def port_open(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run(cmd, cwd=None):
    """Run a command, return (returncode, output)."""
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True,
                          errors="replace")
    return proc.returncode, proc.stdout or ""


def pip_install(python, packages, index_url=None, proxy=None, user_site=False):
    cmd = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
    if user_site:
        cmd.append("--user")
    if index_url:
        cmd += ["--index-url", index_url]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd += list(packages)
    return run(cmd)


def install(python, packages, proxy=None, user_site=False):
    """Try every mirror until one works."""
    for name, index_url, mirror_proxy in MIRRORS:
        if proxy and not mirror_proxy:
            continue
        use_proxy = proxy or mirror_proxy
        if use_proxy and not port_open("127.0.0.1", 7897):
            continue
        label = name if not use_proxy else "%s (%s)" % (name, use_proxy)
        print("--- pip install via %s ---" % label)
        code, out = pip_install(python, packages, index_url, use_proxy, user_site)
        tail = [l for l in out.strip().splitlines() if l.strip()][-4:]
        for line in tail:
            print("    " + line)
        if code == 0:
            print("installed from %s" % label)
            return True
    return False


def self_test(python):
    """Run the generator on a known string and look at the result."""
    code = (
        "import sys;"
        "sys.path.insert(0, %r);"
        "from nmud_style import engine;"
        "c=str(engine.find_data('nmud.txt'));"
        "k=str(engine.find_data('nmud_style_params.json'));"
        "_,p,o,c2,s,m=engine.fit(k,c,quiet=True);"
        "t=engine.style_text('今天买了个新玩具，蓝色的。',p,o,c2,soft=s,mu=m);"
        "print(t.replace(chr(10),' / '))" % str(ROOT)
    )
    rc, out = run([str(python), "-c", code])
    if rc != 0:
        print("self test FAILED")
        print(out)
        return False
    print("self test ok:")
    print("    " + out.strip().splitlines()[-1])
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="only report the state of this device")
    ap.add_argument("--system", action="store_true",
                    help="install into the running interpreter, not .venv")
    ap.add_argument("--proxy", default="",
                    help="use this proxy for pip, e.g. 127.0.0.1:7897")
    ap.add_argument("--no-selftest", action="store_true")
    args = ap.parse_args(argv)

    print("=== nmud-style environment check ===")
    ready = envcheck.report()
    if args.check:
        return 0 if ready else 1

    missing = envcheck.missing_packages()
    if not missing:
        print("\nnothing to install, the environment is already complete.")
    else:
        print("\nmissing: %s" % ", ".join(missing))

    if args.system:
        python = Path(sys.executable)
        user_site = False
        print("installing into the running interpreter: %s" % python)
    else:
        user_site = False
        if not VENV.exists():
            print("\ncreating the environment: %s" % VENV)
            rc, out = run([sys.executable, "-m", "venv", str(VENV)])
            if rc != 0:
                # A sandbox or a locked down python can refuse the venv.
                # The generator still works from the running interpreter,
                # so fall back to it instead of giving up.
                print("    the environment could not be created:")
                for line in out.strip().splitlines()[-3:]:
                    print("    " + line)
                print("    falling back to the running interpreter")
                python = Path(sys.executable)
                user_site = True
        if user_site is False:
            python = venv_python()
            if not python.exists():
                print("the environment was not created: %s" % python)
                return 1

    if missing:
        if not install(python, missing, proxy=args.proxy, user_site=user_site):
            print("\nthe install failed. Try the proxy that works here:")
            print("    python setup_env.py --proxy 127.0.0.1:7897")
            return 1

    # The package itself is optional: running from the repo root works
    # without it. Installing it only adds the `nmud-style` command.
    print("\ninstalling the package (for the nmud-style command)")
    rc, out = pip_install(python, ["-e", str(ROOT)])
    if rc != 0:
        print("    (skipped, the repo still works: python -m nmud_style)")

    if not args.no_selftest:
        print()
        if not self_test(python):
            return 1

    print("\nready.")
    print("    one click : %s"
          % ("nmud-style.bat" if os.name == "nt" else "./nmud-style.sh"))
    print("    command  : nmud-style --clip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
