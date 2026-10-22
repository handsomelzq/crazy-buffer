import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from shapely.geometry import Point, box

from crazy_buffer import (
    RunReport, SpatialInputError, facility_mix, land_use_mix,
)


def test_facility_counts_density_entropy_and_boundary():
    crs = "EPSG:32650"
    sources = gpd.GeoDataFrame({"id": ["S1", "S2"]}, geometry=[Point(0, 0), Point(100, 0)], crs=crs)
    targets = gpd.GeoDataFrame(
        {"id": ["a", "b", "c", "d"], "type": ["food", "food", "shop", "shop"]},
        geometry=[Point(3, 4), Point(6, 8), Point(10, 0), Point(120, 0)],
        crs=crs,
    )
    before_sources, before_targets = sources.copy(deep=True), targets.copy(deep=True)
    report = RunReport()

    result = facility_mix(
        sources, targets, source_id="id", target_id="id",
        category_column="type", radius_m=10, report=report,
    ).set_index("source_id")

    s1, s2 = result.loc["S1"], result.loc["S2"]
    assert (s1.n_targets, s1.count_food, s1.count_shop, s1.n_categories_present) == (3, 2, 1, 2)
    buffer_area = sources.geometry.iloc[0].buffer(10, quad_segs=32).area
    assert s1.total_density_per_km2 == pytest.approx(3 / buffer_area * 1_000_000)
    assert s1.entropy == pytest.approx(
        -(2 / 3 * math.log(2 / 3) + 1 / 3 * math.log(1 / 3)) / math.log(2)
    )
    assert s2.status == "no_matches"
    assert (s2.n_targets, s2.count_food, s2.count_shop) == (0, 0, 0)
    assert report.steps[-1]["parameters"]["density_denominator"] == "full_buffer_area"
    assert_frame_equal(sources, before_sources)
    assert_frame_equal(targets, before_targets)


def test_facility_empty_inputs_keep_schema_and_explicit_categories():
    sources = gpd.GeoDataFrame({"id": pd.Series([], dtype="string")}, geometry=[], crs="EPSG:32650")
    targets = gpd.GeoDataFrame(
        {"id": pd.Series([], dtype="string"), "type": pd.Series([], dtype="string")},
        geometry=[], crs=sources.crs,
    )
    result = facility_mix(
        sources, targets, source_id="id", target_id="id",
        category_column="type", radius_m=10, categories=["food", "shop"],
    )
    assert result.empty
    assert {"count_food", "density_per_km2_shop"} <= set(result.columns)


@pytest.mark.parametrize("value", [None, "", True, 1.5])
def test_facility_rejects_invalid_categories(value):
    sources = gpd.GeoDataFrame({"id": ["S1"]}, geometry=[Point(0, 0)], crs="EPSG:32650")
    targets = gpd.GeoDataFrame(
        {"id": ["a"], "type": pd.Series([value], dtype="object")},
        geometry=[Point(0, 0)], crs=sources.crs,
    )
    with pytest.raises(SpatialInputError):
        facility_mix(
            sources, targets, source_id="id", target_id="id",
            category_column="type", radius_m=10,
        )


def test_land_use_area_share_coverage_and_entropy():
    crs = "EPSG:32650"
    sources = gpd.GeoDataFrame({"community": ["A"]}, geometry=[box(0, 0, 10, 10)], crs=crs)
    land_use = gpd.GeoDataFrame(
        {"parcel": ["r", "g"], "use": ["居住", "绿地"]},
        geometry=[box(0, 0, 6, 10), box(6, 0, 10, 5)],
        crs=crs,
    )
    report = RunReport()
    result = land_use_mix(
        sources,
        land_use,
        source_id="community",
        land_use_id="parcel",
        category_column="use",
        report=report,
    ).iloc[0]
    assert result.region_area_m2 == 100
    assert result.covered_area_m2 == 80
    assert result.coverage == pytest.approx(0.8)
    assert result["area_m2_居住"] == 60
    assert result["share_居住"] == pytest.approx(0.6)
    assert result["share_绿地"] == pytest.approx(0.2)
    assert result.entropy == pytest.approx(
        -(0.75 * math.log(0.75) + 0.25 * math.log(0.25)) / math.log(2)
    )
    assert result.status == "ok"
    assert report.steps[-1]["parameters"]["share_denominator"] == "analysis_region_area"


def test_land_use_buffer_and_overlap_report():
    crs = "EPSG:32650"
    sources = gpd.GeoDataFrame({"id": ["S"]}, geometry=[Point(0, 0)], crs=crs)
    land_use = gpd.GeoDataFrame(
        {"pid": ["a", "b"], "use": ["residential", "park"]},
        geometry=[box(-5, -5, 5, 5), box(0, 0, 5, 5)],
        crs=crs,
    )
    report = RunReport()
    result = land_use_mix(
        sources, land_use, source_id="id", land_use_id="pid",
        category_column="use", radius_m=10, report=report,
    ).iloc[0]
    assert result.region_area_m2 == pytest.approx(
        sources.geometry.iloc[0].buffer(10, quad_segs=32).area
    )
    assert result["area_m2_residential"] == 100
    assert result["area_m2_park"] == 25
    assert result.overlap_area_m2 == 25
    assert any(item["code"] == "OVERLAPPING_LAND_USE" for item in report.issues)


def test_land_use_no_coverage_and_polygon_required_without_buffer():
    sources = gpd.GeoDataFrame({"id": ["P"]}, geometry=[Point(0, 0)], crs="EPSG:32650")
    land_use = gpd.GeoDataFrame(
        {"pid": ["a"], "use": ["park"]}, geometry=[box(20, 20, 21, 21)], crs=sources.crs,
    )
    with pytest.raises(SpatialInputError, match="Geometry type"):
        land_use_mix(
            sources, land_use, source_id="id", land_use_id="pid",
            category_column="use",
        )
    polygon = gpd.GeoDataFrame({"id": ["P"]}, geometry=[box(0, 0, 1, 1)], crs=sources.crs)
    result = land_use_mix(
        polygon, land_use, source_id="id", land_use_id="pid",
        category_column="use",
    ).iloc[0]
    assert result.coverage == 0
    assert np.isnan(result.entropy)
    assert result.status == "no_land_use"
