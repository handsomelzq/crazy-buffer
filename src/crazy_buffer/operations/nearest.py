"""Indexed planar nearest-point distances with deterministic exact ties."""

import pandas as pd

from ..errors import SpatialInputError
from ..validate import _issue, _raise_issues, validate_layer
from .neighbors import _record_error, _validate_pair

_COLUMNS = ['source_id', 'target_id', 'distance_m', 'tie_count', 'status']


def nearest_distance(sources, targets, *, source_id, target_id, report=None):
    """Find each point's nearest target in a shared metre-based projected CRS.

    All engine-exact distance ties are counted; the target with the smallest
    ``str(ID)`` is selected. CRS validation does not establish study-area fit.
    """
    try:
        # Pair validation supplies common ID/CRS checks; nearest sources have
        # the stricter Point-only requirement as well.
        _validate_pair(sources, targets, source_id, target_id)
        validate_layer(sources, id_column=source_id, geometry_types=('Point',), require_metric=True)
        if len(targets) == 0:
            _raise_issues([_issue('EMPTY_TARGETS', 'Nearest distance requires at least one target.')])
        rows = []
        target_values = targets[target_id].tolist()
        spatial_index = targets.sindex
        for identifier, geometry in zip(sources[source_id], sources.geometry):
            positions, distances = spatial_index.nearest(
                geometry, return_all=True, return_distance=True,
            )
            # nearest(return_all=True) returns every strictly equal minimum
            # under the geometry engine, without any user tolerance.
            minimum = float(distances.min())
            candidates = positions[1][distances == minimum].tolist()
            chosen = min(candidates, key=lambda position: str(target_values[position]))
            rows.append((identifier, target_values[chosen], minimum, len(candidates), 'ok'))
        result = pd.DataFrame.from_records(rows, columns=_COLUMNS)
        result['source_id'] = pd.Series(result['source_id'].tolist(), dtype=sources[source_id].dtype)
        result['target_id'] = pd.Series(result['target_id'].tolist(), dtype=targets[target_id].dtype)
        result['distance_m'] = result['distance_m'].astype('float64')
        result['tie_count'] = result['tie_count'].astype('int64')
        result['status'] = result['status'].astype('object')
    except SpatialInputError as exc:
        _record_error(report, exc)
        raise
    if report is not None:
        report.add_step('nearest_distance', {
            'source_id': source_id, 'target_id': target_id,
            'crs': sources.crs.to_string(), 'tie_break': 'lexicographic str(target_id)',
        }, {'sources': len(sources), 'targets': len(targets), 'results': len(result)})
    return result
