# First-party scientific engine: density-log porosity (porosity_density_v1).
#
# Deterministic, dependency-free (stdlib only), fully documented. The binding
# acceptance standard (digest_10) requires a documented scientific engine whose
# results carry citations, parameters, uncertainty bounds and validity limits.
# Negative porosities are REPORTED, never silently clamped — zero hallucination
# applies to numbers as well as text.
#
# Formula:  phi_D = (rho_ma - rho_b) / (rho_ma - rho_fl)
#   Asquith, G.B., Krygowski, D. (2004). Basic Well Log Analysis, 2nd ed.
#   AAPG Methods in Exploration 16 - density porosity equation.
#   Rider, M., Kennedy, M. (2011). The Geological Interpretation of Well Logs,
#   3rd ed. - density log; grain/fluid density defaults.
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

ENGINE_ID = "porosity_density_v1"
ENGINE_VERSION = "1.0.0"

FORMULA = "phi_D = (rho_ma - rho_b) / (rho_ma - rho_fl)"

CITATIONS = [
    "Asquith, G.B., Krygowski, D. (2004). Basic Well Log Analysis, 2nd ed. "
    "AAPG Methods in Exploration 16 - density porosity equation.",
    "Rider, M., Kennedy, M. (2011). The Geological Interpretation of Well Logs, "
    "3rd ed. - density log; grain/fluid density defaults.",
]

_ALLOWED_RHO_MA = {"sandstone": 2.65, "limestone": 2.71, "dolomite": 2.87}
_RHO_FL_RANGE = (0.90, 1.20)   # fresh water .. saline brine range
_SIGMA_RHOB_RANGE = (0.001, 0.100)

VALIDITY_LIMITS_AR = [
    "الصيغة تفترض كثافة مصفوفة رملية (ρma = 2.65)؛ للكلس 2.71 وللدولوميت 2.87 — "
    "خارج ذلك النطاق الصيغة غير صالحة",
    "تفترض ماء عذب في المسام (ρfl = 1.00)؛ الماء المالح (1.05-1.10) والهيدروكربونات "
    "تغيّر ρfl",
    "لا تصحيح لضغط التحدم أو انحراف البئر أو المياه المتبقية في الشعيرات",
    "القيم السلبية تُعلن كما هي (ضجيج قياس أو افتراض مصفوفة خاطئ) ولا تُقصّ بصمت",
]

DISCLAIMERS_AR = [
    "النتائج حساب حتمي للصيغة المعلنة على المدخلات المعلنة فقط — ليست تفسيراً جيولوجياً",
    "أي استنتاج طبقي أو مخزني يتطلب دمج سجلات أخرى ومراجعة بشرية مستقلة",
]


class PorosityEngineError(ValueError):
    """Refuse to compute instead of producing an unverified result."""


def _parse_las(path: Path) -> dict:
    """Minimal self-contained LAS reader (own parser, no shared code)."""
    well: Dict[str, str] = {}
    curves: List[str] = []
    rows: List[List[float]] = []
    current = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("~"):
            current = s[1:2].upper()
            continue
        if not s or s.startswith("#") or current is None:
            continue
        if current == "W" and "." in s:
            key = s.split(".", 1)[0].strip().upper()
            rest = s.split(".", 1)[1]
            well[key] = rest.split(":", 1)[0].strip()
        elif current == "C" and "." in s:
            curves.append(s.split(".", 1)[0].strip().upper())
        elif current == "A":
            try:
                rows.append([float(t) for t in s.split()])
            except ValueError as exc:
                raise PorosityEngineError(f"non-numeric data row: {s!r} ({exc})")
    return {"well": well, "curves": curves, "rows": rows}


def _resolve_params(params: Optional[dict]) -> dict:
    p = dict(params or {})
    matrix = p.get("matrix", "sandstone")
    rho_ma = p.get("rho_ma_gcm3", _ALLOWED_RHO_MA.get(matrix))
    if rho_ma not in _ALLOWED_RHO_MA.values():
        raise PorosityEngineError(
            f"rho_ma_gcm3 {rho_ma!r} not allowed; allowed "
            f"{sorted(set(_ALLOWED_RHO_MA.values()))} (sandstone/limestone/dolomite)")
    rho_fl = p.get("rho_fl_gcm3", 1.00)
    if not (_RHO_FL_RANGE[0] <= float(rho_fl) <= _RHO_FL_RANGE[1]):
        raise PorosityEngineError(
            f"rho_fl_gcm3 {rho_fl!r} outside plausible fluid range {_RHO_FL_RANGE}")
    sigma = p.get("sigma_rhob_gcm3", 0.015)
    if not (_SIGMA_RHOB_RANGE[0] <= float(sigma) <= _SIGMA_RHOB_RANGE[1]):
        raise PorosityEngineError(
            f"sigma_rhob_gcm3 {sigma!r} outside {_SIGMA_RHOB_RANGE}")
    matrix_name = next((k for k, v in _ALLOWED_RHO_MA.items() if v == rho_ma), matrix)
    return {
        "rho_ma_gcm3": float(rho_ma),
        "rho_fl_gcm3": float(rho_fl),
        "sigma_rhob_gcm3": float(sigma),
        "matrix": matrix_name,
        "fluid": p.get("fluid", "fresh_water"),
    }


