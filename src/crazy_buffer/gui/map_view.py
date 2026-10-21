"""Small, read-only map previews; these never substitute for analysis inputs."""

import math

import geopandas as gpd
import numpy as np
import pydeck as pdk
from shapely import get_coordinates
from shapely.geometry import mapping

from crazy_buffer.validate import _metric_crs

MAX_PREVIEW_FEATURES = 2000
ROLE_LABELS = {"sources": "研究对象", "targets": "目标数据", "edges": "道路"}
ROLE_COLORS = {
    "sources": [37, 115, 99, 200],
    "targets": [210, 137, 65, 210],
    "edges": [91, 109, 125, 180],
    "buffer": [37, 115, 99, 35],
}
# Streamlit's frontend requires a URL string even though pydeck accepts dicts.
# CARTO's public style retains OpenStreetMap/CARTO attribution in its sources.
BASEMAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
# Streamlit >=1.66 treats None as a request for its default CARTO basemap.
# This sentinel removes mapStyle while explicitly suppressing that fallback.
NO_BASEMAP_STYLE = "__MAP_STYLE__"


def _usable(geometry, *, geographic=False):
    if geometry is None or geometry.is_empty or not geometry.is_valid:
        return False
    if geometry.geom_type not in {
        "Point", "MultiPoint", "LineString", "MultiLineString",
        "Polygon", "MultiPolygon",
    }:
        return False
    coordinates = get_coordinates(geometry)
    if not len(coordinates) or not np.isfinite(coordinates).all():
        return False
    if geographic:
        # The basemap uses Web Mercator and cannot show the poles.
        return bool(
            (np.abs(coordinates[:, 0]) <= 180).all()
            and (np.abs(coordinates[:, 1]) <= 85.05112878).all()
        )
    return True


def _preview_frame(frame, role, messages):
    label = ROLE_LABELS.get(role, role)
    if not isinstance(frame, gpd.GeoDataFrame) or frame.active_geometry_name is None:
        messages.append(f"{label}尚未提供可显示的空间几何。")
        return None
    if frame.crs is None:
        messages.append(f"{label}缺少原始 CRS，暂不能定位到地图。")
        return None
    selected = frame.iloc[:MAX_PREVIEW_FEATURES].copy()
    if len(frame) > MAX_PREVIEW_FEATURES:
        messages.append(
            f"{label}共 {len(frame)} 条，地图仅预览前 {MAX_PREVIEW_FEATURES} 条；计算仍使用完整输入。"
        )
    valid = selected.geometry.map(_usable)
    if (~valid).sum():
        messages.append(f"{label}有 {int((~valid).sum())} 条空、无效或非有限几何，已从地图预览中跳过。")
    return selected.loc[valid].copy()


def _geographic(frame, label, messages):
    try:
        geographic = frame.to_crs("EPSG:4326")
    except Exception:
        messages.append(f"{label}无法转换到地图坐标，请检查原始 CRS。")
        return None
    valid = geographic.geometry.map(lambda geometry: _usable(geometry, geographic=True))
    if (~valid).sum():
        messages.append(f"{label}有 {int((~valid).sum())} 条坐标超出地图范围或投影无效，已跳过。")
    return geographic.loc[valid].copy()


def _layer(frame, role, id_column):
    label = ROLE_LABELS.get(role, "缓冲范围")
    features = []
    for position in range(len(frame)):
        identifier = str(frame[id_column].iloc[position]) if id_column in frame.columns else str(position + 1)
        features.append({
            "type": "Feature",
            "geometry": mapping(frame.geometry.iloc[position]),
            "properties": {"label": label, "identifier": identifier},
        })
    return pdk.Layer(
        "GeoJsonLayer",
        id=f"preview-{role}",
        data={"type": "FeatureCollection", "features": features},
        pickable=True,
        stroked=True,
        filled=True,
        get_fill_color=ROLE_COLORS[role],
        get_line_color=ROLE_COLORS[role][:3] + [180],
        get_line_width=2 if role == "edges" else 1,
        line_width_units=pdk.types.String("pixels"),
        line_width_min_pixels=1,
        get_point_radius=6 if role == "sources" else 4,
        point_radius_units=pdk.types.String("pixels"),
        point_radius_min_pixels=3,
    )


def _view(bounds):
    if not bounds:
        return pdk.ViewState(longitude=116.40, latitude=39.90, zoom=10, pitch=0)
    all_bounds = np.array(bounds)
    west, south = all_bounds[:, :2].min(axis=0)
    east, north = all_bounds[:, 2:].max(axis=0)
    mercator = lambda latitude: math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
    low, high = mercator(south), mercator(north)
    latitude = math.degrees(2 * math.atan(math.exp((low + high) / 2)) - math.pi / 2)
    x_span = max((east - west) / 360, 1e-8)
    y_span = max((high - low) / (2 * math.pi), 1e-8)
    # Fit a conservative 640 x 480 viewport with room for feature edges.
    zoom = min(math.log2(640 / (512 * x_span)), math.log2(480 / (512 * y_span))) - 0.6
    return pdk.ViewState(
        longitude=float((west + east) / 2), latitude=float(latitude),
        zoom=float(max(0, min(16, zoom))), pitch=0,
    )


def build_map(inputs, params, *, visible_roles=None, show_buffer=True, basemap=True):
    """Return a pydeck map and Chinese preview notices without mutating inputs.

    ``visible_roles`` is a collection of sources/targets/edges; None shows all
    supplied roles. Only selected ID strings are sent as feature attributes.
    Buffers use the same validated metre CRS requirement as the analysis API.
    """
    messages, layers, bounds = [], [], []
    visible = set(inputs) if visible_roles is None else set(visible_roles)
    source_preview = None
    for role in ("edges", "sources", "targets"):
        if role not in visible or role not in inputs:
            continue
        selected = _preview_frame(inputs[role], role, messages)
        if selected is None or selected.empty:
            continue
        if role == "sources":
            source_preview = selected
        geographic = _geographic(selected, ROLE_LABELS[role], messages)
        if geographic is None or geographic.empty:
            continue
        layers.append(_layer(geographic, role, params.get(role + "_id")))
        bounds.append(geographic.total_bounds)
    if show_buffer and params.get("task") == "buffer" and source_preview is not None:
        try:
            radius = float(params.get("radius_m", 0))
            if not math.isfinite(radius) or radius <= 0:
                raise ValueError("positive radius required")
            metric = source_preview.to_crs(_metric_crs(params.get("analysis_crs")))
            # Match make_buffers(); buffer_stats itself uses exact distances.
            metric.geometry = metric.geometry.buffer(radius, quad_segs=32)
            geographic = _geographic(metric, "缓冲范围", messages)
            if geographic is not None and not geographic.empty:
                layers.insert(0, _layer(geographic, "buffer", params.get("sources_id")))
                bounds.append(geographic.total_bounds)
        except Exception:
            messages.append("缓冲范围暂未预览：请设置有效的正数半径和本地米制分析 CRS（不支持经纬度或 Web Mercator）。")
    return pdk.Deck(
        layers=layers, initial_view_state=_view(bounds),
        map_style=BASEMAP_STYLE if basemap else NO_BASEMAP_STYLE,
        map_provider="carto" if basemap else None,
        tooltip={"text": "{properties.label}\nID：{properties.identifier}"},
        height=580,
    ), messages
