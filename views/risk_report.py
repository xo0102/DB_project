from __future__ import annotations

import streamlit as st

from components.map_components import add_report_zones_to_map, add_selected_marker, create_base_map, render_folium_map
from config import RISK_TYPE_LABELS
from db.client import has_supabase, show_supabase_warning
from db.queries import get_active_risk_zones
from services.auth_service import get_logged_in_user_id, is_logged_in
from services.risk_service import submit_report
from utils.formatters import format_error_message
from utils.state_utils import init_point_state, update_point_state_from_map


def render_risk_report(client) -> None:
    st.header("위험 신고")
    st.write("로그인한 사용자가 지도에서 위치를 선택하고 위험 정보를 신고하는 기본 화면입니다.")

    if not has_supabase(client):
        show_supabase_warning()
        return

    if not is_logged_in():
        st.warning("위험 신고는 로그인 후 사용할 수 있습니다. 먼저 로그인 메뉴에서 로그인해주세요.")
        return

    init_point_state("report")

    risk_type = st.selectbox(
        "위험 유형",
        options=list(RISK_TYPE_LABELS.keys()),
        format_func=lambda key: f"{key} - {RISK_TYPE_LABELS[key]}",
    )
    description = st.text_area(
        "설명",
        placeholder="예: 보도블록 위에 물이 고여 있어서 통행이 어렵습니다.",
        height=100,
    )

    st.write("지도에서 신고 위치를 클릭하세요.")

    lat = st.session_state["report_lat"]
    lng = st.session_state["report_lng"]

    m = create_base_map(lat, lng)
    add_selected_marker(m, lat, lng, popup="신고 위치")

    try:
        zones = get_active_risk_zones(client)
        add_report_zones_to_map(m, zones)
    except Exception as e:
        st.caption(f"활성 위험 구역을 불러오지 못했습니다: {format_error_message(e)}")

    map_data = render_folium_map(m, key="report_map")
    update_point_state_from_map("report", map_data)

    st.success(f"선택된 신고 위치: {lat:.6f}, {lng:.6f}")

    if st.button("위험 신고하기", type="primary"):
        ok, message = submit_report(
            client=client,
            user_id=get_logged_in_user_id(),
            risk_type=risk_type,
            lat=lat,
            lng=lng,
            description=description,
        )
        if ok:
            st.success(message)
        else:
            st.warning(message)
