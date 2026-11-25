"""slugs.py — names to URL fragments.

Its own module because both the generator and the validator need it, and the
validator is deliberately free of the generator's dependencies: `check.py`
must run and report on a machine where Jinja2 was never installed.
"""

from __future__ import annotations

import re
import unicodedata


# Letters that survive Unicode decomposition and so need saying by hand. NFKD
# turns é into e plus an accent, which we then drop — but Đ, ø and ß are not
# accented letters, they are letters, and decomposition leaves them alone.
# Without this, "Đà Nẵng" slugs to "-nng" and the page is unreachable.
TRANSLITERATE = str.maketrans({
    "Đ": "D", "đ": "d", "Ð": "D", "ð": "d", "Þ": "Th", "þ": "th",
    "Ø": "O", "ø": "o", "Æ": "Ae", "æ": "ae", "Œ": "Oe", "œ": "oe",
    "ß": "ss", "Ł": "L", "ł": "l", "Ħ": "H", "ħ": "h", "Ŋ": "N", "ŋ": "n",
    "Ə": "E", "ə": "e", "Ɛ": "E", "ɛ": "e", "Ƶ": "Z", "ƶ": "z",
    "ı": "i", "İ": "I",
    # Apostrophes vanish rather than becoming hyphens: L’Aquila is one word to
    # anyone reading the URL, and "l-aquila" reads like two.
    "'": "", "’": "", "ʼ": "", "‘": "",
})


def slugify(text: str) -> str:
    """A URL fragment from a name in any script this gazetteer uses.

    Accents are folded, not stripped blind: Besançon becomes besancon and Cần
    Thơ becomes can-tho, because the horn and the breve decompose away. What
    does not decompose is handled by TRANSLITERATE above.

    A name with no Latin letters at all — a key written only in Chinese, say —
    comes back empty, and the caller must notice rather than mint a page at a
    blank address. Hence the explicit empty string: it is a signal, not a slug.
    """
    folded = unicodedata.normalize("NFKD", text.translate(TRANSLITERATE))
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", stripped.lower())).strip("-")


def sort_key(text: str) -> tuple:
    """An ordering key that files an accented letter under its plain letter.

    Codepoint order puts Arhus, Evry, Osaka and Da Nang after Zurich, which is
    not an alphabet anybody reads. The folding the slugs already use does the
    right thing, and using it for both means a city sorts where its own URL
    says it lives: Da Nang is at /city/da-nang/ and sorts under D.

    Not `locale.strxfrm`, which depends on a locale having been generated on
    whichever machine runs the build, and not PyICU, which would be a second
    dependency for a generator that has one. This matches what the browser's
    own `localeCompare` does for these names, which matters because the city
    and country tables are sorted again in the browser when a reader clicks a
    column: the two orders have to agree.

    Accents still separate names that fold alike, as the second element, so
    Montreal comes before Montreal-with-an-accent rather than either order by
    chance. A name with no Latin letters at all sorts after those that have
    them, which is where a reader of an A-Z list looks for it.
    """
    folded = unicodedata.normalize("NFKD", text.translate(TRANSLITERATE))
    letters = "".join(c for c in folded if not unicodedata.combining(c)).casefold()
    if any("a" <= c <= "z" for c in letters):
        return (0, letters, text.casefold())
    return (1, letters or text.casefold(), text.casefold())
