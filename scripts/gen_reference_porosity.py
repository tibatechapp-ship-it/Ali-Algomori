#!/usr/bin/env python3
"""Generate the pinned reference results for the first-party engine
``porosity_density_v1`` — computed with EXACT rational arithmetic (fractions.Fraction),
independently of the engine's float implementation.

Formula (density-log porosity):
    phi_D = (rho_ma - rho_b) / (rho_ma - rho_fl)

Pinned parameter set (documented defaults):
    rho_ma = 2.65 g/cm3  (sandstone grain density)
    rho_fl = 1.00 g/cm3  (fresh-water filtrate density)
    sigma_rhob = 0.015 g/cm3 (conservative bulk-density tool error assumption)
    -> sigma_phi = sigma_rhob / (rho_ma - rho_fl)

Provenance / independence:
  * input  : tests/data/golden_las_valid.las (rows re-parsed here with plain
             string splitting, NOT by the engine's parser)
  * math   : fractions.Fraction on exact decimal literals, converted to float
             only at JSON write time
  * output : src/geologia/data/reference/porosity_density_v1_reference.json

Re-run from repo root:  python scripts/gen_reference_porosity.py
"""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LAS = ROOT / "tests" / "data" / "golden_las_valid.las"
OUT = ROOT / "src" / "geologia" / "data" / "reference" / "porosity_density_v1_reference.json"

RHO_MA = Fraction(265, 100)   # 2.65 g/cm3 sandstone
RHO_FL = Fraction(100, 100)   # 1.00 g/cm3 fresh water
SIGMA_RHOB = Fraction(15, 1000)  # 0.015 g/cm3
NULL_SENTINEL = Fraction(-99925, 100)  # -999.25


def parse_golden_rows(path: Path):
    """Independent minimal reader: returns [(depth, rhob), ...] from ~A rows."""
    rows = []
    in_data = False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("~"):
            in_data = s[1:2].upper() == "A"
            continue
        if in_data and s and not s.startswith("#"):
            cols = s.split()
            depth = Fraction(cols[0])
            rhob = Fraction(cols[1])
            rows.append((depth, rhob))
    return rows


def main() -> None:
    rows = parse_golden_rows(LAS)
    denominator = RHO_MA - RHO_FL  # 1.65
    sigma_phi = SIGMA_RHOB / denominator

    results = []
    negative = 0
    for depth, rhob in rows:
        if rhob == NULL_SENTINEL:
            results.append({"depth_m": float(depth), "porosity_vv": None,
                            "porosity_pct": None, "flag": "NULL_VALUE"})
            continue
        phi = (RHO_MA - rhob) / denominator
        flag = None
        if phi < 0:
            flag = "NEGATIVE_POROSITY"
            negative += 1
        results.append({
            "depth_m": float(depth),
            "porosity_vv": float(phi),
            "porosity_pct": float(phi * 100),
            "flag": flag,
        })

    digest = hashlib.sha256(LAS.read_bytes()).hexdigest()
    doc = {
        "engine_id": "porosity_density_v1",
        "reference_version": "1.0.0",
        "formula": "phi_D = (rho_ma - rho_b) / (rho_ma - rho_fl)",
        "input": {
            "file": "tests/data/golden_las_valid.las",
            "sha256": digest,
            "curve_used": "RHOB",
            "unit": "g/cm3",
        },
        "params": {
            "rho_ma_gcm3": float(RHO_MA),
            "rho_fl_gcm3": float(RHO_FL),
            "sigma_rhob_gcm3": float(SIGMA_RHOB),
            "matrix": "sandstone",
            "fluid": "fresh_water",
        },
        "expected": {
            "results": results,
            "sigma_phi_vv": float(sigma_phi),
            "negative_porosity_count": negative,
        },
        "tolerance": 1e-9,
        "provenance": {
            "computed_by": "scripts/gen_reference_porosity.py using fractions.Fraction "
                           "(exact rational arithmetic) on hand-parsed LAS rows - "
                           "independent of the engine's float implementation",
            "citations": [
                "Asquith, G.B., Krygowski, D. (2004). Basic Well Log Analysis, "
                "2nd ed. AAPG Methods in Exploration 16 - density porosity equation.",
                "Rider, M., Kennedy, M. (2011). The Geological Interpretation of "
                "Well Logs, 3rd ed. - density log, grain/fluid density defaults.",
            ],
            "note_ar": "القيم المرجعية مثبتة من الصيغة والمدخلات الذهبية بجبر نسبي دقيق؛ "
                       "أي انحراف بين المحرك والمرجع يتجاوز السماحية يفشل الاعتماد فوراً.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"input sha256: {digest}")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
