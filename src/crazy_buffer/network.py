"""Endpoint-only road topology and nearest-target network distances."""
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd

from .errors import SpatialInputError
from .validate import _issue, _raise_issues, validate_layer

_COLUMNS = ['source_id', 'target_id', 'source_access_m', 'network_distance_m',
            'target_access_m', 'total_distance_m', 'tie_count', 'status']


def _nx():
    try:
        import networkx
    except ImportError as exc:
        raise ImportError('Network routing requires the optional networkx dependency.') from exc
    return networkx


@dataclass(frozen=True)
class Network:
    """Validated road snapshot. Treat its edges and endpoint tuples as read-only."""
    edges: object
    edge_id: str
    directed: bool
    endpoints: tuple


def _record(report, exc):
    if report is not None:
        report.issues.extend(exc.issues)


def build_network(edges, *, edge_id, from_node=None, to_node=None, directed=False, report=None):
    """Snapshot simple positive-length metre LineStrings; crossings stay separate."""
    try:
        validate_layer(edges, id_column=edge_id, geometry_types=('LineString',), require_metric=True)
        _raise_issues([_issue('empty_network', 'Road network must contain edges.')] if not len(edges) else [])
        _raise_issues([_issue('invalid_direction', 'directed must be a bool.')] if not isinstance(directed, bool) else [])
        if (from_node is None) != (to_node is None):
            _raise_issues([_issue('invalid_nodes', 'Specify both endpoint node columns.')])
        endpoints = []; locations = {}; kinds = set()
        for pos, line in enumerate(edges.geometry):
            if not np.isfinite(line.length) or line.length <= 0 or not line.is_simple:
                _raise_issues([_issue('invalid_edge', 'Road must have finite positive length and be simple.', row=pos)])
            pair = []
            for column, coordinate in zip((from_node, to_node), (tuple(line.coords[0]), tuple(line.coords[-1]))):
                if column is None:
                    node = coordinate
                else:
                    if column not in edges.columns:
                        _raise_issues([_issue('missing_field', 'Node column is missing.', field=column)])
                    node = edges[column].iloc[pos]
                    if isinstance(node, str) and node.strip():
                        kinds.add('str')
                    elif isinstance(node, Integral) and not isinstance(node, (bool, np.bool_)):
                        kinds.add('int')
                    else:
                        _raise_issues([_issue('invalid_node_id', 'Nodes must be nonempty strings or integers.', row=pos)])
                    if node in locations and locations[node] != coordinate:
                        _raise_issues([_issue('node_coordinate_mismatch', 'A node must have exactly one endpoint position.', row=pos)])
                    locations[node] = coordinate
                pair.append(node)
            endpoints.append(tuple(pair))
        if len(kinds) > 1:
            _raise_issues([_issue('invalid_node_id', 'Mixed node ID types are not allowed.')])
        result = Network(edges.copy(deep=True).reset_index(drop=True), edge_id, directed, tuple(endpoints))
    except SpatialInputError as exc:
        _record(report, exc); raise
    if report is not None:
        report.add_step('build_network', {'edge_id': edge_id, 'from_node': from_node, 'to_node': to_node,
            'directed': directed, 'connectivity': 'exact endpoints only; explicit node IDs preserve levels'}, {'edges': len(edges)})
    return result


