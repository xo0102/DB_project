from __future__ import annotations

import streamlit as st

from db.client import has_supabase, show_supabase_warning
from utils.secret_utils import read_secret


def render_home(client) -> None:
    st.header("홈")
    st.subheader("비 오는 날 야간 도보 이동을 위한 도시 위험 경로 안내 프로젝트")

    st.write(
        "침수 위험 구역, 도로 통제 정보, 날씨 정보, 사용자 신고 데이터를 활용하여 "
        "단순 최단 경로가 아니라 위험 근거를 설명하는 보행 경로를 제공하는 Streamlit + Supabase 프로젝트입니다."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 현재 구현된 기능")
        st.markdown(
            """
            - Supabase 연결 및 회원 인증
            - 사용자 위험 신고 저장 및 활성 위험 구역 생성
            - Folium 기반 위험 지도와 간단 위험도 계산
            - TMAP 보행자 경로 API 연동
            - 지도 클릭 기반 출발지·도착지 선택
            - 실제 도보 경로 PolyLine 시각화
            - **경로별 침수·도로 통제·최근 신고 위험 분석**
            - **50점 이상 또는 최근 신고 포함 시 우회 경로 탐색**
            - **경로에 포함된 신고 내용과 위험 근거 표시**
            - **경로 검색 로그·추천 경로·위험 상세 DB 저장**
            - **경로 좌표를 표준 GeoJSON LineString으로 저장**
            """
        )

    with col2:
        st.markdown("### 다음 구현 단계")
        st.markdown(
            """
            - PostGIS 공간 자료형 도입
            - 저장된 GeoJSON 경로를 PostGIS LineString으로 변환
            - 경로 LineString과 침수 Polygon의 정확한 교차 판별
            - 기상청 API 실시간 연동
            """
        )

    st.markdown("### 연동 상태")
    status_col1, status_col2 = st.columns(2)

    with status_col1:
        if has_supabase(client):
            st.success("Supabase 연결 정보가 설정되어 있습니다.")
        else:
            show_supabase_warning()
            client_error = st.session_state.get("supabase_client_error")
            if client_error:
                st.caption(f"클라이언트 생성 오류: {client_error}")

    with status_col2:
        if read_secret("TMAP_APP_KEY"):
            st.success("TMAP appKey가 설정되어 있습니다.")
        else:
            st.warning("TMAP_APP_KEY가 아직 설정되지 않았습니다.")

    st.info(
        "로그인 상태의 경로 검색 결과는 세 경로 테이블에 자동 저장됩니다. "
        "현재는 중심 좌표와 반경으로 위험을 근사 분석하며, 다음 단계에서 PostGIS로 실제 공간 교차 여부를 정밀 분석합니다."
    )
