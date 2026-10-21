"""Bounded local input, public-API composition and safe JSON replay snapshots."""
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import tempfile
import zipfile

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely import from_wkb
from shapely.geometry import LineString, Point
from crazy_buffer import (RunReport, prepare_layer, buffer_stats, nearest_distance,
                          build_network, nearest_network_distance, export_run)

MAX_BYTES = 20 * 1024 * 1024
LIMITS = {'sources': 5000, 'targets': 5000, 'edges': 20000}


def check_bytes(data):
    if len(data) > MAX_BYTES:
        raise ValueError('每个文件最多 20 MB。')


@contextmanager
def local_file(data):
    check_bytes(data)
    with tempfile.TemporaryDirectory(prefix='crazy-buffer-') as directory:
        path = Path(directory) / 'upload.gpkg'
        path.write_bytes(data)
        yield path


def inspect_upload(data, kind):
    check_bytes(data)
    if kind == 'csv':
        return {'columns': pd.read_csv(BytesIO(data), nrows=0).columns.tolist()}
    with local_file(data) as path:
        return {'layers': pyogrio.list_layers(path)[:, 0].tolist()}


def load_upload(data, *, kind, role, layer=None, x=None, y=None, crs=None):
    check_bytes(data)
    limit = LIMITS[role]
    if kind == 'csv':
        # Keep every string intact until the user explicitly selects numeric fields.
        frame = pd.read_csv(BytesIO(data), dtype='string', nrows=limit + 1)
        if len(frame) > limit:
            raise ValueError(f'{role} 最多 {limit} 行。')
        if x is None or y is None:
            return frame
        frame = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(
            pd.to_numeric(frame[x], errors='raise'), pd.to_numeric(frame[y], errors='raise')), crs=crs)
    else:
        with local_file(data) as path:
            if layer not in pyogrio.list_layers(path)[:, 0]:
                raise ValueError('请明确选择有效的 GPKG 图层。')
            info = pyogrio.read_info(path, layer=layer)
            if info['features'] > limit:
                raise ValueError(f'{role} 最多 {limit} 行。')
            frame = gpd.read_file(path, layer=layer, rows=limit + 1, engine='pyogrio')
    if len(frame) > limit:
        raise ValueError(f'{role} 最多 {limit} 行。')
    return frame


def demo_inputs():
    crs = 'EPSG:32650'
    sources = gpd.GeoDataFrame({'id': ['001', '002']}, geometry=[Point(0, 10), Point(90, 0)], crs=crs)
    targets = gpd.GeoDataFrame({'id': ['010', '020'], 'value': [10., 30.]}, geometry=[Point(20, 0), Point(100, 0)], crs=crs)
    edges = gpd.GeoDataFrame({'id': ['road'], 'start': [1], 'end': [2]}, geometry=[LineString([(0, 0), (100, 0)])], crs=crs)
    return {'sources': sources, 'targets': targets, 'edges': edges}


def encode_frame(frame):
    columns = {}
    for name in frame.columns:
        if name == frame.geometry.name:
            continue
        series = frame[name]
        dtype = str(series.dtype)
        if dtype not in ('object', 'string', 'str', 'int64', 'int32', 'Int64', 'Int32', 'float64', 'float32', 'Float64', 'bool', 'boolean'):
            raise ValueError(f'快照暂不支持字段 {name} 的 dtype {dtype}。')
        values = [None if pd.isna(value) else value.item() if hasattr(value, 'item') else value for value in series]
        if any(value is not None and not isinstance(value, (str, int, float, bool)) for value in values):
            raise ValueError(f'快照不支持字段 {name} 的复杂对象。')
        columns[name] = {'dtype': dtype, 'values': values}
    return {'columns': columns, 'geometry_column': frame.geometry.name,
            'crs': frame.crs.to_wkt(), 'wkb': [g.wkb_hex for g in frame.geometry]}


def decode_frame(snapshot):
    columns = {name: pd.Series(item['values'], dtype=item['dtype']) for name, item in snapshot['columns'].items()}
    geometry_name = snapshot['geometry_column']
    columns[geometry_name] = [from_wkb(bytes.fromhex(value)) for value in snapshot['wkb']]
    return gpd.GeoDataFrame(columns, geometry=geometry_name, crs=snapshot['crs'])


