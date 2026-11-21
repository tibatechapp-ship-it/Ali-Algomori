import pytest

from geologia.planner import (
    SUPPORTED_DOMAINS,
    UnknownDomainError,
    build_plan,
    match_domains,
)
from geologia.registry import ENGINES


def test_plan_3d_english():
    plan = build_plan("Build a 3D geological model and cross-section", language="en")
    assert "geology3d" in plan["matched_domains"]
    assert "gempy" in plan["steps"][0]["candidate_engines"]
    assert plan["scientific_gates"][0] == "Is the data sufficient?"


def test_unknown_request_raises_instead_of_fabricating_gis():
    # Honesty gate: v0.1 silently produced a GIS plan for "مرحبا".
    with pytest.raises(UnknownDomainError) as exc:
        build_plan("مرحبا")
    assert exc.value.supported_domains == list(SUPPORTED_DOMAINS)
    assert "gis" in exc.value.supported_domains


def test_unknown_english_message():
    with pytest.raises(UnknownDomainError) as exc:
        build_plan("hello there friend", language="en")
    assert "fabricated" in exc.value.message


def test_plan_multi_intent():
    plan = build_plan("حلل المياه الجوفية وأنشئ نموذج ثلاثي الأبعاد")
    assert "hydrology" in plan["matched_domains"]
    assert "geology3d" in plan["matched_domains"]
    assert "dem" in plan["required_inputs"]


def test_plan_disclaimer_and_gates():
    plan = build_plan("استكشاف الذهب في المنطقة")
    assert "exploration" in plan["matched_domains"]
    assert len(plan["scientific_gates"]) == 7
    assert "خريطة وحدها" in plan["disclaimer"]


def test_geophysics_routing_arabic():
    # v0.1 silently fell back to gis for geophysics requests.
    plan = build_plan("عكس جيوفيزيائي كهرومغناطيسي للمنطقة")
    assert plan["matched_domains"] == ["geophysics"]
    engines = plan["steps"][0]["candidate_engines"]
    assert "simpeg" in engines and "pygimli" in engines


def test_geophysics_routing_english():
    plan = build_plan("ERT tomography survey interpretation")
    assert plan["matched_domains"] == ["geophysics"]


def test_well_log_las_not_hydrology():
    # v0.1 misrouted LAS/well-log requests to hydrology via "بئر"/"well".
    plan = build_plan("تحليل سجل LAS للبئر رقم 5")
    assert plan["matched_domains"] == ["well_logs"]
    assert "lasio" in plan["steps"][0]["candidate_engines"]


def test_well_log_english_not_hydrology():
    plan = build_plan("LAS well log analysis for well 5")
    assert plan["matched_domains"] == ["well_logs"]


def test_groundwater_plus_well_logs_both_kept():
    # Independent hydrology keywords keep hydrology alongside well_logs.
    plan = build_plan("تحليل المياه الجوفية وسجلات الآبار معاً")
    assert set(plan["matched_domains"]) == {"hydrology", "well_logs"}


def test_tashkeel_does_not_break_matching():
    plan = build_plan("المِيَاهُ الجَوْفِيَّة حَوْل الْمِنْطَقَة")
    assert plan["matched_domains"] == ["hydrology"]


def test_hamza_variants_do_not_break_matching():
    plan = build_plan("دراسة الابار الارتوازية")  # no hamza on alef
    assert plan["matched_domains"] == ["hydrology"]


def test_seismic_reflection_beats_generic_seismic():
    plan = build_plan("معالجة انعكاسية لبيانات سيزمية")
    assert plan["matched_domains"] == ["geophysics"]
    assert "madagascar" in plan["steps"][0]["candidate_engines"]


def test_seismic_hazard_stays_seismology():
    plan = build_plan("حساب الخطر الزلزالي لصنعاء")
    assert plan["matched_domains"] == ["seismology"]


def test_candidate_engines_always_from_registry():
    # No engine may appear outside its registry domain.
    domain_of = {e["engine_id"]: e["domain"] for e in ENGINES}
    plan = build_plan("تحليل المياه الجوفية وأنشئ نموذج ثلاثي الأبعاد وخرائط")
    for step in plan["steps"]:
        for engine_id in step["candidate_engines"]:
            assert domain_of[engine_id] == step["domain"]


def test_every_intent_domain_exists_in_registry():
    registry_domains = {e["domain"] for e in ENGINES}
    assert set(SUPPORTED_DOMAINS) <= registry_domains


def test_plan_includes_matched_keywords_for_traceability():
    plan = build_plan("حلل المياه الجوفية وأنشئ نموذج ثلاثي الأبعاد")
    hydro = next(s for s in plan["steps"] if s["domain"] == "hydrology")
    assert any("مياه" in k for k in hydro["matched_keywords"])


def test_match_domains_scores_and_orders():
    matches = match_domains("المياه الجوفية وأنشئ نموذج ثلاثي الأبعاد")
    domains = [m["domain"] for m in matches]
    assert domains[0] == "hydrology"  # higher keyword score first
    assert "geology3d" in domains
    hydro = matches[0]
    assert hydro["score"] >= 2
    assert hydro["matched_keywords"]  # original keywords reported
    assert hydro["matched_keywords_norm"]  # canonical forms available
