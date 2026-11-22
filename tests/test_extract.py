"""T2.2 — PDF/HTML extraction into candidate knowledge units (frozen samples)."""
import zlib

from geologia.knowledge.extract import (
    candidate_units,
    detect_language,
    extract_html,
    extract_pdf,
)
from geologia.knowledge.units import validate_unit

HTML_DOC = """<html><head><style>hide me</style></head><body>
<h1>Formations of the Sana'a basin</h1>
<p>The Ahwar sandstone unit reaches a thickness of 180 m in the eastern
outcrop belt, according to the measured section.</p>
<script>document.write("never");</script>
<table><tr><th>Unit</th><th>Age</th></tr>
<tr><td>Ahwar</td><td>Miocene</td></tr></table>
</body></html>"""


def _pdf_with_text(text: str) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    stream = zlib.compress(content)
    header = b"%PDF-1.4\n"
    obj = (b"1 0 obj << /Length " + str(len(stream)).encode() +
           b" >>\nstream\n" + stream + b"\nendstream\nendobj\n")
    return header + obj + b"trailer << >>\n%%EOF\n"


def test_html_blocks_and_tables():
    out = extract_html(HTML_DOC)
    assert any("Ahwar sandstone" in b for b in out["text_blocks"])
    assert "hide me" not in " ".join(out["text_blocks"])
    assert "never" not in " ".join(out["text_blocks"]), "script must be skipped"
    assert out["tables"] == [[["Unit", "Age"], ["Ahwar", "Miocene"]]]


def test_pdf_stream_text_extraction():
    out = extract_pdf(_pdf_with_text("The grit reaches 180 m thickness"))
    assert any("180 m" in b for b in out["text_blocks"])
    assert out["streams_total"] >= 1


def test_pdf_limits_are_declared_not_hidden():
    out = extract_pdf(_pdf_with_text("short"))
    assert out["limitations"], "v1 PDF limits must be stated in the payload"
    assert any("no layout tables" in x for x in out["limitations"])


def test_language_detection():
    assert detect_language("الصدع الطويل في حوض مأرب") == "ar"
    assert detect_language("The fault extends across the basin") == "en"


def test_candidates_are_schema_valid_and_short_quotes():
    blocks = [
        "The Ahwar sandstone unit reaches a thickness of 180 m in the "
        "eastern outcrop belt according to the measured section of the "
        "1984 mapping campaign and the accompanying report figures." * 2,
        "too short",
    ]
    res = candidate_units(
        {"text_blocks": blocks, "tables": []},
        source_id="src-abc123def456", license_status="open_access",
        topic="stratigraphy", region="Sana'a basin",
        doi_or_url="https://example.org/report", page_prefix="pdf",
        now_utc="2026-11-22T00:00:00Z")
    assert res["skipped_short"] == 1
    assert res["units"], "a long block must yield at least one candidate"
    for unit in res["units"]:
        validate_unit(unit)          # raises on any schema violation
        assert len(unit["quote"]["text"]) <= 300
        assert unit["review_status"] == "read"
        assert unit["confidence"] == "to_verify"
        assert unit["license_per_purpose"]["retrieval"] in (True, False)
        assert unit["unit_id"].startswith("ku-")


def test_candidates_from_table_rows_carry_positions():
    out = extract_html(HTML_DOC)
    res = candidate_units(
        {"text_blocks": out["text_blocks"], "tables": out["tables"]},
        source_id="src-abc123def456", license_status="public_domain",
        topic="stratigraphy", region="Sana'a basin", now_utc="2026-11-22T00:00:00Z")
    sections = [u["page_or_section"] for u in res["units"]]
    assert any("table-1" in s for s in sections), \
        "table rows must keep a locatable position for re-checking"
