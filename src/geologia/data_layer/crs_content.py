"""CRS detection from actual content — the declaration is evidence, not authority.

Governing sequence step 4 (Phase 2, real GIS): «اكتشاف CRS من المحتوى الفعلي
لا من الإعلان» — detection from the actual content, not from the announcement.
For coordinate-bearing uploads whose format carries no CRS declaration
mechanism (CSV, GeoJSON) the platform previously rested georeferencing on the
declared string alone. This module adds the content side: magnitude-based
classification of coordinate pairs, WGS84 range verification for RFC 7946
content, and an explicit truth classification for every detection so the
record states what the content itself proves and what rests on the
declaration only.

Zero dependencies, bounded by construction (a bounded sample, never the
whole file). Detection proves coordinate CLASS only (geographic degrees vs
UTM-projected metres); a specific UTM zone cannot be confirmed from easting
magnitude alone — stating that honestly is the point, and the inverse-math
zone verification lives in the workspace layer, which owns the frozen UTM
equations engine.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

# Bounded sampling cap: detection reads at most this many coordinate pairs.
MAX_SAMPLE_POINTS_DEFAULT = 10_000

# Content classes (the only three statements content magnitude can support).
CLASS_GEOGRAPHIC = "geographic_degrees"
CLASS_UTM = "utm_projected_metres"
CLASS_UNKNOWN = "unknown"

# Truth classification vocabulary (constraint: every output carries it).
TRUTH_VERIFIED_CONTENT = "verified_content"
TRUTH_DECLARED_ONLY = "declared_unverified"
TRUTH_CONTRADICTED = "contradicted_declared"
TRUTH_UNDETERMINED = "undetermined"

# WGS 84 geographic bounds (RFC 7946 lon,lat membership).
LON_MIN, LON_MAX = -180.0, 180.0
LAT_MIN, LAT_MAX = -90.0, 90.0

# UTM projected-coordinate magnitude envelope (any zone, either hemisphere):
# easting 100000..999999 m, northing 0..10,000,000 m (10,000,000 included for
# the southern-hemisphere false-northing convention).
EASTING_MIN, EASTING_MAX = 100_000.0, 999_999.0
NORTHING_MIN, NORTHING_MAX = 0.0, 10_000_000.0


def detect_point_class(x: float, y: float) -> str:
    """Classify ONE (x, y) pair by magnitude alone.

    Geographic-degrees membership takes precedence: a pair inside the WGS84
    lon/lat envelope is classified as geographic even though a bogus UTM
    pair could numerically satisfy it (an easting of 500000 m and a northing
    of 45.0 degrees are not both plausible, and ambiguity is reported by the
    caller-level aggregation, not hidden here).
    """
    if LON_MIN <= x <= LON_MAX and LAT_MIN <= y <= LAT_MAX:
        return CLASS_GEOGRAPHIC
    if (EASTING_MIN <= x <= EASTING_MAX
            and NORTHING_MIN <= y <= NORTHING_MAX):
        return CLASS_UTM
    return CLASS_UNKNOWN


def classify_content_points(
    points: Sequence[Tuple[float, float]],
    max_points: int = MAX_SAMPLE_POINTS_DEFAULT,
) -> Dict[str, object]:
    """Aggregate content-side classification over a bounded sample of pairs.

    Returns a detection report with an explicit truth classification:
    - ``verified_content``: the sample itself fixes the class (all pairs in
      one plausible envelope, and the other class excluded);
    - ``undetermined``: sample empty, mixed classes, or unknowns present —
      the content does not fix the class;
    - the caller decides whether a declaration agrees (raising the truth
      class) or contradicts the content (``contradicted_declared``).

    Ambiguous pairs (inside the geographic envelope AND satisfying the UTM
    envelope, e.g. x=180, y=90 is neither) are counted, not resolved by fiat.
    """
    sample = list(points[: max(1, int(max_points))])
    if not sample:
        return {
            "detected_class": CLASS_UNKNOWN,
            "truth_class": TRUTH_UNDETERMINED,
            "n_points_checked": 0,
            "n_ambiguous": 0,
            "sample_bounds": None,
            "note_en": "no coordinate pairs available; class rests on the "
                       "declaration only",
            "note_ar": "لا توجد أزواج إحداثيات؛ التصنيف يقوم على الإعلان وحده",
        }
    classes = {CLASS_GEOGRAPHIC: 0, CLASS_UTM: 0, CLASS_UNKNOWN: 0}
    n_ambiguous = 0
    x_min = x_max = None
    y_min = y_max = None
    for x, y in sample:
        both = (LON_MIN <= x <= LON_MAX and LAT_MIN <= y <= LAT_MAX
                and EASTING_MIN <= x <= EASTING_MAX
                and NORTHING_MIN <= y <= NORTHING_MAX)
        if both:
            n_ambiguous += 1
        classes[detect_point_class(x, y)] += 1
        x_min = x if x_min is None else min(x_min, x)
        x_max = x if x_max is None else max(x_max, x)
        y_min = y if y_min is None else min(y_min, y)
        y_max = y if y_max is None else max(y_max, y)

    n = len(sample)
    detected = CLASS_UNKNOWN
    truth = TRUTH_UNDETERMINED
    if classes[CLASS_GEOGRAPHIC] == n:
        # All pairs are valid WGS84 degrees; UTM membership of the same
        # numbers would require easting <= 999999 and northing <= 10M, so
        # some pairs could in principle be both — ambiguity is counted and
        # reported, never silently resolved.
        detected = CLASS_GEOGRAPHIC
        truth = TRUTH_VERIFIED_CONTENT
    elif classes[CLASS_UTM] == n:
        detected = CLASS_UTM
        truth = TRUTH_VERIFIED_CONTENT
    elif classes[CLASS_UNKNOWN] == n:
        detected = CLASS_UNKNOWN
        truth = TRUTH_UNDETERMINED
    else:
        detected = CLASS_UNKNOWN
        truth = TRUTH_UNDETERMINED
    return {
        "detected_class": detected,
        "truth_class": truth,
        "n_points_checked": n,
        "n_geographic": classes[CLASS_GEOGRAPHIC],
        "n_utm": classes[CLASS_UTM],
        "n_unknown": classes[CLASS_UNKNOWN],
        "n_ambiguous": n_ambiguous,
        "sample_bounds": {"x_min": x_min, "x_max": x_max,
                          "y_min": y_min, "y_max": y_max},
        "note_en": (
            "content-side magnitude classification; a specific UTM zone is "
            "not confirmable from easting magnitude alone — zone verification "
            "by inverse math belongs to the workspace layer"
        ),
        "note_ar": (
            "تصنيف من المحتوى بحسب المقدار؛ رقم نطاق UTM بعينه لا يثبت من "
            "مقدار الإحداثية الشرقية وحدها — التحقق بالنطاق عبر الرياضيات "
            "العكسية في طبقة مساحة العمل"
        ),
    }


def verify_wgs84_ranges(points: Sequence[Tuple[float, float]],
                        max_points: int = MAX_SAMPLE_POINTS_DEFAULT,
                        ) -> Optional[Dict[str, object]]:
    """Content-side RFC 7946 membership check over a bounded sample.

    Returns ``None`` when the sample is empty (nothing provable from
    content); otherwise a report whose truth class is
    ``verified_content`` when every sampled position is inside the WGS84
    lon/lat envelope and ``contradicted_declared`` when any position is
    outside (RFC 7946 content is WGS84 by specification — an outside value
    is a content defect, not a style difference).
    """
    sample = list(points[: max(1, int(max_points))])
    if not sample:
        return None
    outside: List[Tuple[float, float]] = []
    for x, y in sample:
        if not (LON_MIN <= x <= LON_MAX and LAT_MIN <= y <= LAT_MAX):
            outside.append((x, y))
    ok = not outside
    return {
        "in_wgs84_range": ok,
        "truth_class": (TRUTH_VERIFIED_CONTENT if ok
                        else TRUTH_CONTRADICTED),
        "n_points_checked": len(sample),
        "n_outside": len(outside),
        "first_outside": list(outside[0]) if outside else None,
        "note_en": ("RFC 7946 geometry is WGS 84 lon/lat degrees; every "
                    "sampled position is inside the envelope" if ok else
                    "RFC 7946 geometry is WGS 84 lon/lat degrees; sampled "
                    "positions fall outside the envelope — the content "
                    "contradicts the WGS84 assumption it is stored under"),
        "note_ar": ("هندسة RFC 7946 هي WGS 84 بالدرجات؛ كل المواضع المفحوصة "
                    "داخل المدى" if ok else
                    "هندسة RFC 7946 هي WGS 84 بالدرجات؛ مواضع مفحوصة خارج "
                    "المدى — المحتوى يناقض افتراض WGS84 الذي محفوظ تحته"),
    }


def declared_crs_kind(declared: Optional[str]) -> str:
    """Classify a declared CRS string's KIND: geo_deg | utm | local | unknown.

    Documented twin of ``validators.classify_crs`` (kept here so the content
    module stays import-cycle-free: validators imports crs_content, never the
    reverse). The regexes mirror the validator's frozen ones.
    """
    import re
    if not declared:
        return "unknown"
    s = str(declared).strip()
    if re.search(r"(4326|CRS84|WGS\s*84)", s, re.I):
        return "geo_deg"
    if re.search(r"(?:EPSG\s*:\s*)?32[67](\d{2})\b|UTM", s, re.I):
        return "utm"
    if re.search(r"local|depth", s, re.I):
        return "local"
    return "unknown"


def resolve_declared_vs_content(
    detected: str, content_truth: str, declared: Optional[str]
) -> Tuple[str, List[str]]:
    """Final truth classification: declaration + content, stated honestly.

    Returns (final_truth_class, note codes). The declaration never upgrades
    the content beyond what content proves; it can only agree (kept at the
    content truth) or contradict (``contradicted_declared`` wins — the
    loudest honest statement). A contradiction is a KIND disagreement
    (declared geographic while content is UTM-projected metres, or the
    reverse) held by content with ``verified_content`` certainty.
    """
    codes: List[str] = []
    if not declared:
        codes.append("CRS_CONTENT_ONLY")
        final = content_truth if content_truth != TRUTH_UNDETERMINED \
            else TRUTH_DECLARED_ONLY
        return final, codes
    codes.append("CRS_DECLARED_PRESENT")
    kind = declared_crs_kind(declared)
    if content_truth == TRUTH_VERIFIED_CONTENT:
        if detected == CLASS_UTM and kind == "geo_deg":
            codes.append("CRS_DECLARATION_CONTRADICTED_BY_CONTENT")
            return TRUTH_CONTRADICTED, codes
        if detected == CLASS_GEOGRAPHIC and kind == "utm":
            codes.append("CRS_DECLARATION_CONTRADICTED_BY_CONTENT")
            return TRUTH_CONTRADICTED, codes
        codes.append("CRS_DECLARATION_AGREES_WITH_CONTENT")
        return TRUTH_VERIFIED_CONTENT, codes
    if content_truth == TRUTH_CONTRADICTED:
        codes.append("CRS_DECLARATION_CONTRADICTED_BY_CONTENT")
        return TRUTH_CONTRADICTED, codes
    codes.append("CRS_CONTENT_UNDETERMINED_DECLARATION_UNVERIFIED")
    return TRUTH_DECLARED_ONLY, codes
