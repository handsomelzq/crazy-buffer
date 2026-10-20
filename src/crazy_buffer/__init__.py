"""Composable spatial analysis with explicit, validated inputs."""

from .api import (
    RunReport, SpatialInputError, iter_neighbor_batches, make_buffers, neighbors_within,
    prepare_layer, read_geopackage, read_points_csv,
)

__all__ = ["make_buffers", "neighbors_within", "iter_neighbor_batches", "RunReport", "SpatialInputError", "prepare_layer", "read_geopackage", "read_points_csv"]

from .api import summarize_neighbors, buffer_stats
__all__ += ['summarize_neighbors', 'buffer_stats']

from .api import nearest_distance
__all__ += ['nearest_distance']

from .api import export_run
__all__ += ['export_run']
