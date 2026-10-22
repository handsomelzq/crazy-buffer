"""Synthetic land-use composition example. Writes only when executed."""
from pathlib import Path
import sys

import geopandas as gpd

from crazy_buffer import RunReport, export_run, land_use_mix as calculate_land_use_mix


def _inputs():
    snapshots = Path(__file__).resolve().parent.parent / "inputs"
    if snapshots.is_dir():
        return (
            gpd.read_file(snapshots / "communities.gpkg", layer="data"),
            gpd.read_file(snapshots / "parcels.gpkg", layer="data"),
        )
    import importlib.util

    helper = Path(__file__).with_name("sample_data.py")
    spec = importlib.util.spec_from_file_location("synthetic_sample_data", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.land_use_mix()


def main(output_dir):
    communities, parcels = _inputs()
    report = RunReport()
    results = calculate_land_use_mix(
        communities,
        parcels,
        source_id="id",
        land_use_id="id",
        category_column="use",
        report=report,
    )
    spatial = communities.merge(results, left_on="id", right_on="source_id")
    return export_run(
        results,
        output_dir,
        report=report,
        spatial=spatial,
        input_frames={"communities": communities, "parcels": parcels},
        script_path=__file__,
        metadata={"data": "synthetic CC0", "example": "land_use_mix"},
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "land-use-mix-run")
