# The agent-level vertical refusal rule (T4.2) — coded, tested, un-bypassable.
#
# Approved-plan wording, executed literally: any answer that involves a
# vertical elevation or a transformation between vertical references returns
# an explicit, CODED refusal (task-gate style, 409) when there is no loaded
# AND independently verified geoid grid. No approximate value, no silent
# assumption of sea level (ADR-0008 lineage: "الارتفاع بلا مرجع يبقى غير
# قابل للتأكيد").
#
# Gate completeness = all eight geoid gates recorded AND the independent
# implementation crosscheck PASSED. A grid that is loaded but unverified is
# refused too — honest posture beats useful-looking nonsense.
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from geologia.data_layer.geoid import parse_grid_file, undulation_at

DEFAULT_REGISTRY = (Path(__file__).parents[1] / "data" / "reference"
                    / "geoid_grid_registry.json")

REQUIRED_GATES = ("sha256", "license", "tide_system", "grid_coords",
                  "interpolation", "crs_pair", "validity_domain")

VERT_REF_UNAVAILABLE = "VERTICAL_REF_UNAVAILABLE"
VERT_REF_UNVERIFIED = "VERTICAL_REF_UNVERIFIED"
VERT_GRID_FILE_MISSING = "VERTICAL_GRID_FILE_MISSING"
VERT_OUT_OF_DOMAIN = "VERTICAL_OUT_OF_DOMAIN"

_MSG = {
    VERT_REF_UNAVAILABLE: {
        "ar": "لا مرجع جيويد محمّل ومتحقق — الارتفاع الرأسي يبقى غير قابل "
              "للتأكيد: لا قيمة تقريبية ولا افتراض صامت لمستوى سطح البحر.",
        "en": "No loaded and verified geoid reference — vertical elevation "
              "stays unverifiable: no approximate value, no silent MSL.",
    },
    VERT_REF_UNVERIFIED: {
        "ar": "الشبكة محمّلة لكن التحقق المستقل لم يجتز — الرفض صادق حتى "
              "يجتاز المطابقة المستقلة.",
        "en": "Grid loaded but the independent crosscheck has not passed — "
              "refusing honestly until it does.",
    },
    VERT_GRID_FILE_MISSING: {
        "ar": "الشبكة مسجّلة بالبصمة لكن ملفها غير موجود في مسار الشبكات "
              "المعلن.",
        "en": "Grid registered by fingerprint but its file is absent from "
              "the declared grid directory.",
    },
    VERT_OUT_OF_DOMAIN: {
        "ar": "النقطة خارج مجال صلاحية الشبكة المثبتة — لا استيفاء خارج "
              "المجال ولا تخمين.",
        "en": "Point outside the pinned grid's validity domain — no "
              "extrapolation, no guessing.",
    },
}

_GRID_CACHE: dict = {}


def _load_grid(path: str):
    key = path
    stat = Path(path).stat()
    sig = (stat.st_size, stat.st_mtime)
    hit = _GRID_CACHE.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    grid = parse_grid_file(path)
    _GRID_CACHE[key] = (sig, grid)
    return grid


def registry_path(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("GEOLOGIA_GEOID_REGISTRY", "")
    if env:
        return Path(env)
    return DEFAULT_REGISTRY


def _refusal(code: str, missing=None, extra=None) -> dict:
    body = {
        "status": 409,
        "error": code,
        "message_ar": _MSG[code]["ar"],
        "message_en": _MSG[code]["en"],
        "missing": missing or [],
    }
    if extra:
        body.update(extra)
    return body


def answer_vertical(lat: float, lon: float, model: str = "EGM96",
                    registry_path_arg: Optional[str] = None,
                    grid_dir: Optional[str] = None) -> dict:
    """The single vertical-answer entry the agent layer may call."""
    rp = registry_path(registry_path_arg)
    if not rp.exists():
        return _refusal(VERT_REF_UNAVAILABLE,
                        missing=[f"registry not found: {rp.name}"])
    import json
    raw = json.loads(rp.read_text(encoding="utf-8"))
    record = next((g for g in raw.get("grids", [])
                   if g.get("model_id") == model and g.get("status")
                   == "recorded"), None)
    if record is None:
        return _refusal(VERT_REF_UNAVAILABLE,
                        missing=[f"no recorded grid for model {model!r}"])

    gates = record.get("gates", {})
    incomplete = [g for g in REQUIRED_GATES
                  if not gates.get(g)
                  or gates.get(g) in ("not_recorded", None)]
    if incomplete:
        return _refusal(VERT_REF_UNAVAILABLE,
                        missing=[f"gate not recorded: {g}" for g in incomplete])
    check = str(gates.get("independent_check", ""))
    if not check.startswith("passed"):
        return _refusal(VERT_REF_UNVERIFIED,
                        extra={"independent_check": check or "pending"})

    gdir = grid_dir or os.environ.get("GEOLOGIA_GEOID_GRID_DIR") \
        or record.get("grid_dir")
    if not gdir:
        return _refusal(VERT_GRID_FILE_MISSING,
                        extra={"hint": "set GEOLOGIA_GEOID_GRID_DIR or pass "
                                       "grid_dir"})
    gpath = Path(gdir) / record["file_name"]
    if not gpath.exists():
        return _refusal(VERT_GRID_FILE_MISSING,
                        extra={"expected_path": str(gpath)})

    sha_now = None
    import hashlib
    sha_now = hashlib.sha256(gpath.read_bytes()).hexdigest()
    if sha_now != gates["sha256"]:
        return _refusal(VERT_REF_UNAVAILABLE,
                        missing=["grid file fingerprint changed on disk "
                                 f"({gpath}) — refuse, never re-trust "
                                 "silently"])

    domain = gates["validity_domain"]
    if not (domain["lat"][0] <= lat <= domain["lat"][1]
            and domain["lon"][0] <= lon <= domain["lon"][1]):
        return _refusal(VERT_OUT_OF_DOMAIN,
                        extra={"validity_domain": domain,
                               "requested": {"lat": lat, "lon": lon}})

    grid = _load_grid(str(gpath))
    undulation = undulation_at(grid, lat, lon)
    if undulation is None:
        return _refusal(VERT_OUT_OF_DOMAIN,
                        extra={"validity_domain": domain,
                               "requested": {"lat": lat, "lon": lon}})
    return {
        "status": 200,
        "model": model,
        "lat": lat,
        "lon": lon,
        "undulation_m": round(undulation, 4),
        "interpolation": gates["interpolation"],
        "grid_sha256": gates["sha256"],
        "independent_check": check,
        "note_ar": "تعويض جيويد من الشبكة المثبتة عبر بوابة مستقلة — "
                   "الارتفاع النهائي يحتاج المرجع الرأسي المعلن للطلب.",
        "note_en": "Geoid undulation from the pinned grid via the honest "
                   "gate — a final elevation still needs the declared "
                   "vertical reference of the request.",
    }
