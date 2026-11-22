# Text & table extraction (T2.2): PDF/HTML -> candidate knowledge units.
#
# Doctrine (from the approved plan):
# - The quotation stays SHORT and verbatim with its position, to preserve
#   licenses (short-quote doctrine, <= 300 chars enforced by the schema).
# - The full original text stays in the source library beside its fingerprint;
#   it is NOT copied into units.
# - Candidates are born as review_status="read" + confidence="to_verify":
#   extraction never confers scientific truth on a claim.
# - PDF v1 limits are DECLARED, not hidden: running-order text only, no
#   layout tables, no CMap-encoded fonts, scanned pages yield nothing.
from __future__ import annotations

import hashlib
import re
import zlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

from geologia.knowledge.licenses import PURPOSES, purpose_allowed
from geologia.knowledge.units import validate_unit

MAX_QUOTE_CHARS = 280          # schema allows 300; we stay under it
MIN_BLOCK_CHARS = 20           # a 3-word fragment is not a claim candidate

_AR = (0x0600, 0x06FF)
_LAT = (0x0041, 0x007A)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
class _HTMLText(HTMLParser):
    """Collect paragraph-level text blocks and table rows (stdlib only)."""

    _BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li",
                   "figcaption", "summary"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: List[str] = []
        self.tables: List[List[List[str]]] = []
        self._buf: List[str] = []
        self._skip = 0
        self._in_cell = False
        self._cell: List[str] = []
        self._row: List[str] = []
        self._table: List[List[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif tag in self._BLOCK_TAGS:
            self._flush()
        elif tag == "table":
            self._flush()
            self._table = []
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCK_TAGS:
            self._flush()
        elif tag in ("td", "th"):
            self._in_cell = False
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = []
        elif tag == "tr":
            if any(c for c in self._row):
                self._table.append(self._row)
            self._row = []
        elif tag == "table":
            if self._table:
                self.tables.append(self._table)
            self._table = []
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_cell:
            self._cell.append(data)
        else:
            self._buf.append(data)

    def _flush(self):
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if text:
            self.blocks.append(text)

    def close(self):
        super().close()
        self._flush()


def extract_html(html: str) -> dict:
    parser = _HTMLText()
    parser.feed(html)
    parser.close()
    return {"text_blocks": parser.blocks, "tables": parser.tables}


# ---------------------------------------------------------------------------
# PDF (best-effort text extraction, declared limits)
# ---------------------------------------------------------------------------
_PDF_STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
_PDF_STR_RE = re.compile(rb"\((?:\\[\s\S]|[^\\()])*\)|<[0-9A-Fa-f\s]+>")
_ESCAPES = {b"n": "\n", b"r": "\r", b"t": "\t", b"b": "\b", b"f": "\f",
            b"(": "(", b")": ")", b"\\": "\\"}
_PDF_LIMITS = (
    "PDF v1: text in running order only - no layout tables or columns",
    "PDF v1: CMap-encoded / subset fonts without ToUnicode are dropped "
    "(counted in streams_dropped)",
    "PDF v1: scanned pages are images - they yield no text here",
)


def _unescape_pdf_string(raw: bytes) -> str:
    if raw.startswith(b"("):
        body = raw[1:-1]
        out: List[str] = []
        i = 0
        while i < len(body):
            b = body[i:i + 1]
            if b == b"\\" and i + 1 < len(body):
                nxt = body[i + 1:i + 2]
                if nxt in _ESCAPES:
                    out.append(_ESCAPES[nxt])
                    i += 2
                    continue
                if nxt.isdigit():
                    oct_digits = body[i + 1:i + 4]
                    m = re.match(rb"[0-7]{1,3}", oct_digits)
                    if m:
                        out.append(chr(int(m.group(0), 8)))
                        i += 1 + len(m.group(0))
                        continue
                i += 2
                continue
            out.append(body[i:i + 1].decode("latin-1"))
            i += 1
        return "".join(out)
    hexbody = re.sub(rb"\s", b"", raw[1:-1])
    if len(hexbody) % 2 == 0 and len(hexbody) >= 2:
        blob = bytes.fromhex(hexbody.decode("ascii"))
        try:
            return blob.decode("utf-16-be")
        except UnicodeDecodeError:
            return blob.decode("latin-1")
    return ""


def _pdf_stream_text(content: bytes) -> Optional[str]:
    if b"Tj" not in content and b"TJ" not in content:
        return None
    parts: List[str] = []
    for m in _PDF_STR_RE.finditer(content):
        s = _unescape_pdf_string(m.group(0))
        if s:
            parts.append(s)
        if len(parts) > 20000:            # bounded extraction
            break
    text = " ".join(" ".join(parts).split())
    return text or None


def extract_pdf(data: bytes) -> dict:
    blocks: List[str] = []
    streams_total = 0
    streams_dropped = 0
    for m in _PDF_STREAM_RE.finditer(data):
        streams_total += 1
        raw = m.group(1)
        try:
            content = zlib.decompress(raw)
        except zlib.error:
            content = raw                     # uncompressed content stream
        text = _pdf_stream_text(content)
        if text:
            blocks.append(text)
        else:
            streams_dropped += 1
        if len(blocks) >= 2000:               # bounded extraction
            break
    return {
        "text_blocks": blocks,
        "tables": [],
        "streams_total": streams_total,
        "streams_dropped": streams_dropped,
        "limitations": list(_PDF_LIMITS),
    }


# ---------------------------------------------------------------------------
# Language + candidate units
# ---------------------------------------------------------------------------
def detect_language(text: str) -> str:
    if not text:
        return "other"
    n = len(text)
    ar = sum(1 for c in text if _AR[0] <= ord(c) <= _AR[1]) / max(n, 1)
    if ar >= 0.25:
        return "ar"
    latin = sum(1 for c in text if _LAT[0] <= ord(c) <= _LAT[1]) / max(n, 1)
    return "en" if latin >= 0.4 else "other"


def _short_quote(text: str, limit: int = MAX_QUOTE_CHARS) -> str:
    if len(text) <= limit:
        return text
    window = text[:limit]
    for sep in (". ", "؟ ", "۔ ", ". ", "؛ "):
        pos = window.rfind(sep)
        if pos >= limit // 2:
            return window[:pos + 1].strip()
    pos = window.rfind(" ")
    return (window[:pos] if pos >= limit // 2 else window).strip()


def candidate_units(extraction: dict, *, source_id: str,
                    license_status: str, topic: str, region: str,
                    doi_or_url: Optional[str] = None,
                    source_version: Optional[str] = None,
                    page_prefix: str = "src",
                    language: Optional[str] = None,
                    now_utc: Optional[str] = None) -> dict:
    """Map extracted text blocks onto schema-v1 candidate knowledge units.

    Every candidate is a VERBATIM short quote tied to its position inside the
    fingerprinted source: the unit never becomes a redistribution channel.
    """
    now = now_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    legs = {p: purpose_allowed(license_status, p)[0] for p in PURPOSES}
    units: List[dict] = []
    seen_ids: Dict[str, int] = {}
    skipped_short = 0
    rejected: List[dict] = []

    def section_for(i: int, kind: str) -> str:
        return f"{page_prefix}:{kind}-{i:04d}"

    # (text, section) pairs: paragraphs keep block positions, table rows keep
    # their own table-row position so any reader can re-check the quote.
    positioned: List[Tuple[str, str]] = [
        (b, section_for(i, "block"))
        for i, b in enumerate(extraction.get("text_blocks") or [], start=1)
    ]
    for t_i, table in enumerate(extraction.get("tables") or [], start=1):
        for r_i, row in enumerate(table, start=1):
            positioned.append(
                ("table cell row: " + " | ".join(row),
                 f"{page_prefix}:table-{t_i}-row-{r_i:03d}"))

    for text, section in positioned:
        if len(text) < MIN_BLOCK_CHARS:
            skipped_short += 1
            continue
        quote = _short_quote(text)
        lang = language or detect_language(quote)
        digest = hashlib.sha256(
            f"{source_id}|{section}|{quote}".encode("utf-8")).hexdigest()[:12]
        unit_id = f"ku-{digest}"
        if unit_id in seen_ids:
            seen_ids[unit_id] += 1
            unit_id = f"{unit_id}-{seen_ids[unit_id]}"
        else:
            seen_ids[unit_id] = 1
        unit = {
            "unit_id": unit_id,
            "claim": quote,
            "source_id": source_id,
            "page_or_section": section,
            "doi_or_url": doi_or_url,
            "language": lang,
            "region": region,
            "topic": topic,
            "confidence": "to_verify",
            "review_status": "read",
            "license": license_status,
            "extracted_at_utc": now,
            "source_version": source_version,
            "license_per_purpose": legs,
            "quote": {"text": quote, "page_or_section": section},
        }
        try:
            units.append(validate_unit(unit))
        except ValueError as exc:
            rejected.append({"section": section, "error": str(exc)})

    return {
        "units": units,
        "skipped_short": skipped_short,
        "rejected_candidates": rejected,
        "generated_from_positions": len(positioned),
    }
