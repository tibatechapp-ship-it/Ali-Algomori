# File reception security layer — the gate every uploaded byte must pass
# BEFORE it can become a dataset record.
#
# Binding policy (ADR-0005, v0.5.0): reception security answers "is this file
# safe to accept and inspect?", the format validators answer "is this file
# internally intact?", and NEITHER answers "are the geological results
# correct?" — that remains the exclusive job of the pinned scientific
# reference tests behind the certification gate. CI green proves code paths,
# not science.
#
# Four dimensions, each with explicit refusal codes:
#   1. size limits      — per-file cap + empty refusal (SEC_TOO_LARGE)
#   2. content sniffing — magic bytes, never the extension (SEC_EXT_MISMATCH,
#                         SEC_UNKNOWN_MAGIC, SEC_HTML_EMBEDDED)
#   3. archive safety   — zip-bomb ratios, path traversal, symlink entries,
#                         encrypted members (SEC_ZIP_BOMB, SEC_PATH_TRAVERSAL,
#                         SEC_ARCHIVE_SYMLINK, SEC_ARCHIVE_ENCRYPTED,
#                         SEC_ARCHIVE_CORRUPT)
#   4. hygiene          — filename sanitization incl. bidi control marks,
#                         NUL bytes, pathological lines, TIFF metadata
#                         reporting + structural stripping (SEC_NAME_REFUSED,
#                         SEC_NAME_SANITIZED, SEC_CONTROL_CHARS,
#                         SEC_LINE_TOO_LONG, META_PRESENT/META_NONE/META_STRIPPED)
#
# Strict parsing guarantees: content is only ever read as bytes, struct
# fields, or via json.loads/csv — never executed, never eval'd, never
# expanded beyond the caps below. All caps are env-tunable but always
# bounded: every value is clamped into a per-limit [min, max] range
# (v0.15.1) — no environment value can push a cap out of its domain.
from __future__ import annotations

import hashlib
import os
import re
import stat
import struct
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Policy limits (env-tunable, always bounded)
# ---------------------------------------------------------------------------
DEFAULT_MAX_UPLOAD_BYTES = 100 * (1 << 20)          # 100 MiB per file
DEFAULT_MAX_ARCHIVE_RATIO = 100                     # per-entry expansion cap
DEFAULT_MAX_ARCHIVE_ENTRIES = 64                    # entry count cap
DEFAULT_MAX_ARCHIVE_UNCOMPRESSED = 1 << 30          # 1 GiB total expansion
DEFAULT_MAX_LINE_BYTES = 1 << 20                    # 1 MiB per text line


