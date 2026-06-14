from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import streamlit as st

from config import DEFAULT_LAT, DEFAULT_LNG


def init_point_state(prefix: str, lat: float = DEFAULT_LAT, lng: float = DEFAULT_LNG) -> None:
    """지도 클릭 위치를 session_state에 초기화한다."""
    lat_key = f"{prefix}_lat"
    lng_key = f"{prefix}_lng"

    if lat_key not in st.session_state:
        st.session_state[lat_key] = lat
    if lng_key not in st.session_state:
        st.session_state[lng_key] = lng


def get_clicked_point(map_data: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float]]:
    """st_folium이 반환한 데이터에서 마지막 클릭 좌표를 추출한다."""
    if not map_data:
        return None

    clicked = map_data.get("last_clicked") or map_data.get("last_object_clicked")
    if not clicked:
        return None

    lat = clicked.get("lat")
    lng = clicked.get("lng")

    if lat is None or lng is None:
        return None

    return float(lat), float(lng)


def update_point_state_from_map(prefix: str, map_data: Optional[Dict[str, Any]]) -> None:
    """지도 클릭 좌표가 있으면 session_state에 반영하고 화면을 다시 그린다."""
    point = get_clicked_point(map_data)
    if not point:
        return

    lat, lng = point
    lat_key = f"{prefix}_lat"
    lng_key = f"{prefix}_lng"

    old_lat = st.session_state.get(lat_key)
    old_lng = st.session_state.get(lng_key)

    if old_lat != lat or old_lng != lng:
        st.session_state[lat_key] = lat
        st.session_state[lng_key] = lng
        st.rerun()
