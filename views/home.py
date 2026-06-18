from __future__ import annotations

import streamlit as st

from db.client import has_supabase, show_supabase_warning
from utils.secret_utils import read_secret


def render_home(client) -> None:
    st.header("홈")
    st.subheader("비 오는 날 야간 도보 이동을 위한 도시 위험 경로 안내 프로젝트")

    st.write(
        "침수 위험 구역, 도로 통제 정보, 날씨 정보, 사용자 신고 데이터를 활용하여 "
        "안전한 보행 경로 안내 기능으로 확장하는 Streamlit + Supabase 프로젝트입니다."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 현재 구현된 기능")
        st.markdown(
            """
            - Supabase 연결 및 회원 인증
            - 사용자 위험 신고 저장
            - 신고 기반 위험 구역 생성
            - Folium 기반 위험 지도 표시
            - 선택 위치 기준 간단 위험도 계산
            - 주요 DB 테이블 조회
            - **TMAP 보행자 경로 API 연동**
            - 실제 보행 거리·시간·경로 좌표 수신
            """
        )

    with col2:
        st.markdown("### 다음 구현 단계")
        st.markdown(
            """
            - TMAP 경로를 지도에 PolyLine으로 표시
            - 경로 검색 결과를 Supabase에 저장
            - PostGIS 공간 자료형 도입
            - 경로 LineString과 침수 Polygon 교차 판별
            - 경로 위험도 계산 및 안전 경로 추천
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
        "현재는 API에서 실제 보행 경로 데이터를 받아오는 1단계입니다. "
        "지도 경로 시각화와 PostGIS 위험 분석은 다음 커밋에서 차례대로 추가합니다."
    )
