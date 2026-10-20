import json

import geopandas as gpd
import numpy as np
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point

from crazy_buffer import RunReport, SpatialInputError
from crazy_buffer.operations.buffer import make_buffers


def test_make_buffers_preserves_ids_crs_input_and_records_parameters():
    sources = gpd.GeoDataFrame(
        {"park_id": ["p1", "p2"]},
        geometry=[Point(500000, 4400000), Point(500010, 4400000)],
        crs="EPSG:32650",
    )
    original = sources.copy(deep=True)
    report = RunReport()

    result = make_buffers(sources, source_id="park_id", radius_m=10, report=report)

    assert list(result.columns) == ["park_id", "radius_m", "geometry"]
    assert result["park_id"].tolist() == ["p1", "p2"]
    assert result["radius_m"].tolist() == [10.0, 10.0]
    assert result.crs == sources.crs
    assert result.geometry.is_valid.all()
    assert result.geometry.area.iloc[0] == pytest.approx(3.141592653589793 * 100, rel=1e-3)
    assert_geodataframe_equal(sources, original)
    assert report.steps[-1]["name"] == "make_buffers"
    assert report.steps[-1]["parameters"]["radius_m"] == 10.0
    assert report.steps[-1]["parameters"]["quad_segs"] == 32


@pytest.mark.parametrize("radius", [0, -1, float("nan"), float("inf"), True])
def test_make_buffers_rejects_invalid_radius(metric_points, radius):
    with pytest.raises(SpatialInputError) as error:
        make_buffers(metric_points, source_id="id", radius_m=radius)
    assert error.value.code == "INVALID_RADIUS"


@pytest.mark.parametrize("radius", [np.float32(-1), np.float64("nan"), float("inf")])
def test_invalid_radius_issues_are_strict_json_safe(metric_points, radius):
    with pytest.raises(SpatialInputError) as error:
        make_buffers(metric_points, source_id="id", radius_m=radius)
    json.dumps(error.value.issues, allow_nan=False)


def test_overflowing_radius_has_structured_error(metric_points):
    with pytest.raises(SpatialInputError) as error:
        make_buffers(metric_points, source_id="id", radius_m=10**1000)
    assert error.value.code == "INVALID_RADIUS"


def test_huge_integer_radius_has_json_safe_structured_error(metric_points):
    radius = 10**10000
    with pytest.raises(SpatialInputError) as error:
        make_buffers(metric_points, source_id="id", radius_m=radius)
    assert error.value.code == "INVALID_RADIUS"
    json.dumps(error.value.issues, allow_nan=False)


@pytest.mark.parametrize("source_id", ["radius_m", "geometry"])
def test_buffer_rejects_reserved_output_id_names(source_id):
    sources = gpd.GeoDataFrame(
        {source_id: ["original-id"], "shape": [Point(500000, 4400000)]},
        geometry="shape", crs="EPSG:32650",
    )
    with pytest.raises(SpatialInputError) as error:
        make_buffers(sources, source_id=source_id, radius_m=5)
    assert error.value.code == "RESERVED_SOURCE_ID"
    assert sources[source_id].tolist() == ["original-id"]


@pytest.mark.parametrize("quad_segs", [0, -1, 1.5, True])
def test_make_buffers_rejects_invalid_quad_segs(metric_points, quad_segs):
    with pytest.raises(SpatialInputError) as error:
        make_buffers(metric_points, source_id="id", radius_m=10, quad_segs=quad_segs)
    assert error.value.code == "INVALID_QUAD_SEGS"
