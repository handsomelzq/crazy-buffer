import geopandas as gpd
import pytest
from shapely.geometry import Point


@pytest.fixture
def metric_points():
    return gpd.GeoDataFrame(
        {"id": ["a", "b"], "value": [10, 20]},
        geometry=[Point(500000, 4400000), Point(500010, 4400000)],
        crs="EPSG:32650",
    )
