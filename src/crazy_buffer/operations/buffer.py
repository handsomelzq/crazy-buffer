"""Buffer construction for validated, metric GeoDataFrames."""

from copy import deepcopy
from numbers import Integral

import geopandas as gpd
import numpy as np

from ..errors import SpatialInputError
from ..validate import _issue, _raise_issues, validate_layer


def _record_error(report, exc):
    if report is not None:
        report.issues.extend(deepcopy(exc.issues))


def _validate_radius(radius_m):
    if isinstance(radius_m, (bool, np.bool_)) or not isinstance(radius_m, (Integral, float, np.integer, np.floating)):
        _raise_issues([_issue("INVALID_RADIUS", "radius_m must be a finite number greater than zero.", radius_m=str(radius_m))])
    try:
        radius = float(radius_m)
    except OverflowError:
        _raise_issues([_issue("INVALID_RADIUS", "radius_m must be a finite number greater than zero.", radius_m="outside float range")])
    if not np.isfinite(radius) or radius <= 0:
        _raise_issues([_issue("INVALID_RADIUS", "radius_m must be a finite number greater than zero.", radius_m=str(radius_m))])
    return radius


def _validate_quad_segs(quad_segs):
    if isinstance(quad_segs, (bool, np.bool_)) or not isinstance(quad_segs, Integral) or quad_segs <= 0:
        _raise_issues([_issue("INVALID_QUAD_SEGS", "quad_segs must be a positive integer.", quad_segs=str(quad_segs))])
    return int(quad_segs)


def make_buffers(sources, *, source_id, radius_m, quad_segs=32, report=None):
    """Return one polygon buffer for each source geometry.

    Inputs are validated and copied; the input GeoDataFrame and its active
    geometry are never modified. Distances are interpreted in CRS units, which
    are required to be metres by the input contract.

    ``source_id`` must not be ``radius_m`` or ``geometry``, which are reserved
    output columns. Conflicts raise ``RESERVED_SOURCE_ID`` without renaming IDs.
    """
    try:
        if source_id in ("radius_m", "geometry"):
            _raise_issues([_issue("RESERVED_SOURCE_ID", "source_id conflicts with a reserved output column.", source_id=source_id)])
        radius = _validate_radius(radius_m)
        segments = _validate_quad_segs(quad_segs)
        validate_layer(
            sources,
            id_column=source_id,
            geometry_types=("Point", "Polygon", "MultiPolygon"),
            require_metric=True,
        )
        buffered = sources.geometry.buffer(radius, quad_segs=segments)
        result = gpd.GeoDataFrame(
            {
                source_id: sources[source_id].copy(deep=True),
                "radius_m": np.full(len(sources), radius, dtype="float64"),
                "geometry": buffered,
            },
            index=sources.index.copy(),
            crs=sources.crs,
        )
    except SpatialInputError as exc:
        _record_error(report, exc)
        raise
    if report is not None:
        report.add_step(
            "make_buffers",
            {
                "source_id": source_id,
                "radius_m": radius,
                "quad_segs": segments,
                "crs": sources.crs.to_string(),
            },
            {"input": len(sources), "output": len(result)},
        )
    return result
