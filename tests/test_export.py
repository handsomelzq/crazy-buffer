import json
import shutil
import geopandas as gpd
import pandas as pd
import pytest
from crazy_buffer import export_run, RunReport


def test_export_complete(tmp_path, metric_points):
    source = tmp_path / 'source.txt'; source.write_text('input')
    script = tmp_path / 'analysis.py'; script.write_text('# explicit user script')
    report = RunReport(issues=[{'id': '001', 'reason': 'example'}])
    report.add_step('actual', {}, {'rows': 2})
    out = export_run(pd.DataFrame({'id': ['001']}), tmp_path / 'run', report=report,
                     spatial=metric_points, input_files={'source': source},
                     input_frames={'points': metric_points}, script_path=script,
                     metadata={'units': 'user claim'})
    manifest = json.loads((out / 'run_manifest.json').read_text())
    assert manifest['reproducibility'] == 'complete'
    assert manifest['metadata']['verification'] == 'unverified_user_supplied'
    assert 'run_manifest.json' not in manifest['outputs']
    assert pd.read_csv(out / 'results.csv', dtype={'id': str}).id[0] == '001'
    assert len(gpd.read_file(out / 'results.gpkg')) == 2
    assert (out / 'quality.json').exists() and (out / 'issues.csv').exists()
    with pytest.raises(FileExistsError):
        export_run(pd.DataFrame(), out, report=report)


def test_failure_cleanup(tmp_path, metric_points, monkeypatch):
    def fail(*args, **kwargs): raise OSError('injected')
    monkeypatch.setattr(gpd.GeoDataFrame, 'to_file', fail)
    with pytest.raises(OSError):
        export_run(pd.DataFrame(), tmp_path / 'run', report=RunReport(), spatial=metric_points)
    assert list(tmp_path.iterdir()) == []


def test_copy_failure_and_reserved_fid(tmp_path, metric_points, monkeypatch):
    source = tmp_path / 'source'; source.write_text('untouched')
    monkeypatch.setattr(shutil, 'copy2', lambda *a, **k: (_ for _ in ()).throw(OSError('copy')))
    with pytest.raises(OSError):
        export_run(pd.DataFrame(), tmp_path/'run', report=RunReport(), input_files={'x': source})
    assert list(tmp_path.iterdir()) == [source]
    points = metric_points.assign(fid=['user-a', 'user-b'])
    with pytest.raises(ValueError, match='fid'):
        export_run(pd.DataFrame(), tmp_path/'run', report=RunReport(), input_frames={'x': points})


def test_strict_json_and_lock(tmp_path):
    lock = tmp_path / '.run.lock'; lock.write_text('competitor')
    with pytest.raises(FileExistsError):
        export_run(pd.DataFrame(), tmp_path/'run', report=RunReport())
    assert lock.read_text() == 'competitor'
    lock.unlink()
    with pytest.raises(ValueError):
        export_run(pd.DataFrame(), tmp_path/'run', report=RunReport(issues=[{'x': float('nan')}]))
    assert list(tmp_path.iterdir()) == []


def test_concurrent_export_and_hashes(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import hashlib
    entered = Event(); release = Event()
    original = pd.DataFrame.to_csv
    def paused(self, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(pd.DataFrame, 'to_csv', paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(export_run, pd.DataFrame({'id':['001']}), tmp_path/'run', report=RunReport())
        assert entered.wait(5)
        try:
            with pytest.raises(FileExistsError):
                export_run(pd.DataFrame(), tmp_path/'run', report=RunReport())
        finally:
            release.set()
        out = first.result(timeout=5)
    manifest = json.loads((out/'run_manifest.json').read_text())
    for relative, detail in manifest['outputs'].items():
        assert hashlib.sha256((out/relative).read_bytes()).hexdigest() == detail['sha256']
    assert list(tmp_path.iterdir()) == [out]


def test_custom_geometry_column_schema(tmp_path, metric_points):
    points = metric_points.rename_geometry('location')
    out = export_run(pd.DataFrame({'id':['001']}), tmp_path/'run', report=RunReport(),
                     input_frames={'points':points}, spatial=points)
    manifest = json.loads((out/'run_manifest.json').read_text())
    entry = manifest['inputs'][0]
    assert entry['geometry_column'] == 'location'
    assert entry['column_dtypes']['id'] == 'object'
    assert points.geometry.name == 'location'
    assert (out/'results.csv').exists() and (out/'results.gpkg').exists()


def test_crs_roundtrip_loss_rejected(tmp_path, metric_points, monkeypatch):
    original = gpd.read_file
    def lost(*args, **kwargs):
        return original(*args, **kwargs).set_crs(None, allow_override=True)
    monkeypatch.setattr(gpd, 'read_file', lost)
    with pytest.raises(ValueError, match='CRS'):
        export_run(pd.DataFrame(), tmp_path/'run', report=RunReport(), input_frames={'points':metric_points})
    assert list(tmp_path.iterdir()) == []


def test_snapshot_float_changes_rejected(tmp_path, metric_points, monkeypatch):
    points = metric_points.assign(value=[1.0, 2.0])
    original = gpd.read_file
    def altered(*args, **kwargs):
        frame = original(*args, **kwargs)
        frame.loc[0,'value'] += 1e-9
        return frame
    monkeypatch.setattr(gpd, 'read_file', altered)
    with pytest.raises(ValueError, match='attribute'):
        export_run(pd.DataFrame(), tmp_path/'run', report=RunReport(), input_frames={'points':points})


def test_geometry_not_last_roundtrip(tmp_path, metric_points):
    points = metric_points.assign(value=[1., 2.])[['id', 'geometry', 'value']]
    assert points.columns[-1] == 'value'
    out = export_run(pd.DataFrame({'ok': [True]}), tmp_path/'run', report=RunReport(),
                     input_frames={'points': points}, spatial=points)
    restored = gpd.read_file(out/'inputs/points.gpkg', layer='data')
    assert restored['value'].tolist() == [1., 2.]
    assert restored.geometry.geom_equals(points.geometry).all()
