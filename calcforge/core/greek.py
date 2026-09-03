"""One Greek letter, one name, however it was typed.

φ is the capacity reduction factor on every page of a New Zealand structural
calculation, and there are four ways to put it on a page: type ``phi``, press
the symbol key, paste ``φ`` (U+03C6) out of a standard, or paste ``ϕ``
(U+03D5) out of a different one. Unicode says the last two are different
characters. To the engineer they are the same letter, and a document where
``φ := 0.9`` on one line and ``ϕ·N`` on the next quietly reads two variables
is worse than useless — it is wrong in a way nobody will spot.

So every Greek letter is folded to one spelling before anything is parsed:
the plain lower-case name it would be typed as. What is *shown* is the letter
— :data:`calcforge.core.mathrender.GREEK` puts it back — so the page reads as
it should while the document holds one name for it.
"""
from __future__ import annotations

# The letters, by their spelled name. Capitals keep their own names, because
# Δ and δ are genuinely different things on a calculation sheet.
LETTERS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lamda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "omicron": "ο",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ", "Epsilon": "Ε",
    "Zeta": "Ζ", "Eta": "Η", "Theta": "Θ", "Iota": "Ι", "Kappa": "Κ",
    "Lamda": "Λ", "Mu": "Μ", "Nu": "Ν", "Xi": "Ξ", "Omicron": "Ο",
    "Pi": "Π", "Rho": "Ρ", "Sigma": "Σ", "Tau": "Τ", "Upsilon": "Υ",
    "Phi": "Φ", "Chi": "Χ", "Psi": "Ψ", "Omega": "Ω",
}

# The other codepoints Unicode has for the same letters. Each is the one a
# standard, a word processor or a font substitution is liable to leave behind.
# µ and Ω are deliberately not here. "µm" is a micrometre and "Ω" is an ohm
# far more often than either is a bare letter, and the unit reader already
# turns them into the prefix and the unit they are. A letter that is usually a
# unit is not a letter this can safely fold.
VARIANTS = {
    "ϕ": "phi",        # GREEK PHI SYMBOL, the one most PDFs use for φ
    "ϑ": "theta",      # GREEK THETA SYMBOL
    "ϰ": "kappa",      # GREEK KAPPA SYMBOL
    "ϱ": "rho",        # GREEK RHO SYMBOL
    "ς": "sigma",      # final sigma — the same letter, at the end of a word
    "ϵ": "epsilon",    # GREEK LUNATE EPSILON SYMBOL
    "ϖ": "pi",         # GREEK PI SYMBOL
    "ϐ": "beta",       # GREEK BETA SYMBOL
    "∆": "Delta",      # INCREMENT, U+2206 — not the same codepoint as Δ
    "∇": "nabla",
    "λ": "lamda",      # Python cannot have a name called "lambda"
    "Λ": "Lamda",
}

# Every character that means a Greek letter, mapped to the one name for it.
TO_NAME: dict[str, str] = {letter: name for name, letter in LETTERS.items()}
TO_NAME.update(VARIANTS)

# What is written for a name that Python could not otherwise hold.
ALIASES = {"lambda": "lamda", "lambda_": "lamda", "Lambda": "Lamda"}


def fold(text: str) -> str:
    """Rewrite every Greek letter in *text* as its spelled name.

    Only whole characters are touched: ``φ`` becomes ``phi`` and ``σ_y``
    becomes ``sigma_y``, while a word that merely contains those letters in
    prose is not something this is ever asked about.
    """
    if not text:
        return text
    out = []
    for character in text:
        out.append(TO_NAME.get(character, character))
    return "".join(out)


def has_greek(text: str) -> bool:
    return any(character in TO_NAME for character in (text or ""))


def name_of(letter: str) -> str:
    """The one name for a Greek character, or "" if it is not one."""
    return TO_NAME.get(letter, "")
