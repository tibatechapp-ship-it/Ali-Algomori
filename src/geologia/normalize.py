# Arabic/Latin text normalization for deterministic keyword matching.
# Purpose: make matching robust to tashkeel (diacritics), hamza variants,
# ta-marbuta, alef maqsura and tatweel — so "المِيَاهُ الجَوْفِيَّة" and
# "المياه الجوفية" produce the same planner result.
import re

# Tashkeel + Quranic annotation marks + small high marks + tatweel.
_AR_DIACRITICS = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")

# Hamza/letter variants folded onto a canonical base letter.
_AR_VARIANTS = str.maketrans({
    "أ": "ا",  # alef with hamza above
    "إ": "ا",  # alef with hamza below
    "آ": "ا",  # alef with madda
    "ٱ": "ا",  # alef wasla
    "ؤ": "و",  # waw with hamza
    "ئ": "ي",  # ya with hamza
    "ى": "ي",  # alef maqsura -> ya
    "ة": "ه",  # ta marbuta -> ha
})

# Anything that is not a word character or Arabic punctuation becomes a space.
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_arabic(text: str) -> str:
    """Fold Arabic orthographic variants onto canonical forms."""
    text = _AR_DIACRITICS.sub("", text)
    return text.translate(_AR_VARIANTS)


def normalize_text(text: str) -> str:
    """Canonical form for matching: lowercase Latin + normalized Arabic,
    punctuation replaced by single spaces, whitespace collapsed."""
    text = text.lower()
    text = normalize_arabic(text)
    text = _NON_WORD.sub(" ", text)
    return " ".join(text.split())


def is_normalized_idempotent(text: str) -> bool:
    """True when normalize_text(normalize_text(x)) == normalize_text(x)."""
    once = normalize_text(text)
    return once == normalize_text(once)
