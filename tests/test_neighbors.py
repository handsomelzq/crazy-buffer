import geopandas as gpd
import math
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from crazy_buffer import SpatialInputError
from crazy_buffer.operations.neighbors import iter_neighbor_batches, neighbors_within

CRS = "EPSG:32650"
OFFSET = (500000, 4400000)


def points(ids, coords):
    return gpd.GeoDataFrame(
        {"id": ids},
        geometry=[Point(OFFSET[0] + x, OFFSET[1] + y) for x, y in coords],
        crs=CRS,
    )


def test_neighbors_uses_exact_distance_and_preserves_ids():
    sources = points(["s"], [(0, 0)])
    targets = points(["a", "b", "c", "d"], [(3, 4), (5, 0), (5.001, 0), (0, 0)])

    links = neighbors_within(sources, targets, source_id="id", target_id="id", radius_m=5)

    assert set(links["target_id"]) == {"a", "b", "d"}
    assert sorted(links["distance_m"].tolist()) == [0.0, 5.0, 5.0]
    assert links["radius_m"].tolist() == [5.0, 5.0, 5.0]


def test_neighbors_handles_polygon_holes_and_multipolygon():
    shell = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    hole = Polygon([(4, 4), (6, 4), (6, 6), (4, 6)])
    donut = Polygon(shell.exterior.coords, [hole.exterior.coords])
    multi = MultiPolygon([Polygon([(20, 0), (22, 0), (22, 2), (20, 2)]), Polygon([(30, 0), (32, 0), (32, 2), (30, 2)])])
    sources = gpd.GeoDataFrame({"sid": ["donut", "multi"]}, geometry=[donut, multi], crs=CRS)
    targets = gpd.GeoDataFrame(
        {"tid": ["hole", "edge", "inside_multi", "inside_second"]},
        geometry=[Point(5, 5), Point(5, 3), Point(21, 1), Point(31, 1)], crs=CRS,
    )

    within_one = neighbors_within(sources, targets, source_id="sid", target_id="tid", radius_m=1)
    assert set(within_one["target_id"]) == {"hole", "edge", "inside_multi", "inside_second"}
    assert within_one.loc[within_one.target_id == "hole", "distance_m"].iloc[0] == pytest.approx(1.0)
    within_half = neighbors_within(sources.iloc[[0]], targets.iloc[[0]], source_id="sid", target_id="tid", radius_m=0.5)
    assert within_half.empty
    inside = gpd.GeoDataFrame({"tid": ["inside"]}, geometry=[Point(5, 3.5)], crs=CRS)
    inside_result = neighbors_within(sources.iloc[[0]], inside, source_id="sid", target_id="tid", radius_m=0.5)
    assert inside_result.loc[0, "distance_m"] == pytest.approx(0.0)


def test_neighbors_keeps_empty_schema_and_id_dtypes():
    sources = points([1], [(0, 0)])
    targets = points([10, 11], [(100, 100), (200, 200)])
    targets.index = [7, 7]

    links = neighbors_within(sources, targets, source_id="id", target_id="id", radius_m=5)

    assert links.empty
    assert list(links.columns) == ["source_id", "target_id", "distance_m", "radius_m"]
    assert links["source_id"].dtype == sources["id"].dtype
    assert links["target_id"].dtype == targets["id"].dtype


def test_neighbors_allows_same_target_for_multiple_sources_and_same_location_ids():
    sources = points(["s1", "s2"], [(0, 0), (0, 0)])
    targets = points(["t1", "t2"], [(0, 0), (0, 0)])
    links = neighbors_within(sources, targets, source_id="id", target_id="id", radius_m=0.1)
    assert len(links) == 4
    assert links.groupby("source_id").size().to_dict() == {"s1": 2, "s2": 2}


def test_neighbors_returns_empty_for_empty_targets_and_rejects_mismatched_crs(metric_points):
    empty = metric_points.iloc[0:0].copy()
    links = neighbors_within(metric_points, empty, source_id="id", target_id="id", radius_m=5)
    assert links.empty
    assert list(links.columns) == ["source_id", "target_id", "distance_m", "radius_m"]
    assert links["source_id"].dtype == metric_points["id"].dtype
    assert links["target_id"].dtype == empty["id"].dtype

    wrong = metric_points.to_crs(4326)
    with pytest.raises(SpatialInputError) as error:
        neighbors_within(metric_points, wrong, source_id="id", target_id="id", radius_m=5)
    assert error.value.code == "CRS_MISMATCH"


def test_neighbors_enforces_match_limit_without_returning_truncated_result():
    sources = points(["s1", "s2"], [(0, 0), (0, 0)])
    targets = points(["t1", "t2"], [(0, 0), (0, 0)])
    with pytest.raises(SpatialInputError) as error:
        neighbors_within(sources, targets, source_id="id", target_id="id", radius_m=1, max_matches=2)
    assert error.value.code == "MATCH_LIMIT_EXCEEDED"
    assert error.value.issues[0]["matches"] == 3


def test_neighbors_rejects_invalid_target_geometry():
    sources = points(["s"], [(0, 0)])
    targets = gpd.GeoDataFrame({"id": ["t"]}, geometry=[Polygon([(0, 0), (1, 0), (0, 1)])], crs=CRS)
    with pytest.raises(SpatialInputError) as error:
        neighbors_within(sources, targets, source_id="id", target_id="id", radius_m=1)
    assert error.value.code == "unsupported_geometry"


def test_iterator_enforces_limit_across_batches():
    sources = points(["s1", "s2"], [(0, 0), (0, 0)])
    targets = points(["t1", "t2"], [(0, 0), (0, 0)])
    batches = iter_neighbor_batches(
        sources, targets, source_id="id", target_id="id", radius_m=1,
        batch_size=1, max_matches=2,
    )
    assert len(next(batches)) == 2
    with pytest.raises(SpatialInputError) as error:
        next(batches)
    assert error.value.code == "MATCH_LIMIT_EXCEEDED"
    assert error.value.issues[0]["matches"] == 3


def test_neighbors_includes_true_boundary_point_outside_discrete_buffer_polygon():
    sources = points(["s"], [(0, 0)])
    angle = math.radians(5.625)
    targets = points(["edge"], [(5 * math.cos(angle), 5 * math.sin(angle))])
    links = neighbors_within(sources, targets, source_id="id", target_id="id", radius_m=5)
    assert links["target_id"].tolist() == ["edge"]
    assert links.loc[0, "distance_m"] == pytest.approx(5.0)
