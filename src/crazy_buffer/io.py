"""Local CSV and GeoPackage readers with explicit coordinate declarations."""

from copy import deepcopy

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from pyproj.exceptions import CRSError

from .errors import SpatialInputError
from .validate import _issue, _json_scalar, _raise_issues, _validate_coordinate_system, validate_layer


def _record_error(report, exc):
    if report is not None:
        report.issues.extend(deepcopy(exc.issues))


def read_points_csv(path, *, id_column, x_column, y_column, crs,
                    coordinate_system="declared_crs", report=None) -> gpd.GeoDataFrame:
    """Read IDs as strings (including leading zeros), without filling missing IDs."""
    try:
        _validate_coordinate_system(coordinate_system)
        try:
            frame = pd.read_csv(path, converters={
                id_column: lambda value: pd.NA if not value.strip() else value,
            })
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            raise SpatialInputError("read_error", "CSV could not be read.", [
                _issue("read_error", str(exc), path=str(path))
            ]) from exc
        _raise_issues([
            _issue("missing_field", "Required CSV field is missing.", field=column)
            for column in (id_column, x_column, y_column) if column not in frame.columns
        ])
        coordinates = []
        issues = []
        for column in (x_column, y_column):
            values = pd.to_numeric(frame[column], errors="coerce")
            invalid = ~np.isfinite(values.to_numpy(dtype=float, na_value=np.nan))
            issues.extend(
                _issue("invalid_coordinate", "Coordinate must be a finite number.",
                       field=column, row=pos, id=_json_scalar(frame[id_column].iloc[pos]))
                for pos in np.flatnonzero(invalid).tolist()
            )
            coordinates.append(values)
        _raise_issues(issues)
        try:
            result = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(*coordinates), crs=crs)
        except (CRSError, ValueError, TypeError) as exc:
            raise SpatialInputError("invalid_crs", "Input CRS is invalid.", [
                _issue("invalid_crs", str(exc), field="crs", crs=str(crs))
            ]) from exc
        validate_layer(result, id_column=id_column, geometry_types=("Point",))
    except SpatialInputError as exc:
        _record_error(report, exc)
        raise
    if report is not None:
        report.add_step("read_points_csv", {
            "path": str(path), "id_column": id_column, "x_column": x_column,
            "y_column": y_column, "crs": result.crs.to_string(),
            "coordinate_system": coordinate_system,
        }, {"output": len(result)})
    return result


def read_geopackage(path, *, layer, id_column, coordinate_system="declared_crs", report=None) -> gpd.GeoDataFrame:
    """Read an explicitly selected layer; never choose the first layer implicitly."""
    try:
        _validate_coordinate_system(coordinate_system)
        try:
            available = pyogrio.list_layers(path)[:, 0].tolist()
        except (OSError, ValueError, pyogrio.errors.DataSourceError) as exc:
            raise SpatialInputError("read_error", "GeoPackage could not be opened.", [
                _issue("read_error", str(exc), path=str(path), layer=str(layer))
            ]) from exc
        if layer not in available:
            _raise_issues([_issue("missing_layer", "Requested layer does not exist.", layer=layer, path=str(path))])
        try:
            result = gpd.read_file(path, layer=layer, engine="pyogrio")
        except (OSError, ValueError, pyogrio.errors.DataSourceError, pyogrio.errors.DataLayerError) as exc:
            raise SpatialInputError("read_error", "GeoPackage layer could not be read.", [
                _issue("read_error", str(exc), path=str(path), layer=str(layer))
            ]) from exc
        validate_layer(result, id_column=id_column, geometry_types=("Point", "LineString", "Polygon", "MultiPolygon"))
    except SpatialInputError as exc:
        _record_error(report, exc)
        raise
    if report is not None:
        report.add_step("read_geopackage", {
            "path": str(path), "layer": layer, "id_column": id_column,
            "crs": result.crs.to_string(), "coordinate_system": coordinate_system,
        }, {"output": len(result)})
    return result
