from __future__ import annotations

import streamlit as st

from components.map_components import add_report_zones_to_map, add_selected_marker, create_base_map, render_folium_map
from db.client import has_supabase, show_supabase_warning
from db.queries import get_active_risk_zones
from utils.formatters import format_error_message
from utils.state_utils import init_point_state, update_point_state_from_map


def render_risk_map(client) -> None:
    st.header("위험 지도")
    st.write("report_risk_zones 테이블에 저장된 활성 위험 구역을 지도에 원 형태로 표시합니다.")

    if not has_supabase(client):
        show_supabase_warning()
        return

    init_point_state("map")

    col1, col2 = st.columns(2)
    with col1:
        center_lat = st.number_input(
            "지도 중심 위도",
            value=float(st.session_state["map_lat"]),
            format="%.6f",
        )
    with col2:
        center_lng = st.number_input(
            "지도 중심 경도",
            value=float(st.session_state["map_lng"]),
            format="%.6f",
        )

    st.session_state["map_lat"] = center_lat
    st.session_state["map_lng"] = center_lng

    try:
        zones = get_active_risk_zones(client)
    except Exception as e:
        zones = []
        st.error(f"위험 구역 조회 중 오류가 발생했습니다: {format_error_message(e)}")

    m = create_base_map(center_lat, center_lng)
    add_selected_marker(m, center_lat, center_lng, popup="지도 중심")
    add_report_zones_to_map(m, zones)

    map_data = render_folium_map(m, key="risk_map")
    update_point_state_from_map("map", map_data)

    st.caption(f"현재 표시 가능한 활성 위험 구역: {len(zones)}개")

    if zones:
        with st.expander("활성 위험 구역 데이터 보기"):
            st.dataframe(zones, use_container_width=True)
    else:
        st.info("현재 표시할 활성 위험 구역이 없습니다.")
