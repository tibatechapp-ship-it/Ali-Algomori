from geologia.normalize import is_normalized_idempotent, normalize_arabic, normalize_text


def test_tashkeel_stripped():
    # Note: ta-marbuta folds to ha by design (both text and keywords fold alike).
    assert normalize_arabic("المِيَاهُ الجَوْفِيَّة") == "المياه الجوفيه"


def test_hamza_variants_fold_to_alef():
    assert normalize_arabic("أبار إبرات آبار ٱمرأ") == "ابار ابرات ابار امرا"


def test_waw_ya_hamza_fold():
    assert normalize_arabic("ؤلوم ئميل") == "ولوم يميل"


def test_ta_marbuta_and_alef_maqsura():
    assert normalize_arabic("خريطة مصطدة") == "خريطه مصطده"
    assert normalize_arabic("على") == "علي"


def test_tatweel_removed():
    assert normalize_arabic("مــيــاه") == "مياه"


def test_latin_lowercased_and_punctuation_spaced():
    assert normalize_text("Cross-Section & LAS!") == "cross section las"


def test_full_normalize_matches_plain_text():
    # The exact reason this module exists: diacritised text must match.
    assert normalize_text("المِيَاهُ الجَوْفِيَّة حَوْل الْمِنْطَقَة") == normalize_text(
        "المياه الجوفية حول المنطقة"
    )


def test_idempotent():
    assert is_normalized_idempotent("مَيَاه AQUIFER-3d")
