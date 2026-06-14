from __future__ import annotations

import streamlit as st

from components.map_components import add_report_zones_to_map, add_selected_marker, create_base_map, render_folium_map
from db.client import has_supabase, show_supabase_warning
from db.queries import get_active_risk_zones
from services.risk_service import calculate_simple_risk
from utils.formatters import format_error_message
from utils.state_utils import init_point_state, update_point_state_from_map


def render_simple_risk_calculator(client) -> None:
    st.header("간단 위험도 계산")
    st.write(
        "지도에서 선택한 위치를 기준으로 신고 기반 위험 구역, 침수 이력 구역, 최신 날씨 위험 점수를 단순 합산합니다."
    )

    if not has_supabase(client):
        show_supabase_warning()
        return

    init_point_state("calc")

    lat = st.session_state["calc_lat"]
    lng = st.session_state["calc_lng"]

    m = create_base_map(lat, lng)
    add_selected_marker(m, lat, lng, popup="위험도 계산 위치")

    try:
        zones = get_active_risk_zones(client)
        add_report_zones_to_map(m, zones)
    except Exception as e:
        st.caption(f"활성 위험 구역을 불러오지 못했습니다: {format_error_message(e)}")

    map_data = render_folium_map(m, key="calc_map")
    update_point_state_from_map("calc", map_data)

    st.success(f"선택된 위치: {lat:.6f}, {lng:.6f}")

    score, reasons = calculate_simple_risk(client, lat, lng)
    st.metric("위험도 점수", f"{score}/100")

    if reasons:
        st.markdown("### 계산 근거")
        for reason in reasons:
            st.write(f"- {reason}")
    else:
        st.info("현재 반영된 위험 요소가 없습니다.")
