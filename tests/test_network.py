import builtins
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point
from crazy_buffer import Network, RunReport, SpatialInputError, build_network, nearest_network_distance


def layer(ids, geoms):
    return gpd.GeoDataFrame({'id': ids}, geometry=geoms, crs='EPSG:32650')


def roads(lines, **kwargs):
    return build_network(layer([str(i) for i in range(len(lines))], [LineString(x) for x in lines]), edge_id='id', **kwargs)


def route(network, starts, ends, **kwargs):
    return nearest_network_distance(layer([str(i) for i in range(len(starts))], [Point(x) for x in starts]),
        layer([str(i) for i in range(len(ends))], [Point(x) for x in ends]), network,
        source_id='id', target_id='id', **kwargs)


def test_middle_road_access_and_immutable():
    net = roads([[(0, 0), (100, 0)]])
    before = net.edges.copy(deep=True)
    row = route(net, [(20, 3)], [(80, 4)]).iloc[0]
    assert [row.source_access_m, row.network_distance_m, row.target_access_m, row.total_distance_m] == [3, 60, 4, 67]
    pd.testing.assert_frame_equal(before, net.edges)
    assert isinstance(net, Network)


def test_bend_and_crossing_without_junction():
    net = roads([[(0, 0), (0, 10), (10, 10)]])
    assert route(net, [(0, 5)], [(5, 10)]).network_distance_m.iloc[0] == 10
    net = roads([[(-10, 0), (10, 0)], [(0, -10), (0, 10)]])
    assert route(net, [(-5, 0)], [(0, 5)]).status.iloc[0] == 'unreachable'


def test_directed_forward_reverse_and_coincident_reverse_geometry():
    net = roads([[(0, 0), (100, 0)]], directed=True)
    assert route(net, [(20, 0)], [(80, 0)]).network_distance_m.iloc[0] == 60
    assert route(net, [(80, 0)], [(20, 0)]).status.iloc[0] == 'unreachable'
    net = roads([[(0, 0), (100, 0)], [(100, 0), (0, 0)]], directed=True)
    assert route(net, [(80, 0)], [(20, 0)]).network_distance_m.iloc[0] == 60
    assert route(net, [(20, 0)], [(80, 0)]).network_distance_m.iloc[0] == 60


def test_parallel_edges_and_loop():
    net = roads([[(0, 0), (10, 0)], [(0, 0), (5, 5), (10, 0)],
                 [(10, 0), (20, 0), (20, 10), (10, 0)]])
    assert route(net, [(0, 0)], [(10, 0)]).network_distance_m.iloc[0] == 10
    assert route(net, [(20, 0)], [(20, 10)]).network_distance_m.iloc[0] == 10


def test_grade_separated_explicit_nodes():
    edges = layer(['a', 'b'], [LineString([(0, 0), (10, 0)]), LineString([(10, 0), (20, 0)])])
    edges['u'] = ['a', 'upper']; edges['v'] = ['lower', 'b']
    net = build_network(edges, edge_id='id', from_node='u', to_node='v')
    assert route(net, [(5, 0)], [(15, 0)]).status.iloc[0] == 'unreachable'
    edges.geometry = [LineString([(0, 0), (10, 0)]), LineString([(10, 0), (0, 0)])]
    net = build_network(edges, edge_id='id', from_node='u', to_node='v', directed=True)
    # Geometrically coincident but topologically separate decks cannot supply reverse travel.
    assert route(net, [(8, 0)], [(2, 0)]).status.iloc[0] == 'unreachable'


def test_strict_ties_and_edge_id_tie():
    net = roads([[(-10, 0), (10, 0)]])
    sources = layer(['s'], [Point(0, 0)])
    targets = layer(['B', 'A'], [Point(5, 0), Point(-5, 0)])
    row = nearest_network_distance(sources, targets, net, source_id='id', target_id='id').iloc[0]
    assert row.target_id == 'A' and row.tie_count == 2
    targets.geometry = [Point(5, 0), Point(-5.000001, 0)]
    assert nearest_network_distance(sources, targets, net, source_id='id', target_id='id').target_id.iloc[0] == 'B'
    net = roads([[(-10, -1), (10, -1)], [(-10, 1), (10, 1)]])
    assert route(net, [(0, 0)], [(5, -1)]).status.iloc[0] == 'ok'
    assert route(net, [(0, 0)], [(5, 1)]).status.iloc[0] == 'unreachable'


