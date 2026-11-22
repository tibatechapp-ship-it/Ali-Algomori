"""UI contract tests for the offline, validation-gated map view.

The Phase-2 display layer must stay dependency-free (no CDN, no tile
servers) and must draw only what the gated /display endpoint returns:
"no drawing before verification" is enforced client-side as well.
"""
from pathlib import Path

ROOT = Path(__file__).parents[1]
WEB = ROOT / "src" / "geologia_workspace" / "web"


def test_no_external_map_dependencies_in_web_assets():
    for name in ("index.html", "app.js", "style.css", "service-worker.js"):
        content = (WEB / name).read_text(encoding="utf-8").lower()
        for marker in ("unpkg", "leaflet", "openstreetmap", "cdn"):
            assert marker not in content, f"{name} references {marker}"


def test_index_attribution_declares_offline_vector_display():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'data-i18n="mapOfflineNote"' in html
    assert "EPSG:4326" in html
    assert "no basemap tiles" in html or "بلا بلاطات أساس" in html


def test_map_renders_through_the_gated_display_endpoint():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert '"/api/v1/datasets/"+encodeURIComponent(datasetId)+"/display"' in script
    assert '"/geojson"' not in script


def test_map_refusal_branch_clears_features_without_drawing():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert "mapFeatures=[];drawMap();mapMessage(tr(\"mapRefused\")" in script
    assert "truth_class" not in script  # classification lives in the API envelope


def test_map_renderer_is_dependency_free_svg():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert "createElementNS" in script
    assert "map-graticule" in script
    assert "projectLonLat" in script
    assert "collectMapBbox" in script
    assert "innerHTML" not in script


def test_map_feature_info_uses_text_nodes_only():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert "showFeatureInfo" in script
    assert "textContent=typeof value===\"string\"?value:JSON.stringify(value)" in script
    styles = (WEB / "style.css").read_text(encoding="utf-8")
    assert ".map-feature-info" in styles
    assert ".map-graticule" in styles


def test_map_panel_element_ids_are_present():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for element_id in ("geoMap", "mapDataset", "mapStatus", "mapFeatureInfo",
                       "targetCrs", "reprojectButton"):
        assert f'id="{element_id}"' in html


def test_service_worker_still_caches_shell_without_api_data():
    worker = (WEB / "service-worker.js").read_text(encoding="utf-8")
    assert '"/app.js"' in worker
    assert "/api/" in worker  # cache exclusion rule stays intact
