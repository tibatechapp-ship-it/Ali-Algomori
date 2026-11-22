"""CRS detection from actual content + UTM zone plausibility by inverse math.

Workspace-side companion of the governing sequence step 4: «اكتشاف CRS من
المحتوى الفعلي لا من الإعلان» then «التحليل المكاني المطابق لمرجع عبر
Workers». Core (``geologia.data_layer.crs_content``) classifies coordinate
magnitude. This module owns the inverse-math half, with an honest limit
stated up front:

A UTM zone NUMBER is not falsifiable from (easting, northing) alone — the
same plausible pair inverts to a self-consistent position under ANY zone,
shifted by the zone difference. What the frozen equations CAN verify against
content: the content is self-consistent UTM data under the declared
interpretation (clean inverse, recovered positions inside the zone's
longitude band, sub-metre forward round-trip against the frozen reference),
and implausible content under the declaration (degree-like magnitudes,
extreme eastings landing outside the band) is refused. Confirming a zone
label requires an independent geographic anchor; the Sana'a 44.2°E
zone-38-not-37 lesson is exactly that limit, recorded here rather than
hidden behind a stronger claim.

Detection proves class; verification proves plausibility and
self-consistency; neither certifies that real-world coordinates are
scientifically correct — every result carries its truth classification.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# Bounded sample cap: verification reads at most this many pairs.
MAX_SAMPLE_POINTS_DEFAULT = 10_000

# Zone-to-band edges: zone Z is centred on 6Z-183 degrees (zone 38 -> 45E).
def _central_meridian(zone: int) -> float:
    return 6.0 * zone - 183.0

_UTM_EPSG_RE = None  # compiled lazily; keeps module import cheap


def parse_utm_epsg(crs: Optional[str]) -> Optional[Tuple[int, str]]:
    """Parse ``EPSG:326xx`` / ``EPSG:327xx`` -> (zone, hemisphere), else None.

    The same shapes the display fallback accepts; kept here so the content
    verification and the transform path agree on one parser.
    """
    global _UTM_EPSG_RE
    if not crs:
        return None
    import re
    if _UTM_EPSG_RE is None:
        _UTM_EPSG_RE = re.compile(r"(?i)\s*EPSG:32([67])(\d{2})\s*")
    m = _UTM_EPSG_RE.fullmatch(str(crs))
    if not m:
        return None
    zone = int(m.group(2))
    if not 1 <= zone <= 60:
        return None
    return zone, ("north" if m.group(1) == "6" else "south")


def extract_geojson_positions(
    payload: object, max_points: int = MAX_SAMPLE_POINTS_DEFAULT,
) -> List[Tuple[float, float]]:
    """Extract a bounded sample of (x, y) positions from a GeoJSON payload.

    Walks FeatureCollection / Feature / geometry ``coordinates`` nesting,
    collecting the first two numbers of every position. Collection stops at
    ``max_points`` — bounded by construction. Non-numeric positions are
    skipped (structural validation owns those errors; detection never
    fabricates a pair).
    """
    collected: List[Tuple[float, float]] = []

    def walk(node: object) -> None:
        if len(collected) >= max_points:
            return
        if isinstance(node, dict):
            if "coordinates" in node:
                walk(node.get("coordinates"))
            else:
                # Feature -> geometry; FeatureCollection -> features.
                if "geometry" in node:
                    walk(node.get("geometry"))
                if "features" in node:
                    walk(node.get("features"))
            return
        if isinstance(node, list):
            if (len(node) >= 2
                    and isinstance(node[0], (int, float))
                    and not isinstance(node[0], bool)
                    and isinstance(node[1], (int, float))
                    and not isinstance(node[1], bool)):
                collected.append((float(node[0]), float(node[1])))
                return
            for child in node:
                walk(child)
            return

    walk(payload)
    return collected


TRUTH_ORDER = (
    "contradicted_declared",   # loudest: content contradicts the declaration
    "undetermined",            # content cannot fix the class/zone
    "verified_content",        # content itself proves the statement
    "declared_unverified",     # only the declaration, nothing from content
)


def loudest_truth(*truths: Optional[str]) -> str:
    """Pick the loudest honest statement from several truth classifications.

    A contradiction outranks uncertainty; certainty from content outranks a
    bare declaration. Used at envelope level so one response carries ONE
    truth class that summarizes its parts without hiding any of them (each
    part's own truth class stays in the response).
    """
    for candidate in TRUTH_ORDER:
        if candidate in truths:
            return candidate
    return "undetermined"


def utm_zone_longitude_band(zone: int) -> Tuple[float, float]:
    """Return the (min_lon, max_lon) degree band a UTM zone governs."""
    if not 1 <= zone <= 60:
        raise ValueError("UTM zone must be 1..60")
    cm = _central_meridian(zone)
    lo = -180.0 if zone == 1 else cm - 3.0
    hi = 180.0 if zone == 60 else cm + 3.0
    return lo, hi


def detect_coordinate_class(
    points: Sequence[Tuple[float, float]],
    max_points: int = MAX_SAMPLE_POINTS_DEFAULT,
) -> Dict[str, object]:
    """Magnitude-only content classification (documented cross-layer twin of
    ``geologia.data_layer.crs_content.classify_content_points``; the layers
    are separate distributions by ADR-0001, and this heuristic is small and
    frozen-by-test on both sides).

    Classes: ``geographic_degrees`` (all pairs inside the WGS84 envelope),
    ``utm_projected_metres`` (all pairs inside the UTM magnitude envelope),
    ``unknown`` otherwise. Truth classification on the result: content
    proves class only when every sampled pair agrees and no pair is
    ambiguous.
    """
    sample = list(points[: max(1, int(max_points))])
    if not sample:
        return {
            "detected_class": "unknown",
            "truth_class": "undetermined",
            "n_points_checked": 0,
            "n_ambiguous": 0,
            "note_en": "no coordinate pairs available",
            "note_ar": "لا توجد أزواج إحداثيات",
        }
    geo = utm = unknown = ambiguous = 0
    for x, y in sample:
        in_geo = -180.0 <= x <= 180.0 and -90.0 <= y <= 90.0
        in_utm = 100_000.0 <= x <= 999_999.0 and 0.0 <= y <= 10_000_000.0
        if in_geo and in_utm:
            ambiguous += 1
        if in_geo:
            geo += 1
        elif in_utm:
            utm += 1
        else:
            unknown += 1
    n = len(sample)
    if geo == n:
        detected, truth = "geographic_degrees", "verified_content"
    elif utm == n:
        detected, truth = "utm_projected_metres", "verified_content"
    else:
        detected, truth = "unknown", "undetermined"
    return {
        "detected_class": detected,
        "truth_class": truth,
        "n_points_checked": n,
        "n_geographic": geo,
        "n_utm": utm,
        "n_unknown": unknown,
        "n_ambiguous": ambiguous,
    }


def verify_utm_zone_from_content(
    points: Sequence[Tuple[float, float]],
    declared_zone: int,
    hemisphere: str = "north",
    max_points: int = MAX_SAMPLE_POINTS_DEFAULT,
) -> Dict[str, object]:
    """Test content plausibility and self-consistency under a declared zone.

    Runs a bounded sample of (easting, northing) pairs through the frozen
    ``utm_equations.utm_inverse`` under the DECLARED zone, checks every
    recovered longitude against the zone's longitude band, and re-runs the
    forward direction on the recovered lon/lat so the verification is itself
    reference-matched (the equations module carries the frozen golden
    contract against PROJ).

    Verdicts (each carried with its truth classification):
    - ``verified_content`` + ``UTM_ZONE_CONTENT_VERIFIED``: every pair
      inverts cleanly, every recovered longitude lies in the declared
      zone's band, and the round-trip residual is sub-metre. This proves
      the content is self-consistent UTM data under the declared
      interpretation — it does NOT confirm the zone number itself (an
      equally self-consistent result would arise under a wrong neighbouring
      zone label); the limit note is carried on the verdict.
    - ``contradicted_declared`` + ``UTM_ZONE_CONTENT_MISMATCH``: recovered
      longitudes fall outside the declared zone's band — the content is not
      plausible under this declaration; a suggested zone is computed from
      the out-of-band longitudes as evidence.
    - ``undetermined`` + ``UTM_ZONE_CONTENT_MIXED``: some inside, some
      outside — needs review, no single verdict;
    - ``undetermined`` + ``UTM_ZONE_CONTENT_UNVERIFIABLE``: the inverse math
      refused the inputs (out-of-domain points) or no pairs exist —
      stated, never guessed.
    """
    from geologia_workspace.utm_equations import (
        detect_utm_zone,
        utm_forward,
        utm_inverse,
    )

    if not 1 <= declared_zone <= 60:
        return {
            "verdict_code": "UTM_ZONE_CONTENT_UNVERIFIABLE",
            "truth_class": "undetermined",
            "reason_en": f"declared zone {declared_zone} is out of range 1..60",
            "reason_ar": f"النطاق المعلن {declared_zone} خارج المدى 1..60",
            "n_points_checked": 0,
        }
    sample = list(points[: max(1, int(max_points))])
    if not sample:
        return {
            "verdict_code": "UTM_ZONE_CONTENT_UNVERIFIABLE",
            "truth_class": "undetermined",
            "reason_en": "no coordinate pairs available; the zone rests on "
                         "the declaration alone",
            "reason_ar": "لا توجد أزواج إحداثيات؛ النطاق يقوم على الإعلان وحده",
            "n_points_checked": 0,
        }
    lo, hi = utm_zone_longitude_band(declared_zone)
    inside = outside = failed = 0
    lons: List[float] = []
    first_outside_lon: Optional[float] = None
    roundtrip_residuals: List[float] = []
    for easting, northing in sample:
        try:
            lon, lat = utm_inverse(declared_zone, hemisphere,
                                   float(easting), float(northing))
        except (ValueError, OverflowError):
            failed += 1
            continue
        if not (math.isfinite(lon) and math.isfinite(lat)):
            failed += 1
            continue
        lons.append(lon)
        # Round-trip reference matching: feed the recovered lon/lat back
        # through the forward equations; the residual must be sub-metre.
        try:
            e2, n2 = utm_forward(declared_zone, lon, lat)
            roundtrip_residuals.append(
                math.hypot(e2 - float(easting), n2 - float(northing)))
        except (ValueError, OverflowError):
            pass
        if lo <= lon <= hi:
            inside += 1
        else:
            outside += 1
            if first_outside_lon is None:
                first_outside_lon = lon
    n = len(sample)
    suggestion: Optional[int] = None
    anchor_lons = [v for v in (first_outside_lon and [first_outside_lon]
                              or lons) if -180.0 <= v < 180.0]
    if anchor_lons:
        try:
            suggestion = detect_utm_zone(
                sum(anchor_lons) / len(anchor_lons))
        except ValueError:
            suggestion = None
    base = {
        "declared_zone": declared_zone,
        "declared_band": [lo, hi],
        "hemisphere": hemisphere,
        "n_points_checked": n,
        "n_inside_band": inside,
        "n_outside_band": outside,
        "n_math_failed": failed,
        "suggested_zone": suggestion,
        "max_roundtrip_residual_m": (max(roundtrip_residuals)
                                     if roundtrip_residuals else None),
    }
    if n and inside == n:
        return {
            **base,
            "verdict_code": "UTM_ZONE_CONTENT_VERIFIED",
            "truth_class": "verified_content",
            "note_en": ("content is self-consistent UTM data under the "
                        "declared zone: every sampled position inverts "
                        "cleanly, lands inside the zone's longitude band, "
                        "and round-trips to the frozen reference sub-metre. "
                        "LIMIT: the zone NUMBER itself is not confirmable "
                        "from (easting, northing) alone — a wrong "
                        "neighbouring zone label would produce an equally "
                        "self-consistent result; confirming the label "
                        "requires an independent geographic anchor."),
            "note_ar": ("المحتوى بيانات UTM ذاتية الاتساق تحت النطاق المعلن: "
                        "كل موضع مفحوص ينعكس نظيفاً داخل نطاق الطول ويكتمل "
                        "المدار إلى المرجع المجمّد دون متر. الحد: رقم النطاق "
                        "نفسه لا يُثبت من (الإحداثية الشرقية، الشمالية) وحدهما "
                        "— إعلان نطاق مجاور خاطئ يعطي نتيجة ذاتية الاتساق "
                        "بالمثل؛ تأكيد الرمز يحتاج مرساة جغرافية مستقلة."),
        }
    if n and outside == n and not failed:
        return {
            **base,
            "verdict_code": "UTM_ZONE_CONTENT_MISMATCH",
            "truth_class": "contradicted_declared",
            "first_outside_lon": first_outside_lon,
            "note_en": ("recovered longitudes fall outside the declared "
                        "zone's band — the content is not plausible under "
                        "this declaration (degree-like magnitudes or a "
                        "foreign grid); the suggested zone from the "
                        "out-of-band longitudes is evidence, not a "
                        "correction"),
            "note_ar": ("أطوال مسترجعة خارج نطاق النطاق المعلن — المحتوى غير "
                        "معقول تحت هذا الإعلان (مقادير درجاتية أو شبكة "
                        "أجنبية)؛ النطاق المقترح من الأطوال الخارجة دليل لا "
                        "تصحيح"),
        }
    if inside and outside:
        return {
            **base,
            "verdict_code": "UTM_ZONE_CONTENT_MIXED",
            "truth_class": "undetermined",
            "first_outside_lon": first_outside_lon,
            "note_en": ("sample straddles band edges or contains mixed "
                        "positions — needs review, no single verdict"),
            "note_ar": ("العينة تعبر حدود النطاق أو تحوي مواضع مختلطة — "
                        "بحاجة مراجعة، لا حكم واحد"),
        }
    return {
        **base,
        "verdict_code": "UTM_ZONE_CONTENT_UNVERIFIABLE",
        "truth_class": "undetermined",
        "reason_en": ("the inverse math refused the sampled inputs; nothing "
                      "is proven either way"),
        "reason_ar": ("رفضت الرياضيات العكسية المدخلات المفحوصة؛ لا يثبت "
                      "شيء بأي اتجاه"),
    }
