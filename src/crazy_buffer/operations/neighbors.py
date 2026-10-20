"""Spatial neighbor matching with index candidates and exact distances."""

from copy import deepcopy
from numbers import Integral

import numpy as np
import pandas as pd
from shapely.geometry import box

from ..errors import SpatialInputError
from ..validate import _issue, _raise_issues, validate_layer
from .buffer import _validate_radius

_RESULT_COLUMNS = ["source_id", "target_id", "distance_m", "radius_m"]


def _record_error(report, exc):
    if report is not None:
        report.issues.extend(deepcopy(exc.issues))


def _validate_max_matches(max_matches):
    if isinstance(max_matches, (bool, np.bool_)) or not isinstance(max_matches, Integral) or max_matches <= 0:
        _raise_issues([_issue(
            "INVALID_MAX_MATCHES",
            "max_matches must be a positive integer.",
            max_matches=str(max_matches),
        )])
    return int(max_matches)


def _validate_pair(sources, targets, source_id, target_id):
    validate_layer(
        sources,
        id_column=source_id,
        geometry_types=("Point", "Polygon", "MultiPolygon"),
        require_metric=True,
    )
    # Report a mismatch before target metric validation when both CRS values
    # are declared; this makes a geographic-vs-projected pair actionable.
    if getattr(targets, "crs", None) is not None and sources.crs != targets.crs:
        _raise_issues([_issue(
            "CRS_MISMATCH",
            "Sources and targets must use the same CRS.",
            source_crs=sources.crs.to_string(),
            target_crs=targets.crs.to_string(),
        )])
    validate_layer(
        targets,
        id_column=target_id,
        geometry_types=("Point",),
        require_metric=True,
    )


def _empty_result(source_dtype, target_dtype):
    return pd.DataFrame({
        "source_id": pd.Series([], dtype=source_dtype),
        "target_id": pd.Series([], dtype=target_dtype),
        "distance_m": pd.Series([], dtype="float64"),
        "radius_m": pd.Series([], dtype="float64"),
    }, columns=_RESULT_COLUMNS)


def _batch_frame(rows, source_dtype, target_dtype):
    if not rows:
        return _empty_result(source_dtype, target_dtype)
    result = pd.DataFrame.from_records(rows, columns=_RESULT_COLUMNS)
    # Explicit casts preserve business ID dtypes, including integer IDs, even
    # when a batch happens to contain only a subset of the input values.
    result["source_id"] = pd.Series(result["source_id"].tolist(), dtype=source_dtype)
    result["target_id"] = pd.Series(result["target_id"].tolist(), dtype=target_dtype)
    result["distance_m"] = result["distance_m"].astype("float64")
    result["radius_m"] = result["radius_m"].astype("float64")
    return result


def iter_neighbor_batches(
    sources,
    targets,
    *,
    source_id,
    target_id,
    radius_m,
    batch_size=256,
    max_matches=None,
):
    """Yield exact source-target relationships in bounded source batches.

    The target spatial index only supplies bounding-box candidates. Every
    candidate is then filtered by ``geometry.distance <= radius_m`` against the
    original geometry, so curved buffer polygon approximation never controls
    membership. No all-pairs distance matrix is materialized.
    """
    radius = _validate_radius(radius_m)
    if isinstance(batch_size, (bool, np.bool_)) or not isinstance(batch_size, Integral) or batch_size <= 0:
        _raise_issues([_issue("INVALID_BATCH_SIZE", "batch_size must be a positive integer.", batch_size=str(batch_size))])
    _validate_pair(sources, targets, source_id, target_id)
    limit = None if max_matches is None else _validate_max_matches(max_matches)
    emitted = 0
    if len(targets) == 0:
        return

    target_index = targets.sindex
    source_values = sources[source_id].tolist()
    target_values = targets[target_id].tolist()
    target_geometries = targets.geometry.tolist()
    for start in range(0, len(sources), int(batch_size)):
        rows = []
        stop = min(start + int(batch_size), len(sources))
        for source_value, source_geometry in zip(source_values[start:stop], sources.geometry.iloc[start:stop]):
            # Query an expanded axis-aligned envelope through the spatial
            # index. A polygonal buffer is deliberately not used here: its
            # chord approximation can exclude a true distance==radius point.
            minx, miny, maxx, maxy = source_geometry.bounds
            candidate_positions = target_index.query(box(minx - radius, miny - radius, maxx + radius, maxy + radius))
            for target_position in sorted(candidate_positions.tolist()):
                target_geometry = target_geometries[target_position]
                distance = float(source_geometry.distance(target_geometry))
                if distance <= radius:
                    if limit is not None and emitted + len(rows) + 1 > limit:
                        _raise_issues([_issue(
                            "MATCH_LIMIT_EXCEEDED",
                            "The number of spatial relationships exceeds max_matches.",
                            max_matches=limit,
                            matches=emitted + len(rows) + 1,
                        )])
                    rows.append((source_value, target_values[target_position], distance, radius))
        emitted += len(rows)
        yield _batch_frame(rows, sources[source_id].dtype, targets[target_id].dtype)


def neighbors_within(
    sources,
    targets,
    *,
    source_id,
    target_id,
    radius_m,
    max_matches=1_000_000,
    report=None,
):
    """Return all target points within an exact planar radius of each source."""
    try:
        radius = _validate_radius(radius_m)
        limit = _validate_max_matches(max_matches)
        _validate_pair(sources, targets, source_id, target_id)
        batches = []
        total = 0
        for batch in iter_neighbor_batches(
            sources,
            targets,
            source_id=source_id,
            target_id=target_id,
            radius_m=radius,
            max_matches=limit,
        ):
            batch_count = len(batch)
            if total + batch_count > limit:
                _raise_issues([_issue(
                    "MATCH_LIMIT_EXCEEDED",
                    "The number of spatial relationships exceeds max_matches.",
                    max_matches=limit,
                    matches=total + batch_count,
                )])
            total += batch_count
            batches.append(batch)
        if batches:
            result = pd.concat(batches, ignore_index=True)
            # concat can widen extension dtypes; cast back to the source/target
            # business ID dtypes declared by the inputs.
            result["source_id"] = pd.Series(result["source_id"].tolist(), dtype=sources[source_id].dtype)
            result["target_id"] = pd.Series(result["target_id"].tolist(), dtype=targets[target_id].dtype)
        else:
            result = _empty_result(sources[source_id].dtype, targets[target_id].dtype)
    except SpatialInputError as exc:
        _record_error(report, exc)
        raise
    if report is not None:
        report.add_step(
            "neighbors_within",
            {
                "source_id": source_id,
                "target_id": target_id,
                "radius_m": radius,
                "max_matches": limit,
                "crs": sources.crs.to_string(),
            },
            {"sources": len(sources), "targets": len(targets), "matches": len(result)},
        )
    return result[_RESULT_COLUMNS]
