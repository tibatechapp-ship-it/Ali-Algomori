from geologia.planner import build_plan


def test_plan_3d_english():
    plan = build_plan("Build a 3D geological model and cross-section", language="en")
    assert "geology3d" in plan["matched_domains"]
    assert "gempy" in plan["steps"][0]["candidate_engines"]
    assert plan["scientific_gates"][0] == "Is the data sufficient?"


def test_plan_defaults_to_gis_baseline():
    plan = build_plan("مرحبا")
    assert plan["matched_domains"] == ["gis"]
    assert plan["plan_only"] is True


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
