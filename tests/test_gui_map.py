import json

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

pytest.importorskip("pydeck")
from crazy_buffer.gui.map_view import MAX_PREVIEW_FEATURES, build_map


def frame(geometries, crs="EPSG:4326"):
    return gpd.GeoDataFrame(
        {"id": [f"a{i}" for i in range(len(geometries))], "private": ["secret"] * len(geometries)},
        geometry=geometries, crs=crs,
    )


def serialized(deck):
    return json.loads(deck.to_json())


def test_projects_without_mutating_or_leaking_attributes():
    sources = frame([Point(116.4, 39.9)]).to_crs(32650)
    original = sources.copy(deep=True)
    deck, notices = build_map({"sources": sources}, {"sources_id": "id"})
    feature = serialized(deck)["layers"][0]["data"]["features"][0]
    assert feature["geometry"]["coordinates"] == pytest.approx([116.4, 39.9])
    assert feature["properties"] == {"identifier": "a0", "label": "研究对象"}
    assert "secret" not in deck.to_json()
    assert sources.equals(original)
    assert sources.crs == original.crs
    assert not notices
    assert "text" in deck._tooltip and "html" not in deck._tooltip


def test_polygon_buffer_uses_metres_and_preserves_source():
    source = frame([Polygon([(500000, 4400000), (500100, 4400000), (500100, 4400100), (500000, 4400100)])], 32650)
    deck, notices = build_map(
        {"sources": source},
        {"sources_id": "id", "task": "buffer", "radius_m": 100, "analysis_crs": "EPSG:32650"},
    )
    feature = serialized(deck)["layers"][0]["data"]["features"][0]
    actual = gpd.GeoDataFrame.from_features([feature], crs=4326).to_crs(32650)
    assert actual.geometry.iloc[0].area == pytest.approx(source.geometry.buffer(100, quad_segs=32).iloc[0].area, rel=1e-8)
    assert source.geometry.iloc[0].area == 10000
    assert not notices


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:3857", "bad"])
def test_bad_analysis_crs_keeps_input_visible(crs):
    deck, notices = build_map(
        {"sources": frame([Point(116.4, 39.9)])},
        {"task": "buffer", "radius_m": 1500, "analysis_crs": crs},
    )
    assert len(deck.layers) == 1
    assert any("缓冲" in message for message in notices)


def test_visibility_and_no_basemap():
    inputs = {"sources": frame([Point(116, 39)]), "targets": frame([Point(117, 40)])}
    deck, _ = build_map(inputs, {"task": "buffer"}, visible_roles={"targets"}, basemap=False)
    data = serialized(deck)
    assert [layer["id"] for layer in data["layers"]] == ["preview-targets"]
    assert data.get("mapProvider") is None
    assert data["mapStyle"] == "__MAP_STYLE__"
    empty, notices = build_map(inputs, {}, visible_roles=set())
    assert not empty.layers and not notices


def test_empty_uses_beijing_with_no_fake_features():
    deck, notices = build_map({}, {})
    assert not deck.layers
    assert deck.initial_view_state.longitude == 116.4
    assert deck.initial_view_state.latitude == 39.9
    assert not notices
    data = serialized(deck)
    assert isinstance(data["mapStyle"], str)
    assert data["mapStyle"] == "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    assert data["mapProvider"] == "carto"


def test_invalid_empty_nonfinite_and_out_of_range_are_skipped():
    sources = frame([None, Point(), Point(float("inf"), 1), Point(181, 30), Point(116, 39)])
    deck, notices = build_map({"sources": sources}, {})
    features = serialized(deck)["layers"][0]["data"]["features"]
    assert len(features) == 1
    assert len(notices) == 2
    assert "Infinity" not in deck.to_json()


def test_line_preview_and_budget_apply_to_buffers():
    sources = frame([Point(116.4, 39.9)] * (MAX_PREVIEW_FEATURES + 1))
    roads = frame([LineString([(116.4, 39.9), (116.5, 40)])])
    deck, notices = build_map(
        {"sources": sources, "edges": roads},
        {"task": "buffer", "radius_m": 50, "analysis_crs": "EPSG:32650"},
    )
    data = serialized(deck)
    assert len(data["layers"][0]["data"]["features"]) == MAX_PREVIEW_FEATURES
    assert len(data["layers"][2]["data"]["features"]) == MAX_PREVIEW_FEATURES
    assert data["layers"][1]["data"]["features"][0]["geometry"]["type"] == "LineString"
    assert any("2000" in message for message in notices)


def test_missing_crs_is_notice_not_crash():
    sources = frame([Point(1, 2)], crs=None)
    deck, notices = build_map({"sources": sources}, {})
    assert not deck.layers
    assert any("CRS" in message for message in notices)


def test_display_units_are_json_literals_not_accessor_expressions():
    deck, _ = build_map({"sources": frame([Point(116.4, 39.9)])}, {})
    layer = serialized(deck)["layers"][0]
    assert layer["lineWidthUnits"] == "pixels"
    assert layer["pointRadiusUnits"] == "pixels"