def run_porosity_density(input_path: str, params: Optional[dict] = None) -> dict:
    """Compute density-log porosity with full evidence and uncertainty bounds.

    Negative porosities are reported raw with a NEGATIVE_POROSITY flag — no
    silent clamping. NULL rows yield porosity=None with a NULL_VALUE flag.
    """
    p = _resolve_params(params)
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input LAS not found: {input_path}")
    las = _parse_las(path)
    curves, rows = las["curves"], las["rows"]
    if "RHOB" not in curves:
        raise PorosityEngineError(
            f"no RHOB curve in {path.name}; found curves: {curves}")
    if not rows:
        raise PorosityEngineError("LAS has no data rows in ~A")
    width = len(curves)
    bad_width = [i for i, r in enumerate(rows) if len(r) != width]
    if bad_width:
        raise PorosityEngineError(
            f"rows with wrong width at line {bad_width[:3]}: expected {width} columns")
    rhob_i = curves.index("RHOB")
    null = float(las["well"].get("NULL", -999.25)) if las["well"].get("NULL") else -999.25

    denom = p["rho_ma_gcm3"] - p["rho_fl_gcm3"]
    sigma_phi = p["sigma_rhob_gcm3"] / denom

    results: List[dict] = []
    issues: Dict[str, int] = {}
    for r in rows:
        depth, rhob = r[0], r[rhob_i]
        flag: Optional[str] = None
        if math.isclose(rhob, null, abs_tol=1e-9):
            phi = None
            flag = "NULL_VALUE"
        else:
            phi = (p["rho_ma_gcm3"] - rhob) / denom
            if phi < 0:
                flag = "NEGATIVE_POROSITY"
        if flag:
            issues[flag] = issues.get(flag, 0) + 1
        results.append({
            "depth_m": depth,
            "rhob_gcm3": rhob,
            "porosity_vv": phi,
            "porosity_pct": None if phi is None else phi * 100,
            "flag": flag,
        })

    issue_list = [{
        "code": code,
        "count": n,
        "note_ar": (
            "قيمة مسامية سالبة: ضجيج قياس أو افتراض مصفوفة خاطئ — تُعلن ولا تُقصّ"
            if code == "NEGATIVE_POROSITY" else
            "صفوف NULL لم تُحسب"
        ),
    } for code, n in sorted(issues.items())]

    return {
        "engine_id": ENGINE_ID,
        "engine_version": ENGINE_VERSION,
        "family": "first_party",
        "deterministic": True,
        "third_party_dependencies": [],
        "formula": FORMULA,
        "citations": CITATIONS,
        "params": p,
        "input": {
            "file": str(path),
            "well": las["well"].get("WELL", ""),
            "strt_m": float(las["well"]["STRT"]) if las["well"].get("STRT") else None,
            "stop_m": float(las["well"]["STOP"]) if las["well"].get("STOP") else None,
            "step_m": float(las["well"]["STEP"]) if las["well"].get("STEP") else None,
            "null_value": null,
            "n_rows": len(rows),
            "curve_used": "RHOB",
            "unit": "g/cm3",
        },
        "results": results,
        "issues": issue_list,
        "uncertainty": {
            "sigma_phi_vv": sigma_phi,
            "sigma_rhob_gcm3": p["sigma_rhob_gcm3"],
            "method": "first-order propagation of bulk-density tool error "
                      "(dphi = drhob / (rho_ma - rho_fl))",
            "note_ar": "حدود ±1σ افتراض خطأ أداة موثق — ليس عدم يقين جيولوجياً",
        },
        "validity_limits_ar": VALIDITY_LIMITS_AR,
        "disclaimers_ar": DISCLAIMERS_AR,
        "no_generated_content": True,
    }
