"""Validated relationship aggregation, shared with streaming recipes."""
from numbers import Real, Integral
import numpy as np
import pandas as pd
from ..validate import _raise_issues, _issue, _json_scalar
from ..errors import SpatialInputError
from .buffer import _validate_radius
from .neighbors import _validate_pair, _record_error


def _numeric(value):
    return isinstance(value, Real) and not isinstance(value, (bool, np.bool_)) and np.isfinite(value)


def _prepare_values(sources, targets, source_id, target_id, value_column):
    _validate_pair(sources, targets, source_id, target_id)
    if value_column not in targets.columns:
        _raise_issues([_issue('missing_field','Value field is missing.',field=value_column)])
    values = {}
    issues = []
    for identifier, value in zip(targets[target_id], targets[value_column]):
        if pd.api.types.is_scalar(value) and pd.isna(value):
            values[identifier] = None
        elif not _numeric(value):
            issues.append(_issue('invalid_value','Values must be finite numbers or null.',id=_json_scalar(identifier),field=value_column,value=_json_scalar(value)))
        else:
            values[identifier] = float(value)
    _raise_issues(issues)
    return values


def _check_links(links, sources, values, radius_m):
    columns = ['source_id','target_id','distance_m','radius_m']
    if not isinstance(links,pd.DataFrame) or any(c not in links.columns for c in columns):
        _raise_issues([_issue('invalid_links','Links require source_id, target_id, distance_m, radius_m.')])
    radius = None if radius_m is None else _validate_radius(radius_m)
    if len(links)==0:
        if radius is None:
            _raise_issues([_issue('missing_radius','Empty links require radius_m.')])
        return radius
    source_set=set(sources)
    # Python equality equates True and 1; require the original ID kind too.
    source_kind = str if not sources or isinstance(sources[0],str) else Integral
    target_kind = str if not values or isinstance(next(iter(values)),str) else Integral
    seen=set()
    for position,row in enumerate(links[columns].itertuples(index=False,name=None)):
        sid,tid,distance,row_radius=row
        details={'row':position,'source_id':_json_scalar(sid),'target_id':_json_scalar(tid)}
        valid_sid=isinstance(sid,source_kind) and not isinstance(sid,(bool,np.bool_))
        valid_tid=isinstance(tid,target_kind) and not isinstance(tid,(bool,np.bool_))
        if not valid_sid or not valid_tid or sid not in source_set or tid not in values:
            _raise_issues([_issue('orphan_link','Relationship IDs must exist in their input layers.',**details)])
        if (sid,tid) in seen:
            _raise_issues([_issue('duplicate_link','Source-target pairs must be unique.',**details)])
        seen.add((sid,tid))
        if not _numeric(row_radius) or row_radius<=0:
            _raise_issues([_issue('invalid_radius','Relationship radius must be positive and finite.',**details)])
        if radius is None: radius=float(row_radius)
        if row_radius!=radius:
            _raise_issues([_issue('mixed_radius','All relationships must use the same radius.',**details)])
        if not _numeric(distance) or distance<0 or distance>radius:
            _raise_issues([_issue('invalid_distance','Distance must be finite, nonnegative and within radius.',**details)])
    return radius


def _accumulate(links, values, counts):
    for sid, tid in links[['source_id', 'target_id']].itertuples(index=False, name=None):
        state = counts.setdefault(sid, [0, 0, 0.])
        state[0] += 1
        value = values[tid]
        if value is not None:
            previous_count = state[1]
            state[1] += 1
            # A convex weighted mean avoids overflowing either a running sum
            # or value - previous_mean for finite values of opposite signs.
            state[2] = (
                state[2] * (previous_count / state[1])
                + value / state[1]
            )


def _finish(sources, source_id, radius, counts):
    rows = []
    for sid in sources[source_id]:
        n_matches, n_valid, mean = counts.get(sid, (0, 0, 0.))
        if n_valid:
            status = 'ok'
        elif n_matches:
            status = 'no_valid_values'
        else:
            status = 'no_matches'
        rows.append((
            sid, radius, n_matches, n_valid,
            mean if n_valid else np.nan, status,
        ))
    result = pd.DataFrame(rows, columns=[
        'source_id', 'radius_m', 'n_matches', 'n_valid_values',
        'mean_value', 'status',
    ])
    result['source_id'] = pd.Series(
        sources[source_id].tolist(), dtype=sources[source_id].dtype,
    )
    return result.astype({
        'radius_m': 'float64', 'n_matches': 'int64',
        'n_valid_values': 'int64', 'mean_value': 'float64', 'status': 'object',
    })


def summarize_neighbors(links, *, sources, targets, source_id, target_id, value_column, radius_m=None, report=None):
    """Summarize a validated subset of relationships, preserving all sources."""
    try:
        values=_prepare_values(sources,targets,source_id,target_id,value_column)
        radius=_check_links(links,sources[source_id].tolist(),values,radius_m)
        counts={}; _accumulate(links,values,counts)
        result=_finish(sources,source_id,radius,counts)
    except SpatialInputError as exc:
        _record_error(report,exc); raise
    if report is not None:
        report.add_step('summarize_neighbors',dict(source_id=source_id,target_id=target_id,value_column=value_column,radius_m=radius,crs=sources.crs.to_string()),dict(sources=len(sources),targets=len(targets),matches=len(links)))
    return result
