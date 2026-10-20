import json

import geopandas as gpd
from geopandas.testing import assert_geodataframe_equal
import pytest
from shapely.geometry import Point, Polygon


def prepare(frame, **kwargs):
    from crazy_buffer import prepare_layer

    return prepare_layer(
        frame, id_column="id", analysis_crs="EPSG:32650",
        geometry_types=("Point",), **kwargs,
    )


@pytest.mark.parametrize("case,code", [
    ("no_crs", "missing_crs"),
    ("duplicate_id", "duplicate_id"),
    ("mixed_id", "invalid_id_type"),
    ("bool_id", "invalid_id_type"),
    ("empty_id", "missing_id"),
    ("null_id", "missing_id"),
    ("empty_geometry", "empty_geometry"),
    ("null_geometry", "empty_geometry"),
    ("invalid_geometry", "invalid_geometry"),
    ("z_geometry", "unsupported_dimension"),
    ("infinity", "nonfinite_coordinates"),
    ("wrong_type", "unsupported_geometry"),
])
def test_rejects_invalid_input_with_locatable_issue(metric_points, case, code):
    from crazy_buffer import SpatialInputError

    frame = metric_points.copy()
    if case == "no_crs":
        frame = frame.set_crs(None, allow_override=True)
    elif case == "duplicate_id":
        frame["id"] = ["a", "a"]
    elif case == "mixed_id":
        frame["id"] = ["a", 2]
    elif case == "bool_id":
        frame["id"] = [True, False]
    elif case == "empty_id":
        frame.loc[0, "id"] = " "
    elif case == "null_id":
        frame.loc[0, "id"] = None
    else:
        values = {
            "empty_geometry": Point(), "null_geometry": None,
            "invalid_geometry": Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)]),
            "z_geometry": Point(1, 2, 3),
            "infinity": Point(float("inf"), 2),
            "wrong_type": Polygon([(0, 0), (0, 2), (2, 0)]),
        }
        frame.loc[0, "geometry"] = values[case]
    with pytest.raises(SpatialInputError) as error:
        prepare(frame)
    assert error.value.code == code
    assert error.value.issues
    assert all("reason" in item for item in error.value.issues)
    json.dumps(error.value.issues, allow_nan=False)


@pytest.mark.parametrize("crs", ["EPSG:2263", "EPSG:4326", "EPSG:3857", "EPSG:900913", "ESRI:102113"])
def test_rejects_analysis_crs_without_suitable_meter_axes(metric_points, crs):
    from crazy_buffer import prepare_layer, SpatialInputError

    with pytest.raises(SpatialInputError) as error:
        prepare_layer(metric_points, id_column="id", analysis_crs=crs, geometry_types=("Point",))
    assert error.value.code == "invalid_analysis_crs"


def test_duplicate_dataframe_index_is_not_duplicate_business_id(metric_points):
    metric_points.index = [8, 8]
    original = metric_points.copy(deep=True)
    result = prepare(metric_points)
    assert result["id"].tolist() == ["a", "b"]
    assert result.index.tolist() == [8, 8]
    assert result is not metric_points
    assert_geodataframe_equal(metric_points, original)


def test_explicit_projection_preserves_original():
    frame = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(116.4, 39.9)], crs=4326)
    original = frame.copy(deep=True)
    result = prepare(frame)
    assert result.crs.to_epsg() == 32650
    assert result.geometry.x.iloc[0] == pytest.approx(448709.38, abs=1)
    assert result.geometry.y.iloc[0] == pytest.approx(4416830.56, abs=1)
    assert result["id"].tolist() == [1]
    assert_geodataframe_equal(frame, original)


def test_projection_nonfinite_result_rejected():
    from crazy_buffer import SpatialInputError

    frame = gpd.GeoDataFrame({"id": ["pole"]}, geometry=[Point(116, 100)], crs=4326)
    with pytest.raises(SpatialInputError) as error:
        prepare(frame)
    assert error.value.code == "nonfinite_coordinates"


def test_drop_requires_report(metric_points):
    from crazy_buffer import SpatialInputError

    with pytest.raises(SpatialInputError) as error:
        prepare(metric_points, on_invalid="drop")
    assert error.value.code == "report_required"


def test_drop_records_excluded_ids_without_mutating_input(metric_points):
    from crazy_buffer import RunReport

    metric_points.loc[1, "geometry"] = Point()
    original = metric_points.copy(deep=True)
    report = RunReport()
    result = prepare(metric_points, on_invalid="drop", report=report)
    assert result["id"].tolist() == ["a"]
    assert report.issues[0]["id"] == "b"
    assert report.issues[0]["action"] == "excluded"
    assert report.steps[-1]["counts"] == {"input": 2, "output": 1, "excluded": 1}
    json.dumps({"steps": report.steps, "issues": report.issues, "metadata": report.metadata}, allow_nan=False)
    assert_geodataframe_equal(metric_points, original)


@pytest.mark.parametrize("coordinate_system", ["GCJ-02", "BD-09"])
def test_rejects_offset_coordinate_system(metric_points, coordinate_system):
    from crazy_buffer import SpatialInputError

    with pytest.raises(SpatialInputError) as error:
        prepare(metric_points, coordinate_system=coordinate_system)
    assert error.value.code == "unsupported_coordinate_system"


def test_internal_validation_can_require_metric_crs(metric_points):
    from crazy_buffer.validate import validate_layer
    from crazy_buffer import SpatialInputError

    validate_layer(metric_points, id_column="id", geometry_types=("Point",), require_metric=True)
    with pytest.raises(SpatialInputError) as error:
        validate_layer(metric_points.to_crs(4326), id_column="id", geometry_types=("Point",), require_metric=True)
    assert error.value.code == "invalid_analysis_crs"


def test_m_dimension_is_rejected():
    from crazy_buffer import SpatialInputError
    from shapely import from_wkt

    frame = gpd.GeoDataFrame({"id": ["measured"]}, geometry=[from_wkt("POINT M (1 2 3)")], crs=32650)
    with pytest.raises(SpatialInputError) as error:
        prepare(frame)
    assert error.value.code == "unsupported_dimension"


def test_non_scalar_id_is_structured_error(metric_points):
    from crazy_buffer import SpatialInputError

    metric_points.at[0, "id"] = [1, 2]
    with pytest.raises(SpatialInputError) as error:
        prepare(metric_points)
    assert error.value.code == "invalid_id_type"
    json.dumps(error.value.issues, allow_nan=False)


def test_drop_records_projection_failure_and_preserves_valid_row():
    from crazy_buffer import RunReport

    frame = gpd.GeoDataFrame({"id": ["valid", "bad_lat"]}, geometry=[Point(116.4, 39.9), Point(116.4, 100)], crs=4326)
    report = RunReport()
    result = prepare(frame, on_invalid="drop", report=report)
    assert result["id"].tolist() == ["valid"]
    assert report.issues[0]["id"] == "bad_lat"
    assert report.issues[0]["code"] == "nonfinite_coordinates"


def test_error_report_records_field_issue(metric_points):
    from crazy_buffer import RunReport, SpatialInputError

    report = RunReport()
    metric_points["id"] = ["a", "a"]
    with pytest.raises(SpatialInputError):
        prepare(metric_points, report=report)
    assert {item["id"] for item in report.issues} == {"a"}
    assert report.steps == []
