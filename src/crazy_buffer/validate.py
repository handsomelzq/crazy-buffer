"""Shared validation. DataFrame indices are never treated as business IDs."""

from numbers import Integral

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely import get_coordinates
from shapely.validation import explain_validity

from .errors import SpatialInputError


def _json_scalar(value):
    if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def _issue(code, reason, **details):
    return {"code": code, "reason": reason, **details}


def _raise_issues(issues):
    if issues:
        raise SpatialInputError(issues[0]["code"], issues[0]["reason"], issues)


def _validate_coordinate_system(coordinate_system):
    if coordinate_system != "declared_crs":
        _raise_issues([_issue(
            "unsupported_coordinate_system",
            "Use coordinates in a declared CRS; GCJ-02/BD-09 cannot be mixed directly.",
            coordinate_system=str(coordinate_system),
        )])


def _metric_crs(crs):
    try:
        parsed = CRS.from_user_input(crs)
    except (CRSError, ValueError, TypeError) as exc:
        raise SpatialInputError("invalid_analysis_crs", "A valid analysis CRS is required.", [
            _issue("invalid_analysis_crs", str(exc), field="analysis_crs", crs=str(crs))
        ]) from exc
    axes = parsed.axis_info
    if (not parsed.is_projected or parsed.to_epsg() == 3857 or len(axes) < 2
            or any(axis.unit_name.lower() not in ("metre", "meter")
                   or axis.unit_conversion_factor != 1 for axis in axes[:2])):
        _raise_issues([_issue(
            "invalid_analysis_crs", "Analysis requires a projected CRS with metre axes, excluding Web Mercator.",
            field="analysis_crs", crs=parsed.to_string(),
        )])
    return parsed


def _validate_structure(frame, id_column):
    if not isinstance(frame, gpd.GeoDataFrame):
        _raise_issues([_issue("invalid_frame", "Expected a GeoDataFrame.")])
    if id_column not in frame.columns:
        _raise_issues([_issue("missing_field", "ID field is missing.", field=id_column)])
    try:
        frame.geometry
    except AttributeError:
        _raise_issues([_issue("missing_geometry", "An active geometry column is required.")])
    if frame.crs is None:
        _raise_issues([_issue("missing_crs", "Input CRS must be explicitly declared.", field="crs")])
    issues = []
    ids = frame[id_column]
    kinds = set()
    for position, value in enumerate(ids):
        details = {"id": _json_scalar(value), "field": id_column, "row": position}
        if (pd.api.types.is_scalar(value) and pd.isna(value)) or (isinstance(value, str) and not value.strip()):
            issues.append(_issue("missing_id", "ID must not be empty.", **details))
        elif isinstance(value, str):
            kinds.add("str")
        elif isinstance(value, Integral) and not isinstance(value, (bool, np.bool_)):
            kinds.add("int")
        else:
            issues.append(_issue("invalid_id_type", "IDs must be all strings or all integers, excluding booleans.", **details))
    _raise_issues(issues)
    if len(kinds) > 1:
        _raise_issues([_issue("invalid_id_type", "Mixed ID types are not allowed.", field=id_column)])
    duplicate = ids.duplicated(keep=False).to_numpy()
    _raise_issues([
        _issue("duplicate_id", "Business ID must be unique.", id=_json_scalar(ids.iloc[pos]), field=id_column, row=pos)
        for pos in np.flatnonzero(duplicate).tolist()
    ])


def _geometry_issues(frame, id_column, geometry_types):
    issues = []
    for position, (identifier, geometry) in enumerate(zip(frame[id_column], frame.geometry)):
        details = {"id": _json_scalar(identifier), "field": frame.geometry.name, "row": position}
        if geometry is None or geometry.is_empty:
            issue = _issue("empty_geometry", "Geometry must not be null or empty.", **details)
        elif geometry.has_z or getattr(geometry, "has_m", False):
            issue = _issue("unsupported_dimension", "Only two-dimensional geometry is supported.", **details)
        elif not np.isfinite(get_coordinates(geometry)).all():
            issue = _issue("nonfinite_coordinates", "Coordinates must be finite.", **details)
        elif not geometry.is_valid:
            issue = _issue("invalid_geometry", explain_validity(geometry), **details)
        elif geometry.geom_type not in geometry_types:
            issue = _issue("unsupported_geometry", "Geometry type is not allowed.", geometry_type=geometry.geom_type, **details)
        else:
            continue
        issues.append(issue)
    return issues


def validate_layer(frame, *, id_column, geometry_types, require_metric=False) -> None:
    """Check ID, CRS, finite valid 2D geometry; optionally require metre axes.

    These formal CRS checks do not establish suitability for a study area.
    """
    _validate_structure(frame, id_column)
    _raise_issues(_geometry_issues(frame, id_column, geometry_types))
    if require_metric:
        _metric_crs(frame.crs)
