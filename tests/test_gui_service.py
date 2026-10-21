import json
from pathlib import Path
import subprocess
import sys
import zipfile
from io import BytesIO

import geopandas as gpd
import pandas as pd
import pytest
from crazy_buffer.gui import service as svc


def parameters(task):
    return dict(task=task, sources_id='id', targets_id='id', edges_id='id', analysis_crs='EPSG:32650',
                radius_m=50., value_column='value', directed=False, max_snap_distance_m=100.,
                from_node='start', to_node='end')


@pytest.mark.parametrize('task', ['buffer', 'nearest', 'network'])
def test_export_replay_outside_repository(tmp_path, task):
    if task == 'network':
        pytest.importorskip('networkx')
    tmp_path = tmp_path / 'artifacts'
    tmp_path.mkdir()
    inputs = svc.demo_inputs()
    inputs['sources'] = inputs['sources'].rename_geometry('position')
    frozen = svc.freeze_run(inputs, parameters(task))
    with zipfile.ZipFile(BytesIO(frozen['zip'])) as archive:
        assert {'results.csv', 'quality.json', 'run_manifest.json', 'inputs/inputs.json', 'inputs/parameters.json', 'artifacts/script.py', 'replay.py'} <= set(archive.namelist())
        archive.extractall(tmp_path)
    subprocess.run([sys.executable, str(tmp_path / 'replay.py')], cwd=tmp_path, check=True,
                   capture_output=True, text=True, timeout=30)
    expected = pd.read_csv(tmp_path / 'results.csv', dtype={'source_id': 'string', 'target_id': 'string'})
    actual = pd.read_csv(tmp_path / 'replayed.csv', dtype={'source_id': 'string', 'target_id': 'string'})
    pd.testing.assert_frame_equal(expected, actual)
    snapshot = json.loads((tmp_path / 'inputs/inputs.json').read_text())
    assert snapshot['sources']['columns']['id']['values'] == ['001', '002']
    assert snapshot['sources']['geometry_column'] == 'position'
    if task == 'network':
        assert snapshot['edges']['columns']['start']['dtype'] == 'int64'


def test_csv_leading_zeros_and_limits(monkeypatch):
    data = b'id,x,y,value\n001,0,0,10\n002,1,0,20\n'
    frame = svc.load_upload(data, kind='csv', role='sources', x='x', y='y', crs='EPSG:32650')
    assert frame.id.tolist() == ['001', '002']
    monkeypatch.setitem(svc.LIMITS, 'sources', 1)
    with pytest.raises(ValueError, match='1'):
        svc.load_upload(data, kind='csv', role='sources', x='x', y='y', crs='EPSG:32650')
    monkeypatch.setattr(svc, 'MAX_BYTES', 1)
    with pytest.raises(ValueError, match='20 MB'):
        svc.inspect_upload(data, 'csv')


def test_explicit_gpkg_layer_and_cleanup(tmp_path):
    path = tmp_path / 'layers.gpkg'
    inputs = svc.demo_inputs()
    inputs['sources'].to_file(path, layer='sources')
    inputs['targets'].to_file(path, layer='targets')
    data = path.read_bytes()
    assert svc.inspect_upload(data, 'gpkg')['layers'] == ['sources', 'targets']
    with pytest.raises(ValueError, match='图层'):
        svc.load_upload(data, kind='gpkg', role='sources')
    assert svc.load_upload(data, kind='gpkg', role='targets', layer='targets').id.tolist() == ['010', '020']
    with pytest.raises(RuntimeError):
        with svc.local_file(data) as temporary:
            assert temporary.exists()
            raise RuntimeError()
    assert not temporary.exists()


def test_route_budget_before_projection(monkeypatch):
    inputs = svc.demo_inputs()
    inputs['targets'] = pd.concat([inputs['targets']] * 1001)
    inputs['edges'] = pd.concat([inputs['edges']] * 1000)
    monkeypatch.setattr(svc, 'prepare_layer', lambda *a, **k: pytest.fail('projection ran before budget'))
    with pytest.raises(ValueError, match='2000000'):
        svc.run_analysis(inputs, parameters('network'))


def test_polygon_buffer_and_nonfinite_snapshot():
    from shapely.geometry import box
    inputs = svc.demo_inputs()
    inputs['sources'] = gpd.GeoDataFrame({'id': ['park']}, geometry=[box(0, -5, 30, 5)], crs='EPSG:32650')
    frozen = svc.freeze_run(inputs, parameters('buffer'))
    assert frozen['result'].mean_value.tolist() == [10.0]
    inputs['targets']['value'] = [float('inf'), 1.]
    with pytest.raises(ValueError):
        svc.freeze_run(inputs, parameters('buffer'))


def test_zip_strict_json_hashes_and_unused_attributes(tmp_path):
    import hashlib
    inputs = svc.demo_inputs()
    inputs['sources']['unused_date'] = pd.to_datetime(['2026-01-01', '2026-01-02'])
    inputs['targets']['value'] = [float('nan'), 30.]
    frozen = svc.freeze_run(inputs, parameters('buffer'))
    with zipfile.ZipFile(BytesIO(frozen['zip'])) as archive:
        manifest = json.loads(archive.read('run_manifest.json'))
        for name, entry in manifest['outputs'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == entry['sha256']
        for name in archive.namelist():
            if name.endswith('.json'):
                json.loads(archive.read(name), parse_constant=lambda value: pytest.fail(value))
        snapshots = json.loads(archive.read('inputs/inputs.json'))
        assert 'unused_date' not in snapshots['sources']['columns']
        assert snapshots['targets']['columns']['value']['values'][0] is None
        archive.extractall(tmp_path)
    completed = subprocess.run([sys.executable, str(tmp_path / 'artifacts/script.py')], cwd=tmp_path,
                               capture_output=True, text=True, timeout=30, check=True)
    assert 'ScriptRunContext' not in completed.stderr
    assert (tmp_path / 'replayed.csv').exists()


def test_multipolygon_buffer():
    from shapely.geometry import MultiPolygon, box
    inputs = svc.demo_inputs()
    inputs['sources'] = gpd.GeoDataFrame({'id': ['parks']},
        geometry=[MultiPolygon([box(0, -5, 30, 5), box(95, -5, 105, 5)])], crs='EPSG:32650')
    assert svc.freeze_run(inputs, parameters('buffer'))['result'].mean_value.tolist() == [20.]


def test_launcher_loopback_and_optional_imports(monkeypatch):
    from types import SimpleNamespace
    from crazy_buffer.gui.launcher import main
    captured = []
    def launch():
        captured.extend(sys.argv)
        return 0
    monkeypatch.setitem(sys.modules, 'streamlit.web', SimpleNamespace(cli=SimpleNamespace(main=launch)))
    monkeypatch.setattr(sys, 'argv', ['crazy-buffer-gui'])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert '--server.address=127.0.0.1' in captured
    assert '--browser.gatherUsageStats=false' in captured
    assert '--server.maxUploadSize=20' in captured
    completed = subprocess.run([sys.executable, '-c',
        'import sys; import crazy_buffer; import crazy_buffer.gui; '
        'assert "streamlit" not in sys.modules; assert "networkx" not in sys.modules'],
        check=True, capture_output=True, text=True, timeout=30)