def bounded_env_int(name: str, default: int,
                    minimum: int, maximum: int) -> int:
    """Env-tunable integer limit that is ALWAYS bounded.

    Unset/empty or non-integer values fall back to `default`; a parsed
    integer outside [minimum, maximum] is clamped into range. This turns
    "always bounded" from a description into a fact: no environment
    value — negative, zero, absurd, or garbage — can push a cap below
    `minimum` or above `maximum`.
    """
    raw = (os.environ.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def max_upload_bytes() -> int:
    return bounded_env_int("GEOLOGIA_MAX_UPLOAD_BYTES",
                           DEFAULT_MAX_UPLOAD_BYTES, 1, 1 << 30)


def max_archive_ratio() -> int:
    return bounded_env_int("GEOLOGIA_MAX_ARCHIVE_RATIO",
                           DEFAULT_MAX_ARCHIVE_RATIO, 2, 10_000)


def max_archive_entries() -> int:
    return bounded_env_int("GEOLOGIA_MAX_ARCHIVE_ENTRIES",
                           DEFAULT_MAX_ARCHIVE_ENTRIES, 1, 4096)


def max_archive_uncompressed() -> int:
    return bounded_env_int("GEOLOGIA_MAX_ARCHIVE_UNCOMPRESSED",
                           DEFAULT_MAX_ARCHIVE_UNCOMPRESSED,
                           1 << 20, 1 << 33)


def max_line_bytes() -> int:
    return bounded_env_int("GEOLOGIA_MAX_LINE_BYTES",
                           DEFAULT_MAX_LINE_BYTES, 256, 1 << 24)


# ---------------------------------------------------------------------------
# Refusal codes (stable contract; tests assert them)
# ---------------------------------------------------------------------------
RF = {
    "SEC_TOO_LARGE": "error",
    "SEC_EMPTY_FILE": "error",
    "SEC_EXT_MISMATCH": "error",
    "SEC_UNKNOWN_MAGIC": "error",
    "SEC_HTML_EMBEDDED": "error",
    "SEC_CONTROL_CHARS": "error",
    "SEC_LINE_TOO_LONG": "error",
    "SEC_ZIP_BOMB": "error",
    "SEC_PATH_TRAVERSAL": "error",
    "SEC_ARCHIVE_SYMLINK": "error",
    "SEC_ARCHIVE_ENCRYPTED": "error",
    "SEC_ARCHIVE_CORRUPT": "error",
    "SEC_NAME_REFUSED": "error",
    "SEC_NAME_SANITIZED": "warning",
    "SEC_SIZE_OK": "info",
    "SEC_MAGIC_MATCH": "info",
    "SEC_ARCHIVE_OK": "info",
    "SEC_NAME_OK": "info",
    "SEC_CONTENT_VALID": "info",
    "SEC_CONTENT_INVALID": "error",
    "META_PRESENT": "info",
    "META_NONE": "info",
    "META_STRIPPED": "info",
}


def _rfinding(code: str, message: str) -> dict:
    return {"code": code, "severity": RF[code], "message": message}


# ---------------------------------------------------------------------------
# 1. filename sanitization
# ---------------------------------------------------------------------------
# Unicode bidi/invisible marks must never survive into stored filenames:
# they can visually reorder a name like "cod.las" into "las.doc".
_BIDI_MARKS = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff\u00ad]")
_RESERVED_WIN = {"con", "prn", "aux", "nul",
                 *(f"com{i}" for i in range(1, 10)),
                 *(f"lpt{i}" for i in range(1, 10))}
_MAX_NAME_BYTES = 120


def sanitize_filename(name: str) -> Tuple[str, List[str]]:
    """Return (safe_name, flags). Never trust the client name: take the base
    name only, strip bidi/control marks and path separators, refuse empty or
    reserved results. Flags record what changed, for the evidence log."""
    flags: List[str] = []
    original = str(name)
    base = re.split(r"[\\/]+", original)[-1]
    if base != original:
        flags.append("path_components_removed")
    cleaned = _BIDI_MARKS.sub("", base)
    if cleaned != base:
        flags.append("bidi_or_hidden_marks_removed")
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)
    cleaned = cleaned.strip(" .")
    cleaned = re.sub(r"\s+", "_", cleaned)
    if cleaned != base:
        flags.append("normalized")
    stem = Path(cleaned).stem.lower()
    if stem in _RESERVED_WIN:
        cleaned = f"_{cleaned}"
        flags.append("reserved_name_prefixed")
    if not cleaned or cleaned in (".", ".."):
        return "", ["refused_empty_after_sanitization"]
    if len(cleaned.encode("utf-8")) > _MAX_NAME_BYTES:
        suffix = Path(cleaned).suffix
        stem_budget = _MAX_NAME_BYTES - len(suffix.encode("utf-8"))
        cleaned = Path(cleaned).stem.encode("utf-8")[:stem_budget].decode(
            "utf-8", errors="ignore") + suffix
        flags.append("truncated_to_120_bytes")
    if cleaned.startswith("-"):
        cleaned = "_" + cleaned[1:]
        flags.append("leading_dash_replaced")
    return cleaned, flags