def nearest_network_distance(sources, targets, network, *, source_id, target_id,
                             max_snap_distance_m=100.0, report=None):
    """Nearest target using access + routed road length + target access.

    Reverse Dijkstra runs stream one target at a time, retaining only source minima.
    Coincident opposite-direction edges share attachment only when their endpoint
    node identities agree spatially; explicit grade-separated nodes stay separate.
    """
    try:
        if not isinstance(network, Network):
            _raise_issues([_issue('invalid_network', 'Expected a Network.')])
        for frame, field in ((sources, source_id), (targets, target_id)):
            validate_layer(frame, id_column=field, geometry_types=('Point',), require_metric=True)
            if frame.crs != network.edges.crs:
                _raise_issues([_issue('crs_mismatch', 'Points and network must share a CRS.')])
        if not len(targets):
            _raise_issues([_issue('EMPTY_TARGETS', 'At least one target is required.')])
        if isinstance(max_snap_distance_m, (bool, np.bool_)) or not isinstance(max_snap_distance_m, Real) or not np.isfinite(max_snap_distance_m) or max_snap_distance_m < 0:
            _raise_issues([_issue('invalid_snap_distance', 'Maximum snap distance must be finite and nonnegative.')])
        nx = _nx(); edges = network.edges
        graph = nx.DiGraph(); splits = [dict() for _ in range(len(edges))]
        for i, (u, v) in enumerate(network.endpoints):
            splits[i][0.0] = ('endpoint', u)
            splits[i][float(edges.geometry.iloc[i].length)] = ('endpoint', v)
        def snap(point):
            positions, distances = edges.sindex.nearest(point, return_all=True, return_distance=True)
            if not len(distances) or not np.isfinite(distances).all():
                _raise_issues([_issue('nonfinite_distance', 'Road access exceeds finite numeric range.')])
            minimum = float(distances.min())
            candidates = positions[1][distances == minimum].tolist()
            chosen = min(candidates, key=lambda i: str(edges[network.edge_id].iloc[i]))
            line = edges.geometry.iloc[chosen]; offset = float(line.project(point))
            node = splits[chosen].get(offset, ('attachment', chosen, offset))
            # Only geometrically identical roads in the same endpoint topology
            # offer alternate legal directions at this nearest-road attachment.
            for i in candidates:
                other = edges.geometry.iloc[i]
                if not line.equals(other):
                    continue
                same = tuple(line.coords[0]) == tuple(other.coords[0])
                expected = network.endpoints[chosen] if same else network.endpoints[chosen][::-1]
                if network.endpoints[i] != expected:
                    continue
                location = float(other.project(line.interpolate(offset)))
                existing = splits[i].get(location)
                if existing is not None:
                    node = existing
            for i in candidates:
                other = edges.geometry.iloc[i]
                same = tuple(line.coords[0]) == tuple(other.coords[0])
                expected = network.endpoints[chosen] if same else network.endpoints[chosen][::-1]
                if line.equals(other) and network.endpoints[i] == expected:
                    splits[i][float(other.project(line.interpolate(offset)))] = node
            splits[chosen][offset] = node
            return node, minimum
        target_snaps = [snap(p) for p in targets.geometry]
        source_snaps = [snap(p) for p in sources.geometry]
        def arc(u, v, length):
            if not graph.has_edge(u, v) or length < graph[u][v]['weight']:
                graph.add_edge(u, v, weight=length)
        for points in splits:
            ordered = sorted(points.items())
            graph.add_nodes_from(points.values())
            for (a, u), (b, v) in zip(ordered, ordered[1:]):
                arc(u, v, b-a)
                if not network.directed:
                    arc(v, u, b-a)
        accepted = [i for i, (_, access) in enumerate(target_snaps) if access <= max_snap_distance_m]
        # Stream a target at a time: bounded O(V+S) state, no S-by-T matrix.
        # Comparing computed totals (rather than only route+target minima) also
        # counts exact floating-point ties created by adding source access.
        best = [None] * len(sources)
        reverse = graph.reverse(copy=False)
        for target in accepted if len(sources) else []:
            target_node, target_access = target_snaps[target]
            distances = nx.single_source_dijkstra_path_length(reverse, target_node, weight='weight')
            for source, (node, access) in enumerate(source_snaps):
                if access > max_snap_distance_m or node not in distances:
                    continue
                distance = distances[node]
                total = access + distance + target_access
                if not np.isfinite(total):
                    _raise_issues([_issue('nonfinite_distance', 'Computed distance exceeds finite numeric range.')])
                previous = best[source]
                if previous is None or total < previous[0]:
                    best[source] = (total, target, distance, 1)
                elif total == previous[0]:
                    chosen = target if str(targets[target_id].iloc[target]) < str(targets[target_id].iloc[previous[1]]) else previous[1]
                    best[source] = (total, chosen, distance if chosen == target else previous[2], previous[3] + 1)
        rows = []
        for index, (identifier, (_, access)) in enumerate(zip(sources[source_id], source_snaps)):
            status = ('source_too_far' if access > max_snap_distance_m else
                      'no_reachable_target' if not accepted else 'unreachable' if best[index] is None else 'ok')
            if status == 'ok':
                total, chosen, distance, count = best[index]
                rows.append((identifier, targets[target_id].iloc[chosen], access, distance,
                             target_snaps[chosen][1], total, count, status))
            else:
                rows.append((identifier, None, access, np.nan, np.nan, np.nan, 0, status))
        # Construct identifiers directly from raw records: pandas otherwise
        # infers float for integer IDs mixed with None, losing values > 2**53.
        raw_target_ids = [row[1] for row in rows]
        result = pd.DataFrame.from_records(rows, columns=_COLUMNS)
        result['target_id'] = pd.Series(raw_target_ids, dtype=object)
        result['source_id'] = pd.Series(result.source_id.tolist(), dtype=sources[source_id].dtype)
        target_dtype = targets[target_id].dtype if result.empty or result.target_id.notna().all() else object
        result['target_id'] = pd.Series(result.target_id.tolist(), dtype=target_dtype)
        for column in _COLUMNS[2:6]:
            result[column] = result[column].astype(float)
        result['tie_count'] = result.tie_count.astype('int64')
    except SpatialInputError as exc:
        _record(report, exc); raise
    if report is not None:
        report.add_step('nearest_network_distance', {'max_snap_distance_m': float(max_snap_distance_m),
            'directed': network.directed, 'connectivity': 'exact endpoints; crossings disconnected',
            'tie_break': 'lexicographic str(target_id)', 'snap_tie_break': 'lexicographic str(edge_id)'},
            {'sources': len(sources), 'targets': len(targets), 'excluded_targets': len(targets)-len(accepted), 'results': len(result)})
    return result
