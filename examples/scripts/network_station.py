"""Reproducible synthetic road routing; writes only when executed."""
from pathlib import Path
import sys
import geopandas as gpd
from shapely.geometry import Point, LineString
from crazy_buffer import RunReport, build_network, nearest_network_distance, export_run


def inputs():
    directory = Path(__file__).resolve().parent.parent / 'inputs'
    if directory.is_dir():
        return tuple(gpd.read_file(directory / f'{name}.gpkg', layer='data') for name in ('sources', 'targets', 'edges'))
    def layer(ids, geometry):
        return gpd.GeoDataFrame({'id': ids}, geometry=geometry, crs='EPSG:32650')
    return (layer(['home-1', 'home-2'], [Point(20, 3), Point(90, 2)]),
            layer(['station'], [Point(60, 4)]),
            layer(['road'], [LineString([(0, 0), (100, 0)])]))


def main(output):
    sources, targets, edges = inputs()
    report = RunReport()
    network = build_network(edges, edge_id='id', report=report)
    results = nearest_network_distance(sources, targets, network, source_id='id', target_id='id', report=report)
    return export_run(results, output, report=report,
        input_frames={'sources': sources, 'targets': targets, 'edges': edges},
        script_path=__file__, metadata={'data': 'synthetic CC0', 'example': 'network_station'})


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'network_station-run')
