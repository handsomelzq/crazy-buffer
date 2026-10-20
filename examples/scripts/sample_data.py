"""CC0 synthetic fixtures; Cartesian metre coordinates, not real locations."""
import geopandas as gpd
from shapely.geometry import Point, box


def park_prices():
    parks = gpd.GeoDataFrame({'id': ['P1', 'P2']},
        geometry=[box(0, 0, 10, 10), box(100, 100, 110, 110)], crs='EPSG:32650')
    homes = gpd.GeoDataFrame({'id': ['H1', 'H2', 'H3'], 'price': [10000., 30000., 90000.]},
        geometry=[Point(5, 5), Point(15, 5), Point(30, 5)], crs=parks.crs)
    return parks, homes


def nearest_station():
    homes = gpd.GeoDataFrame({'id': ['001', '002']},
        geometry=[Point(0, 0), Point(3, 4)], crs='EPSG:32650')
    stations = gpd.GeoDataFrame({'id': ['B', 'A']},
        geometry=[Point(3, 4), Point(-3, 4)], crs=homes.crs)
    return homes, stations
