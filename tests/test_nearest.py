import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from crazy_buffer import RunReport, SpatialInputError, nearest_distance


def layer(ids, geometries, **kwargs):
    return gpd.GeoDataFrame({'id': ids}, geometry=geometries, crs=kwargs.pop('crs', 'EPSG:32650'), **kwargs)


def nearest(sources, targets, **kwargs):
    return nearest_distance(sources, targets, source_id='id', target_id='id', **kwargs)


def test_ties_are_stable_and_strict():
    sources = layer(['001'], [Point(0, 0)])
    targets = layer(['B', 'A'], [Point(3, 4), Point(-3, 4)])
    result = nearest(sources, targets)
    assert result.loc[0, 'target_id'] == 'A'
    assert result.loc[0, 'distance_m'] == 5.0
    assert result.loc[0, 'tie_count'] == 2
    pd.testing.assert_frame_equal(result, nearest(sources, targets.iloc[::-1]))
    close = layer(['A', 'B'], [Point(5.000000000001, 0), Point(5, 0)])
    result = nearest(sources, close)
    assert result.loc[0, 'target_id'] == 'B'
    assert result.loc[0, 'tie_count'] == 1


def test_integer_ids_and_duplicate_indices_preserved():
    sources = layer(pd.Series([7, 8], dtype='int32'), [Point(0, 0), Point(3, 4)])
    sources.index = [5, 5]
    targets = layer(pd.Series([2, 10], dtype='int64'), [Point(-3, 4), Point(3, 4)])
    targets.index = [9, 9]
    before_sources, before_targets = sources.copy(deep=True), targets.copy(deep=True)
    result = nearest(sources, targets)
    assert result.target_id.tolist() == [10, 10]
    assert result.source_id.tolist() == [7, 8]
    assert result.distance_m.tolist() == [5.0, 0.0]
    assert result.tie_count.tolist() == [2, 1]
    assert result.source_id.dtype == sources.id.dtype
    assert result.target_id.dtype == targets.id.dtype
    pd.testing.assert_frame_equal(sources, before_sources)
    pd.testing.assert_frame_equal(targets, before_targets)


def test_empty_sources_schema_and_report():
    sources = layer(pd.Series([], dtype='int32'), [])
    targets = layer(['A'], [Point(0, 0)])
    report = RunReport()
    result = nearest(sources, targets, report=report)
    assert result.columns.tolist() == ['source_id', 'target_id', 'distance_m', 'tie_count', 'status']
    assert result.empty
    assert result.source_id.dtype == sources.id.dtype
    assert result.target_id.dtype == targets.id.dtype
    assert report.steps[-1]['name'] == 'nearest_distance'


def test_empty_targets_error():
    report = RunReport()
    with pytest.raises(SpatialInputError) as caught:
        nearest(layer([], []), layer([], []), report=report)
    assert caught.value.code == 'EMPTY_TARGETS'
    assert report.issues


@pytest.mark.parametrize('bad_side', ['source', 'target'])
def test_non_point_rejected(bad_side):
    good = layer(['A'], [Point(0, 0)])
    bad = layer(['B'], [Polygon([(0, 0), (1, 0), (0, 1)])])
    with pytest.raises(SpatialInputError):
        nearest(bad if bad_side == 'source' else good, bad if bad_side == 'target' else good)


@pytest.mark.parametrize('crs', ['EPSG:32651', 'EPSG:4326', 'EPSG:3857'])
def test_crs_rejected(crs):
    with pytest.raises(SpatialInputError):
        nearest(layer(['A'], [Point(0, 0)]), layer(['B'], [Point(0, 0)], crs=crs))


@pytest.mark.parametrize('ids', [['A', 'A'], ['A', None], [1, 'A'], [True, False]])
def test_invalid_ids_rejected(ids):
    with pytest.raises(SpatialInputError):
        nearest(layer(['A'], [Point(0, 0)]), layer(ids, [Point(0, 0), Point(1, 0)]))
