from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import folium
from streamlit_folium import st_folium

from config import DEFAULT_ZOOM, RISK_TYPE_LABELS
from utils.formatters import to_float, to_int

MapPoint = Tuple[float, float]


def create_base_map(lat: float, lng: float, zoom: int = DEFAULT_ZOOM) -> folium.Map:
    return folium.Map(location=[lat, lng], zoom_start=zoom, tiles="OpenStreetMap")


def add_selected_marker(m: folium.Map, lat: float, lng: float, popup: str = "선택 위치") -> None:
    folium.Marker(
        [lat, lng],
        popup=popup,
        tooltip=popup,
        icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(m)


def add_report_zones_to_map(m: folium.Map, zones: List[Dict[str, Any]]) -> None:
    for zone in zones:
        lat = to_float(zone.get("center_lat"))
        lng = to_float(zone.get("center_lng"))
        radius_m = to_int(zone.get("radius_m"), 50)
        risk_score = to_int(zone.get("risk_score"), 0)
        risk_type = zone.get("risk_type", "unknown")
        risk_label = RISK_TYPE_LABELS.get(risk_type, risk_type)

        folium.Circle(
            location=[lat, lng],
            radius=radius_m,
            popup=f"{risk_label} / 위험점수 {risk_score}",
            tooltip=f"{risk_label} ({risk_score}점)",
            color="red",
            fill=True,
            fill_opacity=0.25,
        ).add_to(m)


def add_route_endpoint_markers(
    m: folium.Map,
    start: MapPoint,
    end: MapPoint,
    start_name: str = "출발지",
    end_name: str = "도착지",
) -> None:
    """경로 지도에 출발지와 도착지 마커를 구분해서 표시한다."""
    folium.Marker(
        location=list(start),
        tooltip=f"출발지 · {start_name}",
        popup=f"출발지: {start_name}<br>{start[0]:.6f}, {start[1]:.6f}",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(m)

    folium.Marker(
        location=list(end),
        tooltip=f"도착지 · {end_name}",
        popup=f"도착지: {end_name}<br>{end[0]:.6f}, {end[1]:.6f}",
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(m)


def add_route_polyline(
    m: folium.Map,
    route_coordinates: Sequence[MapPoint],
) -> None:
    """TMAP에서 받은 (위도, 경도) 좌표 목록을 지도 위 경로선으로 표시한다."""
    if len(route_coordinates) < 2:
        return

    folium.PolyLine(
        locations=[list(point) for point in route_coordinates],
        color="#2474FF",
        weight=7,
        opacity=0.9,
        tooltip="TMAP 도보 경로",
        line_cap="round",
        line_join="round",
    ).add_to(m)


def fit_map_to_points(
    m: folium.Map,
    points: Sequence[MapPoint],
    padding: Tuple[int, int] = (40, 40),
) -> None:
    """주어진 좌표들이 한 화면에 보이도록 지도 범위를 맞춘다."""
    valid_points = [
        [float(lat), float(lng)]
        for lat, lng in points
        if -90 <= float(lat) <= 90 and -180 <= float(lng) <= 180
    ]

    if len(valid_points) >= 2:
        min_lat = min(point[0] for point in valid_points)
        max_lat = max(point[0] for point in valid_points)
        min_lng = min(point[1] for point in valid_points)
        max_lng = max(point[1] for point in valid_points)
        m.fit_bounds(
            [[min_lat, min_lng], [max_lat, max_lng]],
            padding=padding,
            max_zoom=18,
        )


def create_route_selection_map(
    start: MapPoint,
    end: MapPoint,
    route_coordinates: Optional[Sequence[MapPoint]] = None,
    start_name: str = "출발지",
    end_name: str = "도착지",
) -> folium.Map:
    """
    출발지·도착지 선택과 TMAP 경로 표시를 함께 사용하는 지도를 생성한다.

    경로가 있으면 경로 전체가 보이도록 맞추고, 없으면 두 지점이 보이도록 맞춘다.
    """
    route_points = list(route_coordinates or [])
    points_for_view: Sequence[MapPoint] = [*route_points, start, end] if route_points else [start, end]
    center_lat = sum(point[0] for point in points_for_view) / len(points_for_view)
    center_lng = sum(point[1] for point in points_for_view) / len(points_for_view)

    m = create_base_map(center_lat, center_lng)

    if route_points:
        add_route_polyline(m, route_points)

    add_route_endpoint_markers(m, start, end, start_name=start_name, end_name=end_name)
    fit_map_to_points(m, points_for_view)
    return m


def render_folium_map(
    m: folium.Map,
    key: str,
    height: int = 520,
    returned_objects: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    return st_folium(
        m,
        width=None,
        height=height,
        key=key,
        returned_objects=returned_objects,
    )
