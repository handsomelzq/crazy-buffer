"""Categorized point counts, density and diversity within exact buffers."""

from collections import Counter
from copy import deepcopy

import numpy as np
import pandas as pd

from ..errors import SpatialInputError
from ..operations.buffer import _validate_radius
from ..operations.categories import (
    metric_columns, normalized_entropy, prepare_categories,
)
from ..operations.neighbors import (
    _validate_max_matches, _validate_pair, iter_neighbor_batches,
)
from ..validate import _issue, _raise_issues


def _record_error(report, exc):
    if report is not None:
        report.issues.extend(deepcopy(exc.issues))


def facility_mix(
    sources,
    targets,
    *,
    source_id,
    target_id,
    category_column,
    radius_m,
    categories=None,
    batch_size=256,
    max_matches=1_000_000,
    report=None,
):
    """Return category counts and densities per source buffer.

    Density uses the full planar buffer area as denominator. Each target point
    contributes one count; labels are not treated as measurements. Diversity is
    normalized Shannon entropy over categories observed inside that source.
    """
    try:
        radius = _validate_radius(radius_m)
        limit = _validate_max_matches(max_matches)
        _validate_pair(sources, targets, source_id, target_id)
        labels, category_by_id, observed = prepare_categories(
            targets,
            id_column=target_id,
            category_column=category_column,
            categories=categories,
        )
        counts = {}
        matches = 0
        for links in iter_neighbor_batches(
            sources,
            targets,
            source_id=source_id,
            target_id=target_id,
            radius_m=radius,
            batch_size=batch_size,
            max_matches=limit,
        ):
            for source_value, target_value in links[
                ["source_id", "target_id"]
            ].itertuples(index=False, name=None):
                counts.setdefault(source_value, Counter())[
                    category_by_id[target_value]
                ] += 1
            matches += len(links)

        areas = {
            identifier: float(area)
            for identifier, area in zip(
                sources[source_id],
                sources.geometry.buffer(radius, quad_segs=32).area,
            )
        }
        rows = []
        for identifier in sources[source_id]:
            category_counts = counts.get(identifier, Counter())
            present_weights = [category_counts[label] for label in labels]
            total = sum(present_weights)
            area = areas[identifier]
            row = {
                "source_id": identifier,
                "radius_m": radius,
                "n_targets": total,
                "n_categories_present": sum(value > 0 for value in present_weights),
            }
            for label in labels:
                count = category_counts[label]
                row[f"count_{label}"] = count
            row["entropy"] = normalized_entropy(present_weights)
            for label in labels:
                count = category_counts[label]
                row[f"density_per_km2_{label}"] = count / area * 1_000_000
            row.update({
                "buffer_area_m2": area,
                "total_density_per_km2": total / area * 1_000_000,
                "status": "ok" if total else "no_matches",
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
                "n_targets": pd.Series([], dtype="int64"),
                "n_categories_present": pd.Series([], dtype="int64"),
                "entropy": pd.Series([], dtype="float64"),
                "buffer_area_m2": pd.Series([], dtype="float64"),
                "total_density_per_km2": pd.Series([], dtype="float64"),
                "status": pd.Series([], dtype="object"),
                **{
                    column: pd.Series([], dtype="float64")
                    for column in metric_columns("facility", labels)
                },
            })
    except SpatialInputError as exc:
        _record_error(report, exc)
        raise

    if report is not None:
        if matches == 0:
            report.issues.append(_issue(
                "no_spatial_matches",
                "No target points fall within the requested buffers.",
            ))
        report.add_step(
            "facility_mix",
            {
                "source_id": source_id,
                "target_id": target_id,
                "category_column": category_column,
                "categories": labels,
                "radius_m": radius,
                "crs": sources.crs.to_string(),
                "density_denominator": "full_buffer_area",
                "entropy_normalization": "log_categories_present",
            },
            {"sources": len(sources), "targets": len(targets), "matches": matches},
        )
    return result
