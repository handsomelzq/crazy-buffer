"""Streaming composition of exact matching and attribute summaries."""
from ..errors import SpatialInputError
from ..operations.aggregate import _prepare_values, _accumulate, _finish
from ..operations.buffer import _validate_radius
from ..operations.neighbors import iter_neighbor_batches, _record_error


def buffer_stats(sources, targets, *, source_id, target_id, radius_m, value_column, batch_size=256, report=None):
    """Aggregate one bounded source batch at a time without collecting links."""
    try:
        radius=_validate_radius(radius_m)
        values=_prepare_values(sources,targets,source_id,target_id,value_column)
        counts={}; matches=0
        for links in iter_neighbor_batches(sources,targets,source_id=source_id,target_id=target_id,radius_m=radius,batch_size=batch_size):
            _accumulate(links,values,counts)
            matches+=len(links)
        result=_finish(sources,source_id,radius,counts)
    except SpatialInputError as exc:
        _record_error(report,exc); raise
    if report is not None:
        report.add_step('buffer_stats',dict(source_id=source_id,target_id=target_id,value_column=value_column,radius_m=radius,batch_size=int(batch_size),crs=sources.crs.to_string()),dict(sources=len(sources),targets=len(targets),matches=matches))
    return result
