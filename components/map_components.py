from __future__ import annotations

from typing import Any, Dict, List, Optional

import folium
from streamlit_folium import st_folium

from config import DEFAULT_ZOOM, RISK_TYPE_LABELS
from utils.formatters import to_float, to_int


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


def render_folium_map(m: folium.Map, key: str, height: int = 520) -> Optional[Dict[str, Any]]:
    return st_folium(
        m,
        width=None,
        height=height,
        key=key,
    )