def run_analysis(inputs, params):
    report = RunReport()
    prepared = {}
    roles = ('sources', 'targets', 'edges') if params['task'] == 'network' else ('sources', 'targets')
    for role in roles:
        if len(inputs[role]) > LIMITS[role]:
            raise ValueError(f'{role} 最多 {LIMITS[role]} 行。')
    if params['task'] == 'network' and len(inputs['targets']) * (len(inputs['sources']) + len(inputs['edges'])) > 2_000_000:
        raise ValueError('路由工作量超过 2000000；请按研究区裁剪道路或减少目标。')
    for role in roles:
        prepared[role] = prepare_layer(inputs[role], id_column=params[role + '_id'], analysis_crs=params['analysis_crs'],
            geometry_types=(('LineString',) if role == 'edges' else ('Point', 'Polygon', 'MultiPolygon') if role == 'sources' and params['task'] == 'buffer' else ('Point',)),
            coordinate_system=params.get('coordinate_system', 'declared_crs'), report=report)
    common = dict(source_id=params['sources_id'], target_id=params['targets_id'], report=report)
    if params['task'] == 'buffer':
        prepared['targets'][params['value_column']] = pd.to_numeric(prepared['targets'][params['value_column']], errors='raise')
        result = buffer_stats(prepared['sources'], prepared['targets'], radius_m=params['radius_m'], value_column=params['value_column'], **common)
    elif params['task'] == 'nearest':
        result = nearest_distance(prepared['sources'], prepared['targets'], **common)
    else:
        network = build_network(prepared['edges'], edge_id=params['edges_id'], directed=params['directed'],
            from_node=params.get('from_node'), to_node=params.get('to_node'), report=report)
        result = nearest_network_distance(prepared['sources'], prepared['targets'], network,
            max_snap_distance_m=params['max_snap_distance_m'], **common)
    return result, report


REPLAY = '''from pathlib import Path
import json
from crazy_buffer.gui.service import decode_frame, run_analysis
root = Path(__file__).resolve().parent
if not (root / "run_manifest.json").is_file():
    root = root.parent
if not (root / "run_manifest.json").is_file():
    raise FileNotFoundError("Run manifest not found beside replay bundle")
parameters = json.loads((root / "inputs/parameters.json").read_text(encoding="utf-8"))
snapshots = json.loads((root / "inputs/inputs.json").read_text(encoding="utf-8"))
result, report = run_analysis({key: decode_frame(value) for key, value in snapshots.items()}, parameters)
result.to_csv(root / "replayed.csv", index=False)
(root / "replayed-quality.json").write_text(json.dumps(report.issues, ensure_ascii=False, allow_nan=False), encoding="utf-8")
'''


def freeze_run(inputs, params):
    roles = ('sources', 'targets', 'edges') if params['task'] == 'network' else ('sources', 'targets')
    # Snapshot only fields used by this analysis; unrelated date/object attributes
    # must not prevent reproducible computation or unnecessarily expose data.
    selected = {}
    for role in roles:
        columns = [params[role + '_id'], inputs[role].geometry.name]
        if role == 'targets' and params['task'] == 'buffer':
            columns.append(params['value_column'])
        if role == 'edges':
            columns.extend(params[key] for key in ('from_node', 'to_node') if params.get(key))
        selected[role] = inputs[role][list(dict.fromkeys(columns))].copy()
    snapshots = {role: encode_frame(selected[role]) for role in roles}
    result, report = run_analysis(inputs, params)
    csv = result.to_csv(index=False).encode('utf-8-sig')
    output = BytesIO()
    with tempfile.TemporaryDirectory(prefix='crazy-buffer-export-') as directory:
        root = Path(directory)
        snapshot_path = root / 'inputs.json'
        snapshot_path.write_text(json.dumps(snapshots, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        parameter_path = root / 'parameters.json'
        parameter_path.write_text(json.dumps(params, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        script_path = root / 'script.py'
        script_path.write_text(REPLAY, encoding='utf-8')
        exported = export_run(result, root / 'run', report=report,
            input_files={'inputs.json': snapshot_path, 'parameters.json': parameter_path},
            script_path=script_path, metadata={'snapshot_format': 'json-wkb-v1', 'snapshot_scope': 'analysis_fields_only',
                'replay': 'generated_not_executed', 'parameters': params})
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(exported.rglob('*')):
                if path.is_file():
                    archive.write(path, str(path.relative_to(exported)))
            archive.writestr('replay.py', REPLAY)
    if output.tell() > 60 * 1024 * 1024:
        raise ValueError('重放包超过 60 MB，请缩小输入。')
    return {'result': result, 'report': report, 'csv': csv, 'zip': output.getvalue()}
