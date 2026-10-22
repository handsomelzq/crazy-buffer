"""Synthetic categorized-POI density example. Writes only when executed."""
from pathlib import Path
import sys

import geopandas as gpd

from crazy_buffer import RunReport, export_run, facility_mix as calculate_facility_mix


def _inputs():
    snapshots = Path(__file__).resolve().parent.parent / "inputs"
    if snapshots.is_dir():
        return (
            gpd.read_file(snapshots / "communities.gpkg", layer="data"),
            gpd.read_file(snapshots / "facilities.gpkg", layer="data"),
        )
    import importlib.util

    helper = Path(__file__).with_name("sample_data.py")
    spec = importlib.util.spec_from_file_location("synthetic_sample_data", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.facility_mix()


def main(output_dir):
    communities, facilities = _inputs()
    report = RunReport()
    results = calculate_facility_mix(
        communities,
        facilities,
        source_id="id",
        target_id="id",
        category_column="type",
        radius_m=10,
        report=report,
    )
    spatial = communities.merge(results, left_on="id", right_on="source_id")
    return export_run(
        results,
        output_dir,
        report=report,
        spatial=spatial,
        input_frames={"communities": communities, "facilities": facilities},
        script_path=__file__,
        metadata={"data": "synthetic CC0", "example": "facility_mix"},
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "facility-mix-run")