# ---------------------------------------------------------------------------
# 2. content sniffing (magic bytes — the extension is never trusted)
# ---------------------------------------------------------------------------
def sniff_content(path: Path) -> Tuple[str, str]:
    """Classify content by magic bytes -> (kind, detail).
    kind: tiff | zip | gzip | text | binary_unknown"""
    with path.open("rb") as fh:
        head = fh.read(16)
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff", "TIFF magic (II/MM; structure checked separately)"
    if head[:4] == b"PK\x03\x04":
        return "zip", "ZIP local file header"
    if head[:2] == b"\x1f\x8b":
        return "gzip", "gzip magic"
    if head[:16] == b"SQLite format 3\x00":
        return "sqlite", "SQLite container magic (GeoPackage candidate)"
    try:
        sample = path.open("rb").read(64 << 10)
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return "binary_unknown", "no known magic and not valid UTF-8"
    if "\x00" in text:
        # UTF-8 text carrying NUL bytes: still text (parseable), but the NUL
        # is corruption — the text branch refuses it via SEC_CONTROL_CHARS.
        return "text", "valid UTF-8 text carrying NUL bytes (control-char corruption)"
    return "text", "valid UTF-8 text (no known binary magic)"


def _looks_like_html(text: str) -> bool:
    low = text[:4096].lstrip().lower()
    return (low.startswith("<!") or low.startswith("<html")
            or low.startswith("<svg"))


# ---------------------------------------------------------------------------
# 3. archive safety analysis (structural only — never extracts to disk)
# ---------------------------------------------------------------------------
def scan_archive(path: Path) -> List[dict]:
    findings: List[dict] = []
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile as exc:
        return [_rfinding("SEC_ARCHIVE_CORRUPT",
                          f"unreadable ZIP structure: {exc}")]
    if len(infos) > max_archive_entries():
        findings.append(_rfinding(
            "SEC_ZIP_BOMB",
            f"{len(infos)} entries exceeds the {max_archive_entries()}-entry cap"))
    total_unc = 0
    for info in infos:
        if info.flag_bits & 0x1:
            findings.append(_rfinding("SEC_ARCHIVE_ENCRYPTED",
                                      f"encrypted member {info.filename!r} refused"))
        if stat.S_ISLNK(info.external_attr >> 16):
            findings.append(_rfinding("SEC_ARCHIVE_SYMLINK",
                                      f"symlink member {info.filename!r} refused"))
        name = info.filename.replace("\\", "/")
        parts = name.split("/")
        if (name.startswith("/") or any(p == ".." for p in parts)
                or re.match(r"^[A-Za-z]:", name)):
            findings.append(_rfinding(
                "SEC_PATH_TRAVERSAL",
                f"member name {info.filename!r} escapes the extraction root"))
        comp_size = max(info.compress_size, 1)
        ratio = max(info.file_size, 1) / comp_size
        if info.file_size > 0 and ratio > max_archive_ratio():
            findings.append(_rfinding(
                "SEC_ZIP_BOMB",
                f"member {info.filename!r} expands {ratio:.0f}x "
                f"({info.compress_size} -> {info.file_size} bytes), "
                f"cap is {max_archive_ratio()}x"))
        total_unc += info.file_size
    if total_unc > max_archive_uncompressed():
        findings.append(_rfinding(
            "SEC_ZIP_BOMB",
            f"total uncompressed {total_unc} bytes exceeds the "
            f"{max_archive_uncompressed()}-byte cap"))
    if not findings:
        findings.append(_rfinding(
            "SEC_ARCHIVE_OK",
            f"{len(infos)} member(s), all within entry/ratio/traversal limits"))
    return findings


# ---------------------------------------------------------------------------
# 4. TIFF metadata: report presence; optional structural stripping
# ---------------------------------------------------------------------------
_META_TAGS = {
    269: "DocumentName", 271: "Make", 272: "Model", 305: "Software",
    306: "DateTime", 315: "Artist", 33432: "Copyright", 33723: "IPTC-NAA",
    34665: "ExifIFD", 34853: "GPSInfo", 700: "XMP",
}
_WHITELIST_STRUCTURAL = {256, 257, 258, 259, 262, 273, 277, 278, 279}
_WHITELIST_GEO = {33550, 33922, 34735}

_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1,
                    8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
