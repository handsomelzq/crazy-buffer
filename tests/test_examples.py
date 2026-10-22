import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import geopandas as gpd
import nbformat
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    'name', ['park_prices', 'nearest_station', 'facility_mix', 'land_use_mix'],
)
def test_example_and_snapshot_replay(name, tmp_path):
    path = ROOT / 'examples' / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.main(tmp_path / name)
    result = pd.read_csv(out / 'results.csv')
    if name == 'park_prices':
        assert result.loc[0, 'mean_value'] == 20000.0
    elif name == 'nearest_station':
        assert result.loc[0, 'target_id'] == 'A'
        assert result.loc[0, 'distance_m'] == 5.0
    elif name == 'facility_mix':
        assert result.loc[0, 'count_餐饮'] == 2
        assert result.loc[0, 'count_商业'] == 1
    else:
        assert result.loc[0, 'share_居住'] == pytest.approx(0.6)
        assert result.loc[0, 'share_绿地'] == pytest.approx(0.2)
    manifest = json.loads((out / 'run_manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'success'
    assert manifest['reproducibility'] == 'complete'
    assert len(gpd.read_file(out / 'results.gpkg', layer='data')) == len(result)
    for item in manifest['inputs']:
        assert len(gpd.read_file(out / item['path'], layer='data')) > 0
    replay = tmp_path / f'{name}-replay'
    subprocess.run([sys.executable, str(out / 'artifacts' / 'script.py'), str(replay)],
                   cwd=tmp_path, check=True, timeout=30,
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
    pd.testing.assert_frame_equal(result, pd.read_csv(replay / 'results.csv'))


@pytest.mark.parametrize('name', ['park_prices', 'nearest_station'])
def test_notebook_structure_only(name):
    notebook = nbformat.read(ROOT / 'examples' / 'notebooks' / f'{name}.ipynb', as_version=4)
    nbformat.validate(notebook)
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            assert cell.execution_count is None
            assert cell.outputs == []
            ast.parse('\n'.join(line for line in cell.source.splitlines()
                                if not line.lstrip().startswith(('%', '!'))))
