"""Optional, in-memory processing records; never writes files implicitly."""

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class RunReport:
    steps: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_step(self, name, parameters, counts):
        self.steps.append(deepcopy({
            "name": name, "parameters": parameters, "counts": counts,
        }))


def runtime_versions():
    """Report available runtime versions without network or subprocesses."""
    import platform
    from importlib.metadata import PackageNotFoundError, version
    import shapely
    import pyogrio
    import pyproj
    versions = {'python': platform.python_version()}
    for package in ('crazy-buffer', 'pandas', 'geopandas', 'shapely', 'pyogrio', 'pyproj', 'networkx', 'streamlit'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = 'unknown'
    versions.update(GEOS=getattr(shapely, 'geos_version_string', 'unknown'),
                    GDAL=getattr(pyogrio, '__gdal_version_string__', 'unknown'),
                    PROJ=getattr(pyproj, 'proj_version_str', 'unknown'))
    return versions


def source_revision():
    """Read the package source checkout revision, not the caller's working directory.

    A dirty flag distinguishes an installed editable working tree from its HEAD.
    Git absence, timeout, or a source installation outside Git is explicit null.
    """
    from pathlib import Path
    import os
    import subprocess
    result = {'git_commit': None, 'git_dirty': None,
              'git_scope': 'package_source_repository'}
    environment = dict(os.environ)
    # Avoid inherited Git overrides redirecting lookup to an unrelated repository.
    for key in tuple(environment):
        if key.startswith('GIT_'):
            environment.pop(key)
    environment['GIT_OPTIONAL_LOCKS'] = '0'
    kwargs = dict(cwd=Path(__file__).resolve().parent, capture_output=True,
                  text=True, timeout=5, check=True, env=environment)
    try:
        root = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], **kwargs).stdout.strip()).resolve()
        source = Path(__file__).resolve()
        if source != root / 'src' / 'crazy_buffer' / 'provenance.py' or not (root / 'pyproject.toml').is_file():
            return result
        import tomllib
        with (root / 'pyproject.toml').open('rb') as stream:
            project = tomllib.load(stream)
        if project.get('project', {}).get('name', '').replace('_', '-') != 'crazy-buffer':
            return result
        commit = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], **kwargs).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=normal'], **kwargs).stdout
    except (OSError, subprocess.SubprocessError, ValueError):
        return result
    result.update(git_commit=commit or None, git_dirty=bool(dirty))
    return result