_TIFF_TYPE_FMT = {1: "B", 2: "B", 3: "H", 4: "I", 5: "I", 6: "b", 7: "B",
                  8: "h", 9: "i", 10: "i", 11: "f", 12: "d"}


def _read_tiff_entries(raw: bytes, e: str) -> Dict[int, Tuple[int, int, bytes]]:
    ifd_off = struct.unpack(e + "I", raw[4:8])[0]
    n_entries = struct.unpack(e + "H", raw[ifd_off:ifd_off + 2])[0]
    base = ifd_off + 2
    entries: Dict[int, Tuple[int, int, bytes]] = {}
    for i in range(n_entries):
        rec = raw[base + 12 * i: base + 12 * (i + 1)]
        if len(rec) < 12:
            break
        tag, typ, count = struct.unpack(e + "HHI", rec[:8])
        if typ in _TIFF_TYPE_SIZES:
            entries[tag] = (typ, count, rec[8:12])
    return entries


def _tag_value_block(raw: bytes, e: str,
                     entry: Tuple[int, int, bytes]) -> bytes:
    typ, count, val_field = entry
    size = _TIFF_TYPE_SIZES[typ] * count
    if size <= 4:
        return val_field[:size]
    old = struct.unpack(e + "I", val_field)[0]
    return raw[old:old + size]


def scan_tiff_metadata(path: Path) -> Tuple[Dict[int, str], List[dict]]:
    """Return ({tag_number: tag_name} for metadata tags present, findings)."""
    raw = path.read_bytes()
    e = {"II": "<", "MM": ">"}.get(raw[:2].decode("ascii", errors="ignore"), "")
    if not e:
        return {}, [_rfinding("META_NONE", "not a TIFF; no metadata scan")]
    entries = _read_tiff_entries(raw, e)
    present = {t: nm for t, nm in _META_TAGS.items() if t in entries}
    findings = ([_rfinding("META_PRESENT",
                           f"auxiliary metadata present: "
                           f"{sorted(present.values())}")] if present else
                [_rfinding("META_NONE", "no auxiliary metadata tags found")])
    return present, findings


