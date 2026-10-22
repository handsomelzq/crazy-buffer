"""Category validation and normalized entropy shared by research recipes."""

from numbers import Integral

import numpy as np
import pandas as pd

from ..validate import _issue, _raise_issues

MAX_CATEGORIES = 200


def prepare_categories(frame, *, id_column, category_column, categories=None):
    """Return ordered labels, an ID-to-label mapping and observed labels.

    Category values are treated as labels, never numeric measurements. A single
    layer may use strings or integers, but the two kinds cannot be mixed.
    """
    if category_column not in frame.columns:
        _raise_issues([_issue(
            "missing_field", "Category field is missing.", field=category_column,
        )])
    if category_column == id_column:
        _raise_issues([_issue(
            "category_id_overlap",
            "The category field must be separate from the business ID field.",
            category_column=category_column,
        )])

    issues = []
    kinds = set()
    observed = []
    category_by_id = {}
    normalized_by_label = {}
    for position, (identifier, value) in enumerate(
        zip(frame[id_column], frame[category_column])
    ):
        details = {
            "id": identifier, "field": category_column, "row": position,
        }
        if pd.api.types.is_scalar(value) and pd.isna(value):
            issues.append(_issue("missing_category", "Category must not be empty.", **details))
            continue
        if isinstance(value, str):
            label = value.strip()
            kind = "str"
            if not label:
                issues.append(_issue("missing_category", "Category must not be empty.", **details))
                continue
        elif (
            isinstance(value, Integral)
            and not isinstance(value, (bool, np.bool_))
        ):
            label = str(int(value))
            kind = "int"
        else:
            issues.append(_issue(
                "invalid_category_type",
                "Categories must be all strings or all integers, excluding booleans.",
                **details,
            ))
            continue
        if len(label) > 100:
            issues.append(_issue(
                "category_too_long",
                "Category labels must not exceed 100 characters.",
                **details,
            ))
            continue
        if "\n" in label or "\r" in label:
            issues.append(_issue(
                "invalid_category_label",
                "Category labels must be single-line text.",
                **details,
            ))
            continue
        previous = normalized_by_label.get(label)
        if previous is not None and previous != kind:
            issues.append(_issue(
                "mixed_category_type",
                "Category values that render identically cannot mix string and integer kinds.",
                **details,
            ))
            continue
        kinds.add(kind)
        normalized_by_label[label] = kind
        category_by_id[identifier] = label
        if label not in observed:
            observed.append(label)
    _raise_issues(issues)
    if len(kinds) > 1:
        _raise_issues([_issue(
            "mixed_category_type",
            "Category values must be all strings or all integers.",
            field=category_column,
        )])

    if categories is None:
        labels = observed
    else:
        if isinstance(categories, (str, bytes)) or not hasattr(categories, "__iter__"):
            _raise_issues([_issue(
                "invalid_categories",
                "categories must be an iterable of labels when supplied.",
                field="categories",
            )])
        labels = []
        for value in categories:
            if isinstance(value, bool) or not isinstance(value, (str, Integral)):
                _raise_issues([_issue(
                    "invalid_categories",
                    "Explicit categories must be strings or integers.",
                    value=str(value),
                )])
            label = value.strip() if isinstance(value, str) else str(int(value))
            if not label or "\n" in label or "\r" in label or len(label) > 100:
                _raise_issues([_issue(
                    "invalid_categories",
                    "Explicit categories must be non-empty single-line labels.",
                    value=str(value),
                )])
            if label not in labels:
                labels.append(label)
        unknown = [label for label in observed if label not in labels]
        if unknown:
            _raise_issues([_issue(
                "unknown_category",
                "Explicit categories must include every observed category.",
                categories=labels, unknown_categories=unknown,
            )])
    if len(labels) > MAX_CATEGORIES:
        _raise_issues([_issue(
            "too_many_categories",
            f"At most {MAX_CATEGORIES} categories are supported.",
            categories=len(labels),
        )])
    return labels, category_by_id, observed


def normalized_entropy(values):
    """Normalize Shannon entropy to 0..1 over positive category weights."""
    weights = np.asarray(values, dtype="float64")
    positive = weights[np.isfinite(weights) & (weights > 0)]
    if positive.size < 2:
        return 0.0 if positive.size == 1 else np.nan
    probabilities = positive / positive.sum()
    return float(-(probabilities * np.log(probabilities)).sum() / np.log(positive.size))


def metric_columns(kind, labels):
    """Return deterministic prefixed output columns for category metrics."""
    if kind == "facility":
        return [f"count_{label}" for label in labels] + [
            f"density_per_km2_{label}" for label in labels
        ]
    if kind == "land_use":
        return [f"area_m2_{label}" for label in labels] + [
            f"share_{label}" for label in labels
        ]
    raise ValueError(f"Unknown category metric kind: {kind}")
