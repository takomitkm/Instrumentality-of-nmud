"""nmud-style: restyle Chinese text into the nmud forum style.

The author of the corpus writes in a very particular way: words are
grouped into short units, the units are separated by a single space, and
a line holds two to four units. This package reproduces that layout.

    nmud-style --in plain.txt --out styled.txt
    nmud-style --clip          # clipboard in, nmud style out, back again
    nmud-style --demo
    nmud-style --check-env     # is this device ready?
"""
__version__ = "1.0.0"

__all__ = ["__version__"]
