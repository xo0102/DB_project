from __future__ import annotations

import streamlit as st

from config import DEFAULT_LAT, DEFAULT_LNG
from utils.geo_utils import distance_meters


def render_route_demo() -> None:
    st.header("경로 검색 데모")
    st.write(
        "이번 기본틀에서는 실제 TMAP API를 호출하지 않고, "
        "출발지/도착지 좌표 입력 화면과 추후 구현 예정 흐름만 제공합니다."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 출발지")
        start_lat = st.number_input("출발지 위도", value=DEFAULT_LAT, format="%.6f")
        start_lng = st.number_input("출발지 경도", value=DEFAULT_LNG, format="%.6f")

    with col2:
        st.markdown("### 도착지")
        end_lat = st.number_input("도착지 위도", value=DEFAULT_LAT + 0.003, format="%.6f")
        end_lng = st.number_input("도착지 경도", value=DEFAULT_LNG + 0.003, format="%.6f")

    if st.button("경로 검색 데모 확인"):
        direct_distance = distance_meters(start_lat, start_lng, end_lat, end_lng)
        st.success("입력 UI 확인이 완료되었습니다. 실제 경로 탐색은 추후 단계에서 구현합니다.")
        st.write(f"참고용 직선거리: 약 {direct_distance:.1f}m")

    st.markdown("### 추후 연결할 테이블")
    st.markdown(
        """
        - `route_search_logs`: 사용자의 경로 검색 요청 저장
        - `route_results`: 경로 후보별 거리, 시간, 총 위험 점수 저장
        - `route_risk_details`: 경로별 위험 근거 상세 저장
        """
    )

    st.info("외부 API 연동, 실제 경로 추천, PostGIS 공간 연산은 이번 단계에서는 구현하지 않습니다.")
