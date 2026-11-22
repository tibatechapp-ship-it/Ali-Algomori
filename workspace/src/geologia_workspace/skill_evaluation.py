"""Versioned offline benchmark for Ali's multilingual request-routing skill."""
from __future__ import annotations

from geologia_workspace.planner import classify_request

BENCHMARK_VERSION = "1.0.0"
# Curated smoke/regression set, not a representative scientific evaluation set.
_CASES = (
    ("ar_well_logs", "سجلات الآبار والمسامية", {"well_logs"}),
    ("en_well_logs", "LAS well log porosity", {"well_logs"}),
    ("ar_hydrology", "المياه الجوفية ومنسوب الماء", {"hydrology"}),
    ("en_hydrology", "groundwater aquifer water table", {"hydrology"}),
    ("ru_hydrology", "подземные воды и водоносный горизонт", {"hydrology"}),
    ("ar_geology3d", "مقطع جيولوجي ثلاثي الأبعاد", {"geology3d"}),
    ("en_geology3d", "3D geological model structural geology", {"geology3d"}),
    ("zh_geology3d", "三维地质建模和断层", {"geology3d"}),
    ("ar_seismology", "دراسة الزلازل والموجات الزلزالية", {"seismology"}),
    ("en_seismology", "earthquake waveform ground motion", {"seismology"}),
    ("zh_seismology", "地震波与地震目录", {"seismology"}),
    ("ar_geophysics", "تصوير كهربائي ومقاومة نوعية", {"geophysics"}),
    ("en_geophysics", "geophysical resistivity inversion", {"geophysics"}),
    ("ar_geochemistry", "تحليل كيميائي للصخور", {"geochemistry"}),
    ("en_geochemistry", "Geochemistry elemental analysis", {"geochemistry"}),
    ("ar_exploration", "استكشاف معدني للذهب والتنقيب", {"exploration"}),
    ("en_exploration", "mineral exploration prospectivity", {"exploration"}),
    ("ar_remote_sensing", "صور فضائية واستشعار عن بعد", {"remote_sensing"}),
    ("en_remote_sensing", "remote sensing satellite imagery photogrammetry", {"remote_sensing"}),
    ("ar_gis", "نظم المعلومات الجغرافية وخرائط الطبقات", {"gis"}),
    ("en_gis", "GIS maps layers geographic information system", {"gis"}),
    ("ru_gis", "геоинформационная система карта слои", {"gis"}),
    ("zh_gis", "地理信息系统与坐标参考系", {"gis"}),
    ("ambiguous_no_fallback", "Please analyze this area", set()),
)


def evaluate_routing_benchmark() -> dict:
    """Evaluate deterministic routing against the fixed versioned cases."""
    outcomes = []
    expected_tags = correct_tags = 0
    exact = 0
    for case_id, request, expected in _CASES:
        actual = set(classify_request(request)["matched_domains"])
        matched = actual == expected
        exact += int(matched)
        expected_tags += len(expected)
        correct_tags += len(actual & expected)
        outcomes.append({
            "case_id": case_id,
            "expected_domains": sorted(expected),
            "actual_domains": sorted(actual),
            "passed": matched,
        })
    count = len(_CASES)
    return {
        "benchmark_id": "ali-routing-multilingual",
        "benchmark_version": BENCHMARK_VERSION,
        "status": "passed" if exact == count else "failed",
        "case_count": count,
        "exact_match_count": exact,
        "exact_match_accuracy": exact / count,
        "expected_domain_recall": correct_tags / expected_tags if expected_tags else 1.0,
        "unexpected_domain_count": sum(
            len(set(item["actual_domains"]) - set(item["expected_domains"]))
            for item in outcomes
        ),
        "cases": outcomes,
        "scope": "curated deterministic routing regression only",
        "not_evaluated": [
            "scientific correctness", "engine execution", "real-world domain mastery",
            "routing confidence calibration", "representative field performance",
        ],
    }
