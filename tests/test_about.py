import pytest

from geologia import __version__
from geologia.about import STATUS, banner
from geologia.cli import main


def test_banner_bilingual_carries_all_three_notices():
    text = banner("both")
    assert "GEOLOGIA" in text
    assert __version__ in text
    # status: construction, honestly stated in both languages
    assert "قيد الإنشاء" in text
    assert "under construction" in text
    # support appeal in both languages
    assert "الدعم أو التبني" in text
    assert "support or" in text.lower()
    # rights notice in both languages
    assert "حقوق الابتكار محفوظة" in text
    assert "written license" in text


def test_banner_language_selections():
    ar = banner("ar")
    en = banner("en")
    assert "قيد الإنشاء" in ar and "under construction" not in ar
    assert "under construction" in en and "قيد الإنشاء" not in en
    assert "ترخيص كتابي" in ar
    assert "written license" in en


def test_status_constant_is_honest():
    assert STATUS == "construction"


def test_cli_about_exits_zero_and_prints_notice(capsys):
    code = main(["about"])
    assert code == 0
    out = capsys.readouterr().out
    assert "GEOLOGIA" in out
    assert "قيد الإنشاء" in out
    assert "under construction" in out


def test_cli_about_lang_flag(capsys):
    assert main(["about", "--lang", "en"]) == 0
    out = capsys.readouterr().out
    assert "under construction" in out
    assert "قيد الإنشاء" not in out


@pytest.mark.parametrize("lang", ["ar", "en", "both"])
def test_cli_about_all_langs_valid(lang, capsys):
    assert main(["about", "--lang", lang]) == 0
    assert capsys.readouterr().out.strip()
