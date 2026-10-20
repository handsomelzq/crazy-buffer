"""Explicit projection and opt-in exclusion of unsuitable geometry."""

from copy import deepcopy

import geopandas as gpd

from .errors import SpatialInputError
from .validate import (
    _geometry_issues, _issue, _metric_crs, _raise_issues,
    _validate_coordinate_system, _validate_structure, validate_layer,
)


def prepare_layer(frame, *, id_column, analysis_crs, geometry_types,
                  coordinate_system="declared_crs", on_invalid="error", report=None) -> gpd.GeoDataFrame:
    """Return a projected copy. Never infer a CRS or repair geometry.

    ``drop`` excludes geometry problems only, and requires a report. ID and CRS
    contract violations remain errors. Choosing a locally suitable projection
    remains the caller's responsibility.
    """
    try:
        _validate_coordinate_system(coordinate_system)
        if on_invalid not in ("error", "drop"):
            _raise_issues([_issue("invalid_policy", "on_invalid must be 'error' or 'drop'.", field="on_invalid")])
        if on_invalid == "drop" and report is None:
            _raise_issues([_issue("report_required", "Explicit exclusions require a RunReport.")])
        _validate_structure(frame, id_column)
        target_crs = _metric_crs(analysis_crs)
        result = frame.copy(deep=True)
        excluded = []
        for projected in (False, True):
            if projected:
                result = result.to_crs(target_crs)
            issues = _geometry_issues(result, id_column, geometry_types)
            if on_invalid == "error":
                _raise_issues(issues)
            elif issues:
                excluded.extend({**item, "action": "excluded"} for item in issues)
                bad_positions = {item["row"] for item in issues}
                result = result.iloc[[pos for pos in range(len(result)) if pos not in bad_positions]].copy()
        validate_layer(result, id_column=id_column, geometry_types=geometry_types, require_metric=True)
    except SpatialInputError as exc:
        if report is not None:
            report.issues.extend(deepcopy(exc.issues))
        raise
    if report is not None:
        report.issues.extend(excluded)
        report.add_step("prepare_layer", {
            "id_column": id_column, "source_crs": frame.crs.to_string(),
            "analysis_crs": target_crs.to_string(), "geometry_types": list(geometry_types),
            "coordinate_system": coordinate_system, "on_invalid": on_invalid,
        }, {"input": len(frame), "output": len(result), "excluded": len(excluded)})
    return result