def strip_tiff_auxiliary_tags(src: Path, dst: Path,
                              keep_geo: bool = True) -> dict:
    """Rewrite a TIFF keeping only structural (+ optionally geo) tags.
    Everything else — EXIF, GPS, XMP, copyright, software... — is dropped.
    Strip bytes are re-laid-out and StripOffsets/StripByteCounts are
    re-emitted as LONGs. Zero dependencies, single IFD output.
    Returns {dropped_tags, kept_geo, sha256}."""
    raw = src.read_bytes()
    order = raw[:2].decode("ascii", errors="ignore")
    e = {"II": "<", "MM": ">"}.get(order)
    if e is None:
        raise ValueError("not a TIFF")
    entries = _read_tiff_entries(raw, e)
    for required in (273, 279):
        if required not in entries:
            raise ValueError(f"TIFF lacks tag {required}; cannot re-layout strips")

    keep = set(_WHITELIST_STRUCTURAL) | (set(_WHITELIST_GEO) if keep_geo else set())
    keep &= set(entries)
    dropped = sorted(set(entries) - keep)

    # counts/offsets as integers; re-emitted as LONG (type 4)
    _, n_strips, _ = entries[273]
    _, n_counts, _ = entries[279]
    if n_strips != n_counts:
        raise ValueError("StripOffsets/StripByteCounts count mismatch")
    offsets_raw = _unpack_maybe_short(raw, e, entries[273])
    counts_raw = _unpack_maybe_short(raw, e, entries[279])

    keep_sorted = sorted(keep)
    ifd_size = 2 + 12 * len(keep_sorted) + 4
    value_area_off = 8 + ifd_size

    out = bytearray()
    out += raw[:2] + struct.pack(e + "HI", 42, 8)
    out += struct.pack(e + "H", len(keep_sorted))  # IFD entry count first
    value_area = bytearray()
    strip_placeholder_abs = None  # absolute offset of tag-273 value block

    for tag in keep_sorted:
        typ, count, val_field = entries[tag]
        out_typ, out_count = typ, count
        if tag in (273, 279):
            out_typ = 4  # LONG
        size = _TIFF_TYPE_SIZES[out_typ] * out_count
        rec = struct.pack(e + "HHI", tag, out_typ, out_count)
        if tag == 273:
            block = b"\x00" * size  # placeholder, patched below
            if size <= 4:
                rec += block.ljust(4, b"\x00")
                strip_placeholder_abs = 8 + 2 + 12 * keep_sorted.index(tag) + 8
            else:
                strip_placeholder_abs = value_area_off + len(value_area)
                rec += struct.pack(e + "I", strip_placeholder_abs)
                value_area.extend(block)
        else:
            block = _tag_value_block(raw, e, entries[tag])
            if size <= 4:
                rec += block.ljust(4, b"\x00")
            else:
                rec += struct.pack(e + "I", value_area_off + len(value_area))
                value_area.extend(block)
        if len(value_area) % 2:
            value_area.append(0)
        out += rec

    out += struct.pack(e + "I", 0)  # next IFD = none
    out += value_area
    if len(out) % 2:
        out.append(0)

    strip_start = len(out)
    for off_orig, cnt in zip(offsets_raw, counts_raw):
        out.extend(raw[off_orig: off_orig + cnt])

    new_offsets = []
    cur = strip_start
    for cnt in counts_raw:
        new_offsets.append(cur)
        cur += cnt

    fmt = e + "I" * n_strips
    packed = struct.pack(fmt, *new_offsets)
    size = 4 * n_strips
    if size <= 4:
        out[strip_placeholder_abs:strip_placeholder_abs + 4] = packed.ljust(4, b"\x00")
    else:
        out[strip_placeholder_abs:strip_placeholder_abs + size] = packed

    dst.write_bytes(bytes(out))
    return {"dropped_tags": [f"{t}:{_META_TAGS.get(t, 'foreign/unknown')}"
                             for t in dropped],
            "kept_geo": bool(set(_WHITELIST_GEO) & keep),
            "sha256": hashlib.sha256(bytes(out)).hexdigest()}


def _unpack_maybe_short(raw: bytes, e: str,
                        entry: Tuple[int, int, bytes]) -> Tuple[int, ...]:
    typ, count, val_field = entry
    block = _tag_value_block(raw, e, entry)
    if typ == 3:
        return struct.unpack(e + "H" * count, block)
    return struct.unpack(e + "I" * count, block)


# ---------------------------------------------------------------------------
# main entry: check_upload
# ---------------------------------------------------------------------------
# dtypes whose content validation runs at reception (magic must match one of
# these or the file is refused as unknown binary).
TEXT_DTYPE_MAGIC_OK = ("las", "csv", "geojson", "tiff", "gpkg")