def test_thresholds_empty_and_report():
    report = RunReport(); net = roads([[(0, 0), (100, 0)]], report=report)
    assert route(net, [(20, 5)], [(80, 5)], max_snap_distance_m=5).status.iloc[0] == 'ok'
    assert route(net, [(20, 6)], [(80, 5)], max_snap_distance_m=5).status.iloc[0] == 'source_too_far'
    result = route(net, [(20, 0)], [(80, 6)], max_snap_distance_m=5, report=report)
    assert result.status.iloc[0] == 'no_reachable_target'
    assert pd.isna(result.target_id.iloc[0]) and pd.isna(result.network_distance_m.iloc[0])
    assert report.steps[-1]['counts']['excluded_targets'] == 1
    result = route(net, [], [(80, 0)])
    assert result.empty and len(result.columns) == 8
    with pytest.raises(SpatialInputError):
        route(net, [(0, 0)], [])


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf'), '2'])
def test_invalid_threshold(value):
    with pytest.raises(SpatialInputError):
        route(roads([[(0, 0), (10, 0)]]), [(0, 0)], [(10, 0)], max_snap_distance_m=value)


def test_invalid_network_inputs():
    for edges in [layer([], []), layer(['a'], [Point(0, 0)]),
                  layer(['a'], [LineString([(0, 0), (0, 0)])]),
                  layer(['a'], [LineString([(0, 0), (10, 10), (0, 10), (10, 0)])])]:
        with pytest.raises(SpatialInputError):
            build_network(edges, edge_id='id')
    edges = layer(['a', 'b'], [LineString([(0, 0), (10, 0)]), LineString([(20, 0), (30, 0)])])
    edges['u'] = ['same', 'same']; edges['v'] = ['x', 'y']
    with pytest.raises(SpatialInputError):
        build_network(edges, edge_id='id', from_node='u', to_node='v')
    with pytest.raises(SpatialInputError):
        build_network(edges, edge_id='id', from_node='u')
    for nodes in [[True, False], [None, 'a'], ['a', 1]]:
        edges['u'] = nodes
        with pytest.raises(SpatialInputError):
            build_network(edges, edge_id='id', from_node='u', to_node='v')


def test_optional_dependency_is_lazy(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'networkx':
            raise ImportError('not installed')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    net = roads([[(0, 0), (10, 0)]])
    with pytest.raises(ImportError, match='optional networkx'):
        route(net, [(0, 0)], [(10, 0)])


def test_nonfinite_derived_length_report():
    report = RunReport()
    edges = layer(['huge'], [LineString([(0, 0), (1e308, 0)])])
    with pytest.raises(SpatialInputError, match='finite positive length'):
        build_network(edges, edge_id='id', report=report)
    assert report.issues[-1]['code'] == 'invalid_edge'


def test_curved_reverse_multiple_attachments_and_partial_overlap():
    line = [(0, 0), (0, 10), (10, 10)]
    edges = layer(['a', 'b'], [LineString(line), LineString(line[::-1])])
    edges['u'] = ['start', 'end']; edges['v'] = ['end', 'start']
    net = build_network(edges, edge_id='id', from_node='u', to_node='v', directed=True)
    result = route(net, [(8, 10), (0, 0), (0, 5), (0, 5)], [(0, 2)])
    assert result.network_distance_m.tolist() == [16, 2, 3, 3]
    net = roads([[(0, 0), (100, 0)], [(80, 0), (20, 0)]], directed=True)
    assert route(net, [(70, 0)], [(30, 0)]).status.iloc[0] == 'unreachable'


def test_total_float_ties_and_empty_dtypes():
    net = roads([[(0, 0), (10, 0)]])
    result = route(net, [(0, 1e16)], [(0, 0), (1, 0)], max_snap_distance_m=1e16)
    assert result.tie_count.iloc[0] == 2
    sources = layer(pd.Series([], dtype='int32'), [])
    targets = layer(pd.Series([7], dtype='int64'), [Point(0, 0)])
    result = nearest_network_distance(sources, targets, net, source_id='id', target_id='id')
    assert result.source_id.dtype == sources.id.dtype
    assert result.target_id.dtype == targets.id.dtype


def test_linestring_geopackage_reader(tmp_path):
    from crazy_buffer import read_geopackage
    frame = layer(['001'], [LineString([(0, 0), (10, 0)])])
    path = tmp_path / 'roads.gpkg'
    frame.to_file(path, layer='roads', driver='GPKG', index=False)
    result = read_geopackage(path, layer='roads', id_column='id')
    assert result.id.tolist() == ['001']
    assert build_network(result, edge_id='id').edges.geometry.iloc[0].length == 10
