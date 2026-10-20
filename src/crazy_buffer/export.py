"""Explicit, atomic local run export. No code replay is performed."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import tempfile

import geopandas as gpd
import pandas as pd

from .provenance import RunReport, runtime_versions, source_revision


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def _name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*', name) or name in {'.', '..'}:
        raise ValueError('Input name must be a safe single filename component')
    return name


def _gpkg(frame, path):
    if not isinstance(frame, gpd.GeoDataFrame):
        raise TypeError('Spatial snapshots require a GeoDataFrame')
    # GDAL consumes fid as its feature identifier; reject instead of losing an attribute.
    if any(str(column).lower() in {'fid', 'geom'} for column in frame.columns if column != frame.geometry.name):
        raise ValueError('GeoPackage reserved fid/geom attribute cannot be preserved safely')
    frame.to_file(path, driver='GPKG', layer='data', index=False, engine='pyogrio')
    restored = gpd.read_file(path, layer='data', engine='pyogrio')
    if restored.crs != frame.crs:
        raise ValueError('GeoPackage CRS roundtrip changed or lost metadata')
    if restored.geometry.name != frame.geometry.name:
        restored = restored.rename_geometry(frame.geometry.name)
    if len(restored) != len(frame) or set(restored.columns) != set(frame.columns):
        raise ValueError('GeoPackage snapshot changed rows or columns')
    # Drivers may move the active geometry to the end without changing data.
    restored = restored[list(frame.columns)]
    for column in frame.columns:
        if column == frame.geometry.name:
            if not all(a.equals_exact(b, 0) if a is not None and b is not None else a is b
                       for a, b in zip(frame[column], restored[column])):
                raise ValueError('GeoPackage geometry roundtrip is unsafe')
        else:
            try:
                pd.testing.assert_series_equal(frame[column].reset_index(drop=True),
                    restored[column].reset_index(drop=True), check_dtype=False, check_names=False, check_exact=True)
            except (AssertionError, TypeError) as exc:
                raise ValueError(f'GeoPackage attribute roundtrip is unsafe: {column}') from exc


def export_run(results, output_dir, *, report, spatial=None, input_files=None,
               input_frames=None, script_path=None, metadata=None):
    """Save declared artifacts atomically; completeness does not mean verified replay.

    User code is copied, never executed. CSV column dtypes are described in the
    manifest; use them when reading identifiers with leading zeroes.
    """
    if not isinstance(report, RunReport):
        raise TypeError('report must be a RunReport')
    if not isinstance(results, pd.DataFrame) or isinstance(results, gpd.GeoDataFrame):
        raise TypeError('results must be a non-spatial DataFrame')
    output = Path(output_dir).absolute()
    if not output.parent.is_dir():
        raise FileNotFoundError('Output parent directory must already exist')
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    files = dict(input_files or {}); frames = dict(input_frames or {})
    names = [_name(name) for name in [*files, *frames]]
    if len(names) != len(set(names)):
        raise ValueError('Input names must be unique across files and frames')
    # Validate strict JSON before producing any artifacts.
    quality = {'schema_version': 1, 'steps': report.steps, 'issues': report.issues,
               'metadata': {'verification': 'unverified_user_supplied', 'value': report.metadata}}
    user_metadata = {'verification': 'unverified_user_supplied', 'value': metadata or {}}
    json.dumps([quality, user_metadata], allow_nan=False)
    lock = output.parent / f'.{output.name}.lock'
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    lock_identity = os.fstat(descriptor)
    staging = None
    try:
        os.close(descriptor)
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        staging = Path(tempfile.mkdtemp(prefix=f'.{output.name}.staging-', dir=output.parent))
        results.to_csv(staging / 'results.csv', index=False)
        _json(staging / 'quality.json', quality)
        if report.issues:
            pd.DataFrame(report.issues).to_csv(staging / 'issues.csv', index=False)
        if spatial is not None:
            _gpkg(spatial, staging / 'results.gpkg')
        inputs = []
        if files or frames:
            (staging / 'inputs').mkdir()
        for name, source in files.items():
            source = Path(source)
            target = staging / 'inputs' / name
            before = _hash(source)
            shutil.copy2(source, target)
            if _hash(source) != before or _hash(target) != before:
                raise OSError('Input changed during copy or copied hash differs')
            inputs.append({'name': name, 'kind': 'file_copy', 'path': f'inputs/{name}', 'sha256': before})
        for name, frame in frames.items():
            target = staging / 'inputs' / f'{name}.gpkg'
            if target.exists():
                raise ValueError('Input artifact filenames collide')
            _gpkg(frame, target)
            inputs.append({'name': name, 'kind': 'memory_snapshot', 'path': f'inputs/{name}.gpkg', 'sha256': _hash(target),
                           'geometry_column': frame.geometry.name,
                           'column_dtypes': {str(c): str(t) for c, t in frame.dtypes.items()},
                           'crs_wkt': frame.crs.to_wkt() if frame.crs is not None else None})
        script = None
        if script_path is not None:
            source = Path(script_path)
            (staging / 'artifacts').mkdir()
            target = staging / 'artifacts' / ('script' + source.suffix)
            before = _hash(source)
            shutil.copy2(source, target)
            if _hash(source) != before or _hash(target) != before:
                raise OSError('Script changed during copy or copied hash differs')
            script = {'path': str(target.relative_to(staging)), 'sha256': before, 'verification': 'copied_not_executed'}
        missing = ([] if inputs else ['inputs']) + ([] if script else ['script'])
        outputs = {str(p.relative_to(staging)): {'sha256': _hash(p)} for p in sorted(staging.rglob('*')) if p.is_file()}
        outputs['results.csv']['column_dtypes'] = {str(c): str(t) for c, t in results.dtypes.items()}
        manifest = {'schema_version': 1, 'status': 'success',
                    'reproducibility': 'partial' if missing else 'complete',
                    'reproducibility_scope': 'Declared input and script artifacts saved; no automatic replay or code validation',
                    'missing_artifacts': missing, 'inputs': inputs, 'script': script,
                    'steps': report.steps, 'metadata': user_metadata, 'versions': runtime_versions(),
                    **source_revision(), 'outputs': outputs}
        _json(staging / 'run_manifest.json', manifest)
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        os.rename(staging, output)
        staging = None
        return output
    finally:
        if staging is not None:
            shutil.rmtree(staging)
        try:
            current = lock.stat()
            if (current.st_dev, current.st_ino) == (lock_identity.st_dev, lock_identity.st_ino):
                lock.unlink()
        except FileNotFoundError:
            pass
