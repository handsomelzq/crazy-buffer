import json
import pandas as pd
from crazy_buffer import RunReport, export_run
from crazy_buffer.provenance import runtime_versions


def test_partial_and_actual_steps(tmp_path):
    report = RunReport(); report.add_step('external_claim', {'filter': 'user described'}, {})
    path = export_run(pd.DataFrame({'id': ['01']}), tmp_path/'run', report=report)
    manifest = json.loads((path/'run_manifest.json').read_text())
    assert manifest['reproducibility'] == 'partial'
    assert set(manifest['missing_artifacts']) == {'inputs', 'script'}
    assert manifest['steps'] == report.steps
    assert 'auto' not in manifest['reproducibility']
    assert set(runtime_versions()) >= {'python', 'geopandas', 'GEOS', 'GDAL', 'PROJ'}


def test_source_revision_readonly(monkeypatch):
    import subprocess
    from crazy_buffer.provenance import source_revision
    calls = []
    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        from pathlib import Path
        value = (str(Path(__file__).resolve().parents[1]) + '\n' if '--show-toplevel' in command
                 else 'abc123\n' if 'rev-parse' in command else ' M src/crazy_buffer/export.py\n')
        return subprocess.CompletedProcess(command, 0, value, '')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    result = source_revision()
    assert result['git_commit'] == 'abc123' and result['git_dirty'] is True
    assert all(kwargs['timeout'] <= 5 for _, kwargs in calls)
    assert result['git_scope'] == 'package_source_repository'


def test_source_revision_git_missing(monkeypatch):
    import subprocess
    from crazy_buffer.provenance import source_revision
    def missing(*args, **kwargs): raise FileNotFoundError('git')
    monkeypatch.setattr(subprocess, 'run', missing)
    result = source_revision()
    assert result['git_commit'] is None and result['git_dirty'] is None


def test_unrelated_ancestor_repository_not_claimed(tmp_path, monkeypatch):
    import subprocess
    from crazy_buffer.provenance import source_revision
    def fake_run(command, **kwargs):
        assert '--show-toplevel' in command
        return subprocess.CompletedProcess(command, 0, str(tmp_path), '')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert source_revision()['git_commit'] is None