def check_upload(path: str, declared_name: Optional[str] = None,
                 dtype: str = "auto",
                 declared_crs: Optional[str] = None,
                 declared_units: Optional[str] = None,
                 run_content_validation: bool = True) -> dict:
    """Run the full reception gate. Returns an evidence report:
    {status: accepted|needs_review|rejected, findings, sanitized_name,
     name_flags, size_bytes, sha256, sniffed, dtype, content_report}.
    Refusals cite the policy so the caller can surface the reason honestly."""
    from geologia.data_layer.validators import validate_file

    p = Path(path)
    findings: List[dict] = []
    if not p.exists():
        return {"status": "rejected", "file": str(p), "dtype": dtype,
                "findings": [_rfinding("SEC_EMPTY_FILE", "file does not exist")]}
    size = p.stat().st_size
    if size == 0:
        return {"status": "rejected", "file": str(p), "dtype": dtype,
                "findings": [_rfinding("SEC_EMPTY_FILE", "file is empty")]}
    if size > max_upload_bytes():
        findings.append(_rfinding(
            "SEC_TOO_LARGE",
            f"{size} bytes exceeds the {max_upload_bytes()}-byte reception cap "
            f"(GEOLOGIA_MAX_UPLOAD_BYTES)"))
    raw_name = declared_name or p.name
    safe_name, flags = sanitize_filename(raw_name)
    if "refused_empty_after_sanitization" in flags:
        findings.append(_rfinding(
            "SEC_NAME_REFUSED",
            f"client name {raw_name!r} reduces to nothing safe — refusing"))
    elif flags:
        findings.append(_rfinding("SEC_NAME_SANITIZED",
                                  f"name sanitized {raw_name!r} -> {safe_name!r} "
                                  f"({', '.join(flags)})"))
    else:
        findings.append(_rfinding("SEC_NAME_OK", f"name {safe_name!r} accepted as-is"))

    # content sniffing vs declared/derived type
    kind, detail = sniff_content(p)
    effective = dtype
    if effective == "auto":
        suffix = Path(safe_name).suffix.lower()
        for t, exts in (("las", (".las",)), ("geojson", (".geojson", ".json")),
                        ("csv", (".csv", ".tsv")), ("tiff", (".tif", ".tiff")),
                        ("gpkg", (".gpkg",))):
            if suffix in exts:
                effective = t
                break
    if kind in ("zip", "gzip"):
        findings.extend(scan_archive(p))
    elif kind == "sqlite":
        if effective not in ("gpkg", "auto"):
            findings.append(_rfinding(
                "SEC_EXT_MISMATCH",
                f"content is SQLite (magic) but declared type is {effective!r}"))
        else:
            findings.append(_rfinding("SEC_MAGIC_MATCH", detail))
    elif kind == "tiff":
        if effective not in ("tiff", "auto"):
            findings.append(_rfinding(
                "SEC_EXT_MISMATCH",
                f"content is TIFF (magic) but declared type is {effective!r}"))
        else:
            findings.append(_rfinding("SEC_MAGIC_MATCH", detail))
    elif kind == "text":
        if effective == "tiff":
            findings.append(_rfinding(
                "SEC_EXT_MISMATCH",
                "content is UTF-8 text but declared type is tiff"))
        else:
            findings.append(_rfinding("SEC_MAGIC_MATCH", detail))
        text_head = p.open("rb").read(1 << 16).decode("utf-8", errors="replace")
        if _looks_like_html(text_head):
            findings.append(_rfinding(
                "SEC_HTML_EMBEDDED",
                "markup content (HTML/SVG) in a data upload — stored-XSS risk"))
        if "\x00" in text_head:
            findings.append(_rfinding("SEC_CONTROL_CHARS", "NUL byte in text upload"))
        for ln in text_head.splitlines():
            if len(ln.encode("utf-8")) > max_line_bytes():
                findings.append(_rfinding("SEC_LINE_TOO_LONG",
                                          f"line exceeds {max_line_bytes()} bytes"))
                break
    else:  # binary_unknown
        findings.append(_rfinding("SEC_UNKNOWN_MAGIC",
                                  f"{detail} — refusing unknown binary content"))

    content_report = None
    if run_content_validation and effective in TEXT_DTYPE_MAGIC_OK:
        content_report = validate_file(str(p), effective,
                                       declared_crs=declared_crs,
                                       declared_units=declared_units)
        if content_report["status"] == "pass":
            findings.append(_rfinding("SEC_CONTENT_VALID",
                                      f"content validation passed ({effective})"))
        else:
            content_codes = [f["code"] for f in content_report["findings"]
                             if f["severity"] == "error"]
            findings.append(_rfinding("SEC_CONTENT_INVALID",
                                      f"content validation failed ({effective}): "
                                      f"{content_codes}"))

    hard_fail = any(f["severity"] == "error" for f in findings)
    if hard_fail:
        status = "rejected"
    elif content_report is None:
        status = "needs_review"  # archive/unknown-text: scan passed, content not validated
    else:
        status = "accepted"
    digest = None
    if size <= max_upload_bytes():
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "status": status,
        "file": str(p),
        "dtype": effective,
        "sniffed": kind,
        "size_bytes": size,
        "sha256": digest,
        "sanitized_name": safe_name,
        "name_flags": flags,
        "findings": findings,
        "content_report": content_report,
    }
