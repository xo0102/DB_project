from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Optional, Sequence, Tuple

import folium
from streamlit_folium import st_folium

from config import DEFAULT_ZOOM, RISK_TYPE_LABELS
from services.route_risk_service import RouteRiskAnalysis, RouteRiskItem
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
        popup=f"출발지: {escape(start_name)}<br>{start[0]:.6f}, {start[1]:.6f}",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(m)

    folium.Marker(
        location=list(end),
        tooltip=f"도착지 · {end_name}",
        popup=f"도착지: {escape(end_name)}<br>{end[0]:.6f}, {end[1]:.6f}",
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(m)


def add_route_polyline(
    m: folium.Map,
    route_coordinates: Sequence[MapPoint],
    *,
    color: str = "#2474FF",
    tooltip: str = "TMAP 도보 경로",
    weight: int = 7,
    opacity: float = 0.9,
    dash_array: Optional[str] = None,
    target: Optional[folium.FeatureGroup] = None,
) -> None:
    """TMAP에서 받은 (위도, 경도) 좌표 목록을 지도 위 경로선으로 표시한다."""
    if len(route_coordinates) < 2:
        return

    polyline = folium.PolyLine(
        locations=[list(point) for point in route_coordinates],
        color=color,
        weight=weight,
        opacity=opacity,
        tooltip=tooltip,
        line_cap="round",
        line_join="round",
        dash_array=dash_array,
    )
    polyline.add_to(target or m)


def _risk_item_popup(item: RouteRiskItem) -> str:
    parts = [
        f"<b>{escape(item.title)}</b>",
        f"위험 점수: {item.risk_score}점",
        escape(item.reason),
    ]

    if item.overlap_length_m > 0:
        parts.append(f"실제 교차 길이: 약 {item.overlap_length_m:.1f}m")

    if item.spatial_method:
        parts.append(f"공간 판별: {escape(item.spatial_method)}")

    if item.recent_report:
        parts.append(f"신고 내용: {escape(item.report_description or '설명 없음')}")
        if item.report_created_at:
            parts.append(f"신고 시각: {escape(item.report_created_at)}")
        parts.append(f"누적 신고: {item.duplicate_count}건")

    return "<br>".join(parts)


def add_risk_items_to_map(
    m: folium.Map,
    analysis: Optional[RouteRiskAnalysis],
    *,
    group_name: str = "경로 위험 요소",
) -> None:
    """경로 분석에 포함된 위치 기반 위험 요소를 지도에 표시한다."""
    if not analysis:
        return

    feature_group = folium.FeatureGroup(name=group_name, show=True)
    added = 0

    for item in analysis.spatial_items:
        if item.latitude is None or item.longitude is None:
            continue

        color = "red" if item.recent_report else ("orange" if item.source_type == "road_alert" else "blue")
        radius_m = max(15, item.influence_radius_m)
        popup = _risk_item_popup(item)

        if item.hazard_geojson:
            folium.GeoJson(
                data=item.hazard_geojson,
                name=f"{item.title} Polygon",
                style_function=lambda _feature, polygon_color=color: {
                    "color": polygon_color,
                    "weight": 3,
                    "fillColor": polygon_color,
                    "fillOpacity": 0.22,
                },
                tooltip=f"{item.title} · 실제 교차",
                popup=folium.Popup(popup, max_width=380),
            ).add_to(feature_group)

        folium.Circle(
            location=[item.latitude, item.longitude],
            radius=radius_m,
            color=color,
            fill=True,
            fill_opacity=0.18,
            tooltip=f"{item.title} · {item.risk_score}점",
            popup=folium.Popup(popup, max_width=380),
        ).add_to(feature_group)

        folium.Marker(
            location=[item.latitude, item.longitude],
            tooltip=item.title,
            popup=folium.Popup(popup, max_width=380),
            icon=folium.Icon(color=color, icon="warning-sign"),
        ).add_to(feature_group)
        added += 1

    if added:
        feature_group.add_to(m)


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


def create_route_comparison_map(
    *,
    start: MapPoint,
    end: MapPoint,
    primary_coordinates: Sequence[MapPoint],
    alternative_coordinates: Optional[Sequence[MapPoint]] = None,
    primary_analysis: Optional[RouteRiskAnalysis] = None,
    alternative_analysis: Optional[RouteRiskAnalysis] = None,
    start_name: str = "출발지",
    end_name: str = "도착지",
) -> folium.Map:
    """기본 경로와 위험 회피 대안 경로를 한 지도에 비교 표시한다."""
    primary_points = list(primary_coordinates)
    alternative_points = list(alternative_coordinates or [])
    all_points = [*primary_points, *alternative_points, start, end]
    center_lat = sum(point[0] for point in all_points) / len(all_points)
    center_lng = sum(point[1] for point in all_points) / len(all_points)
    m = create_base_map(center_lat, center_lng)

    primary_group = folium.FeatureGroup(name="기본 TMAP 경로", show=True)
    primary_color = (
        "#EF4444"
        if primary_analysis and primary_analysis.should_offer_alternative
        else "#2474FF"
    )
    add_route_polyline(
        m,
        primary_points,
        color=primary_color,
        tooltip="기본 TMAP 경로",
        target=primary_group,
    )
    primary_group.add_to(m)

    if alternative_points:
        alternative_group = folium.FeatureGroup(name="위험 회피 대안 경로", show=True)
        add_route_polyline(
            m,
            alternative_points,
            color="#16A34A",
            tooltip="위험 회피 대안 경로",
            weight=8,
            target=alternative_group,
        )
        alternative_group.add_to(m)

    # 기본 경로에 실제로 걸린 위험 요소를 표시한다. 대안 경로의 위험은 결과 표에서 별도로 비교한다.
    add_risk_items_to_map(m, primary_analysis)
    add_route_endpoint_markers(m, start, end, start_name=start_name, end_name=end_name)
    fit_map_to_points(m, all_points)
    folium.LayerControl(collapsed=False).add_to(m)
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
