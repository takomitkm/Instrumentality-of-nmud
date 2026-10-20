"""Command line for the nmud style generator.

    nmud-style --in plain.txt --out styled.txt   restyle a file
    nmud-style --clip                            clipboard in, out, back
    nmud-style --demo                            the built in examples
    nmud-style --check-env                       is this device ready?
    nmud-style --refit --report                  refit the model, write the metrics

Everything else (the parameters, the corpus, the result files) has a
default that works from a checkout and from an installed package.
"""
import sys

from . import engine


def clipboard_flow(keep_punct=False, quiet=False):
    """Read the clipboard, restyle it, put it back.

    Returns the exit code: 0 ok, 1 failed, 2 nothing to do.
    """
    try:
        import pyperclip
    except ImportError:
        print("pyperclip is missing. Run the setup again "
              "(python setup_env.py).", file=sys.stderr)
        return 2
    try:
        text = pyperclip.paste()
    except Exception as exc:
        print("cannot read the clipboard: %s" % exc, file=sys.stderr)
        return 1
    if not text or not text.strip():
        print("the clipboard is empty, nothing to do.", file=sys.stderr)
        return 2
    corpus = str(engine.find_data("nmud.txt"))
    cache = str(engine.find_data("nmud_style_params.json"))
    _, params, openers, closers, soft, mu, lb = engine.fit(cache, corpus,
                                                          quiet=True)
    styled = engine.style_text(text, params, openers, closers,
                                soft=soft, mu=mu,
                                drop_punct=not keep_punct, lb=lb)
    try:
        pyperclip.copy(styled)
    except Exception as exc:
        print("cannot write the clipboard: %s" % exc, file=sys.stderr)
        return 1
    if not quiet:
        print(styled)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    # The flags the package adds on top of the engine's own command line.
    if "--check-env" in argv:
        from . import envcheck
        argv.remove("--check-env")
        return 0 if envcheck.report() else 1

    if "--clip" in argv:
        argv.remove("--clip")
        keep = "--keep-punct" in argv
        return clipboard_flow(keep_punct=keep, quiet="--quiet" in argv)

    result = engine.main(argv)
    # the engine hands back its metrics; the exit code is what a caller
    # needs, and a dict would end up printed on stderr by sys.exit
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
