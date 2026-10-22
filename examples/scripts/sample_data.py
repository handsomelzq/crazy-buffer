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


def facility_mix():
    sources = gpd.GeoDataFrame(
        {"id": ["community-1", "community-2"]},
        geometry=[Point(0, 0), Point(100, 0)],
        crs="EPSG:32650",
    )
    facilities = gpd.GeoDataFrame(
        {
            "id": ["food-1", "food-2", "shop-1", "school-1"],
            "type": ["餐饮", "餐饮", "商业", "教育"],
        },
        geometry=[
            Point(3, 4), Point(6, 8), Point(10, 0), Point(106, 8),
        ],
        crs=sources.crs,
    )
    return sources, facilities


def land_use_mix():
    communities = gpd.GeoDataFrame(
        {"id": ["community-1", "community-2"]},
        geometry=[box(0, 0, 10, 10), box(20, 0, 30, 10)],
        crs="EPSG:32650",
    )
    parcels = gpd.GeoDataFrame(
        {
            "id": ["residential-1", "green-1", "residential-2", "commercial-1"],
            "use": ["居住", "绿地", "居住", "商业"],
        },
        geometry=[
            box(0, 0, 6, 10),
            box(6, 0, 10, 5),
            box(20, 0, 28, 10),
            box(28, 0, 30, 6),
        ],
        crs=communities.crs,
    )
    return communities, parcels
