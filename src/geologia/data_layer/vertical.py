"""Vertical reference and units verification.

Horizontal CRS tells you where a point is; the vertical reference tells you
what its height MEANS. A DEM with elevations "in metres" is useless and
dangerous without a datum: metres above MSL, above NAVD88, above the
ellipsoid, or above a local benchmark differ by tens of metres. This module
makes the vertical claim explicit — recognized, unknown, or absent — and
never lets the layer imply a datum the file did not declare.

Sources handled:
- GeoTIFF GeoKeys: VerticalCSTypeGeoKey (4096), VerticalDatumGeoKey (4097),
  VerticalUnitsGeoKey (4098);
- WKT strings (VERTCS[...] blocks, e.g. from GPKG definitions or LAS WKT
  extension headers);
- well-log LAS (~Well section depth datum, when declared at all).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .evidence import (compile_evidence, ev_read, ev_unverifiable,
                       ev_verified)

# Recognized vertical coordinate systems (closed list; anything outside it
# is reported as VERT_DATUM_UNKNOWN, never silently accepted).
VERTICAL_CS_NAMES: Dict[int, str] = {
    4979: "WGS 84 3D (ellipsoidal heights)",
    5703: "NAVD88 height (ftUS/ft) - North American Vertical Datum",
    5714: "MSL height (EPSG:5714)",
    3855: "EGM2008 geoid height",
    5621: "EGM96 geoid height",
}

# GeoTIFF VerticalDatumGeoKey semantic codes.
VERTICAL_DATUM_NAMES: Dict[int, str] = {
    1: "unknown / undocumented",
    2: "ellipsoidal (geodetic) datum",
    3: "mean sea level datum",
    4: "local datum",
    5: "geoid model derived",
    6: "depth (sounding) datum",
    7: "tidal datum",
}

# GeoTIFF VerticalUnitsGeoKey codes.
VERTICAL_UNITS_NAMES: Dict[int, str] = {
    9001: "metre",
    9002: "foot (international)",
    9003: "foot (US survey)",
}

_WKT_VERTCS_RE = re.compile(r"VERTCS\[\s*\"([^\"]+)\"", re.I)
_WKT_ELLIPS_HINT_RE = re.compile(r"ellipsoid|geodetic", re.I)
_WKT_MSL_HINT_RE = re.compile(r"mean\s+sea\s+level|MSL|geoid", re.I)

# LAS ~Well mnemonics that sometimes carry a depth datum hint.
_LAS_DATUM_HINTS = ("KB", "GL", "DF", "DATM", "EGL", "MSL")

VERT_CODES = {
    "VERT_DATUM_OK": "info",
    "VERT_DATUM_MISSING": "warning",
    "VERT_DATUM_UNKNOWN": "warning",
    "VERT_UNITS_NOT_METRE": "warning",
    "VERT_UNITS_MISSING": "warning",
    "VERT_DATUM_CONFLICT": "error",
    "VERT_DEPTH_DATUM_UNDECLARED": "warning",
    "VERT_WKT_VERTCS_UNREADABLE": "warning",
}


def _vf(code: str, message: str) -> dict:
    return {"code": code, "severity": VERT_CODES[code], "message": message}


def classify_vertical_geokeys(geokeys: Dict[int, object]) -> Optional[dict]:
    """Classify the vertical claim carried by GeoTIFF GeoKeys, if any."""
    cs = geokeys.get(4096) if isinstance(geokeys.get(4096), int) else None
    datum = geokeys.get(4097) if isinstance(geokeys.get(4097), int) else None
    units = geokeys.get(4098) if isinstance(geokeys.get(4098), int) else None
    if cs is None and datum is None and units is None:
        return None
    return {
        "cs": cs, "datum": datum, "units": units,
        "cs_name": VERTICAL_CS_NAMES.get(cs) if cs else None,
        "datum_name": VERTICAL_DATUM_NAMES.get(datum) if datum else None,
        "units_name": VERTICAL_UNITS_NAMES.get(units) if units else None,
    }


def vertical_findings(v: Optional[dict]) -> List[dict]:
    """Findings for a GeoTIFF vertical classification (or absence of one)."""
    if v is None:
        return [_vf("VERT_DATUM_MISSING",
                    "no vertical CRS keys (4096/4097/4098): elevation datum "
                    "is undeclared — heights are unanchored")]
    findings: List[dict] = []
    if v["cs"] is not None and v["cs"] not in VERTICAL_CS_NAMES:
        findings.append(_vf("VERT_DATUM_UNKNOWN",
                            f"vertical CS code {v['cs']} is outside the "
                            f"recognized set — datum claim unverifiable"))
    if v["units"] is None:
        findings.append(_vf("VERT_UNITS_MISSING",
                            "vertical units not declared (VerticalUnitsGeoKey)"))
    elif v["units"] != 9001:
        findings.append(_vf("VERT_UNITS_NOT_METRE",
                            f"vertical units are {v['units_name']} "
                            f"(code {v['units']}), not metre"))
    if not findings and v.get("cs_name"):
        findings.append(_vf("VERT_DATUM_OK", f"vertical reference: "
                            f"{v['cs_name']} ({v['units_name']})"))
    return findings


def vertical_evidence(v: Optional[dict]) -> dict:
    """Evidence triple for the vertical claim of a raster."""
    read, verified, unverifiable = [], [], []
    if v is None:
        return compile_evidence([], [], [ev_unverifiable(
            "VERT_DATUM_MISSING",
            "file carries no vertical reference claim",
            reason="GeoTIFF vertical keys absent; any datum "
                   "assumption would be invented by us")])
    read.append(ev_read("VERT_CLAIM_READ",
                        f"vertical CS={v['cs']} datum={v['datum']} "
                        f"units={v['units']}"))
    if v.get("cs_name"):
        verified.append(ev_verified(
            "VERT_DATUM_RECOGNIZED", f"vertical CS {v['cs']} = {v['cs_name']}",
            check="code is in the closed recognized table (VERTICAL_CS_NAMES)"))
    if v["cs"] is not None and not v.get("cs_name"):
        unverifiable.append(ev_unverifiable(
            "VERT_DATUM_UNKNOWN", f"vertical CS code {v['cs']} unrecognized",
            reason="outside the closed recognized table; the layer refuses "
                   "to guess"))
    if v["units"] != 9001 and v["units"] is not None:
        unverifiable.append(ev_unverifiable(
            "VERT_UNITS_NOT_METRE", f"vertical units {v['units_name']}",
            reason="non-metre units downstream mean every z math must "
                   "convert first; kept as an explicit claim, not converted"))
    return compile_evidence(read, verified, unverifiable)


def wkt_vertical(wkt: Optional[str]) -> Optional[dict]:
    """Extract a (honest, minimal) vertical claim from a WKT string."""
    if not wkt:
        return None
    m = _WKT_VERTCS_RE.search(wkt)
    if not m:
        return None
    name = m.group(1)
    return {"name": name,
            "ellipsoidal_hint": bool(_WKT_ELLIPS_HINT_RE.search(wkt)),
            "msl_hint": bool(_WKT_MSL_HINT_RE.search(wkt))}


def check_vertical_consistency(geokeys_v: Optional[dict],
                               wkt_v: Optional[dict]) -> List[dict]:
    """Cross-check GeoTIFF vertical keys against a WKT VERTCS claim."""
    if geokeys_v is None or wkt_v is None:
        return []
    gk_datum = geokeys_v.get("datum_name") or ""
    gk_msl = "sea level" in gk_datum.lower()
    gk_ell = "ellipsoidal" in gk_datum.lower()
    if wkt_v["ellipsoidal_hint"] and gk_msl:
        return [_vf("VERT_DATUM_CONFLICT",
                    f"WKT VERTCS claims ellipsoidal heights while GeoTIFF "
                    f"datum key says '{gk_datum}' — one of them is wrong")]
    if wkt_v["msl_hint"] and gk_ell:
        return [_vf("VERT_DATUM_CONFLICT",
                    f"WKT VERTCS claims MSL/geoid heights while GeoTIFF "
                    f"datum key says '{gk_datum}' — one of them is wrong")]
    return []


def wkt_vertical_evidence(wkt_v: Optional[dict]) -> dict:
    """Evidence for a WKT-carried vertical claim (e.g. GPKG srs definition)."""
    if wkt_v is None:
        return compile_evidence([], [], [ev_unverifiable(
            "VERT_WKT_VERTCS_UNREADABLE",
            "WKT carries no VERTCS block",
            reason="no vertical component declared in the "
                   "definition; nothing to confirm")])
    read = [ev_read("VERT_WKT_READ", f"WKT VERTCS '{wkt_v['name']}'")]
    return compile_evidence(read, [], [ev_unverifiable(
        "VERT_WKT_NAME_ONLY",
        f"vertical datum '{wkt_v['name']}' read from WKT",
        reason="WKT name is a declaration; no independent "
               "anchor in this file confirms it")])


def las_depth_datum(well_mnemonics: List[str]) -> Tuple[List[dict], dict]:
    """Well-log depth datum check: LAS 1.2/2.0 has no machine datum field.

    Depth below KB (Kelly Bushing), GL (ground level), DF (derrick floor) or
    MSL differ by metres — the file either declares it or the layer must say
    it cannot know.
    """
    upper = {str(m).upper() for m in well_mnemonics}
    hints = [h for h in _LAS_DATUM_HINTS if h in upper]
    if hints:
        finding = [_vf("VERT_DEPTH_DATUM_UNDECLARED",
                       f"depth-datum hints found ({', '.join(hints)}) but LAS "
                       f"carries no machine-readable datum field")]
        evidence = compile_evidence(
            [ev_read("VERT_LAS_DATUM_HINT",
                     f"~Well mnemonics hint a datum: {', '.join(hints)}")],
            [],
            [ev_unverifiable(
                "VERT_LAS_DATUM_HINT",
                "depth datum inferred from curve mnemonics",
                reason="free-text hint; not a machine-readable "
                       "declaration")])
    else:
        finding = [_vf("VERT_DEPTH_DATUM_UNDECLARED",
                       "no depth datum (KB/GL/DF/MSL) declared — depths are "
                       "unanchored relative to any vertical reference")]
        evidence = compile_evidence([], [], [ev_unverifiable(
            "VERT_DEPTH_DATUM_UNDECLARED",
            "depth datum undeclared in ~Well section",
            reason="LAS 1.2/2.0 has no datum field; depth "
                   "meaning must come from external "
                   "metadata")])
    return finding, evidence
