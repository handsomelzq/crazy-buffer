"""Land-use area, shares and diversity in explicit planar analysis regions."""

from copy import deepcopy

import numpy as np
import pandas as pd
from shapely.ops import unary_union

from ..errors import SpatialInputError
from ..operations.buffer import _validate_radius
from ..operations.categories import (
    metric_columns, normalized_entropy, prepare_categories,
)
from ..validate import _issue, _raise_issues, validate_layer


def _record_error(report, exc):
    if report is not None:
        report.issues.extend(deepcopy(exc.issues))


def _validate_layers(sources, land_use, source_id, land_use_id, radius):
    source_types = (
        ("Point", "Polygon", "MultiPolygon")
        if radius is not None else ("Polygon", "MultiPolygon")
    )
    validate_layer(
        sources, id_column=source_id, geometry_types=source_types,
        require_metric=True,
    )
    if land_use.crs is not None and sources.crs != land_use.crs:
        _raise_issues([_issue(
            "CRS_MISMATCH",
            "Sources and land-use polygons must use the same CRS.",
            source_crs=sources.crs.to_string(),
            land_use_crs=land_use.crs.to_string(),
        )])
    validate_layer(
        land_use, id_column=land_use_id,
        geometry_types=("Polygon", "MultiPolygon"), require_metric=True,
    )


def land_use_mix(
    sources,
    land_use,
    *,
    source_id,
    land_use_id,
    category_column,
    radius_m=None,
    categories=None,
    max_intersections=1_000_000,
    report=None,
):
    """Return land-use areas and shares for each source study region.

    With ``radius_m=None`` the source polygon itself is the study region.
    Otherwise the source is buffered outward. Same-category intersections are
    dissolved before area calculation. Different-category overlaps remain
    visible through ``overlap_area_m2`` and a run-report issue.
    """
    try:
        radius = None if radius_m is None else _validate_radius(radius_m)
        if (
            isinstance(max_intersections, (bool, np.bool_))
            or not isinstance(max_intersections, (int, np.integer))
            or max_intersections <= 0
        ):
            _raise_issues([_issue(
                "INVALID_MAX_INTERSECTIONS",
                "max_intersections must be a positive integer.",
                max_intersections=str(max_intersections),
            )])
        _validate_layers(sources, land_use, source_id, land_use_id, radius)
        labels, category_by_polygon, observed = prepare_categories(
            land_use,
            id_column=land_use_id,
            category_column=category_column,
            categories=categories,
        )
        region_geometries = (
            sources.geometry
            if radius is None
            else sources.geometry.buffer(radius, quad_segs=32)
        )
        land_use_geometries = land_use.geometry.tolist()
        land_use_categories = land_use[land_use_id].map(category_by_polygon).tolist()
        index = land_use.sindex
        intersections = 0
        rows = []
        for identifier, region in zip(sources[source_id], region_geometries):
            candidates = sorted(index.query(region).tolist())
            category_parts = {label: [] for label in labels}
            for position in candidates:
                intersections += 1
                if intersections > max_intersections:
                    _raise_issues([_issue(
                        "INTERSECTION_LIMIT_EXCEEDED",
                        "The number of source-land-use candidates exceeds max_intersections.",
                        max_intersections=max_intersections,
                        intersections=intersections,
                    )])
                clipped = region.intersection(land_use_geometries[position])
                if clipped.is_empty:
                    continue
                category_parts[land_use_categories[position]].append(clipped)

            category_areas = {
                label: float(unary_union(parts).area) if parts else 0.0
                for label, parts in category_parts.items()
            }
            all_parts = [
                part
                for parts in category_parts.values()
                for part in parts
            ]
            region_area = float(region.area)
            covered_area = float(unary_union(all_parts).area) if all_parts else 0.0
            category_total = sum(category_areas.values())
            overlap_area = max(0.0, category_total - covered_area)
            coverage = min(1.0, covered_area / region_area)
            weights = [category_areas[label] for label in labels]
            row = {
                "source_id": identifier,
                "radius_m": np.nan if radius is None else radius,
                "coverage": coverage,
                "n_categories_present": sum(value > 0 for value in weights),
            }
            for label in labels:
                area = category_areas[label]
                row[f"area_m2_{label}"] = area
            for label in labels:
                area = category_areas[label]
                row[f"share_{label}"] = area / region_area
            row.update({
                "entropy": normalized_entropy(weights),
                "region_area_m2": region_area,
                "covered_area_m2": covered_area,
                "overlap_area_m2": overlap_area,
                "status": "ok" if covered_area > 0 else "no_land_use",
            })
            rows.append(row)
        result = pd.DataFrame(rows)
        if len(result):
            result["source_id"] = pd.Series(
                sources[source_id].tolist(), dtype=sources[source_id].dtype,
            )
        else:
            result = pd.DataFrame({
                "source_id": pd.Series([], dtype=sources[source_id].dtype),
                "radius_m": pd.Series([], dtype="float64"),
                "coverage": pd.Series([], dtype="float64"),
                "n_categories_present": pd.Series([], dtype="int64"),
                "entropy": pd.Series([], dtype="float64"),
                "region_area_m2": pd.Series([], dtype="float64"),
                "covered_area_m2": pd.Series([], dtype="float64"),
                "overlap_area_m2": pd.Series([], dtype="float64"),
                "status": pd.Series([], dtype="object"),
                **{
                    column: pd.Series([], dtype="float64")
                    for column in metric_columns("land_use", labels)
                },
            })
    except SpatialInputError as exc:
        _record_error(report, exc)
        raise

    if report is not None:
        overlapping = result["overlap_area_m2"] > 1e-8 if len(result) else []
        if isinstance(overlapping, pd.Series) and overlapping.any():
            report.issues.append(_issue(
                "OVERLAPPING_LAND_USE",
                "Some analysis regions contain overlapping different-category polygons.",
                source_ids=result.loc[overlapping, "source_id"].tolist(),
                overlap_area_m2=float(result.loc[overlapping, "overlap_area_m2"].sum()),
            ))
        report.add_step(
            "land_use_mix",
            {
                "source_id": source_id,
                "land_use_id": land_use_id,
                "category_column": category_column,
                "categories": labels,
                "radius_m": radius,
                "crs": sources.crs.to_string(),
                "share_denominator": "analysis_region_area",
                "entropy_normalization": "log_categories_present",
            },
            {
                "sources": len(sources),
                "land_use": len(land_use),
                "candidate_intersections": intersections,
            },
        )
    return result
