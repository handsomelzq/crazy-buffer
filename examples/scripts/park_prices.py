"""Synthetic park_prices example. No files are written on import."""
from pathlib import Path
import sys
import geopandas as gpd
from crazy_buffer import RunReport, buffer_stats, make_buffers, export_run


def _inputs():
    snapshots = Path(__file__).resolve().parent.parent / 'inputs'
    if snapshots.is_dir():
        return (gpd.read_file(snapshots / 'parks.gpkg', layer='data'),
                gpd.read_file(snapshots / 'homes.gpkg', layer='data'))
    # Source checkout only: the exported script takes the snapshot branch above.
    import importlib.util
    helper = Path(__file__).with_name('sample_data.py')
    spec = importlib.util.spec_from_file_location('synthetic_sample_data', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.park_prices()


def main(output_dir):
    sources, targets = _inputs()
    report = RunReport()
    results = buffer_stats(sources, targets, source_id='id', target_id='id', radius_m=5, value_column='price', report=report)
    spatial = make_buffers(sources, source_id='id', radius_m=5, report=report).merge(results, left_on='id', right_on='source_id')
    return export_run(results, output_dir, report=report, spatial=spatial,
                      input_frames={'parks': sources, 'homes': targets},
                      script_path=__file__, metadata={'data': 'synthetic CC0', 'example': 'park_prices'})


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'park_prices-run')
