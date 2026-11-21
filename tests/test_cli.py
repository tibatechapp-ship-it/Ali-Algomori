import json

import pytest

from geologia.cli import main


def _out_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_plan_ok(capsys):
    code = main(["plan", "تحليل المياه الجوفية حول المنطقة"])
    assert code == 0
    plan = _out_json(capsys)
    assert plan["plan_only"] is True
    assert plan["matched_domains"] == ["hydrology"]


def test_cli_plan_unknown_exit_code_2(capsys):
    # Design: machine-readable error JSON on stdout (pipe-able), human hint on stderr.
    code = main(["plan", "مرحبا"])
    assert code == 2
    captured = capsys.readouterr()
    err = json.loads(captured.out)
    assert err["error"] == "unknown_domain"
    assert "gis" in err["supported_domains"]
    assert "المجالات المدعومة" in captured.err


def test_cli_plan_bbox_and_lang(capsys):
    code = main(
        ["plan", "groundwater risk assessment", "--lang", "en",
         "--bbox", "43.8", "14.9", "44.6", "15.7"]
    )
    assert code == 0
    plan = _out_json(capsys)
    assert plan["language"] == "en"
    assert plan["aoi_bbox"] == [43.8, 14.9, 44.6, 15.7]


def test_cli_domains(capsys):
    assert main(["domains"]) == 0
    body = _out_json(capsys)
    assert body["count"] == 9


def test_cli_engines_all_and_filtered(capsys):
    assert main(["engines"]) == 0
    body = _out_json(capsys)
    # 30 third-party cards + first-party certified-track engines
    assert body["count"] == 31
    assert sum(1 for e in body["engines"] if e["family"] == "third_party") == 30
    assert main(["engines", "--domain", "geophysics"]) == 0
    body = _out_json(capsys)
    assert body["count"] == 3
    assert {e["engine_id"] for e in body["engines"]} == {"simpeg", "pygimli", "madagascar"}


def test_cli_engine_detail_and_unknown(capsys):
    assert main(["engine", "lasio"]) == 0
    assert _out_json(capsys)["domain"] == "well_logs"
    assert main(["engine", "not-real"]) == 2


def test_cli_version_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
