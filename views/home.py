from __future__ import annotations

import streamlit as st

from db.client import has_supabase, show_supabase_warning
from services.spatial_service import SpatialAnalysisError, get_postgis_status
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
            - **경로 검색 요청·추천 결과·위험 근거를 Supabase에 저장**
            - **경로 좌표를 GeoJSON LineString과 PostGIS LineString으로 저장**
            - **PostGIS ST_Intersects 기반 침수 Polygon 실제 교차 분석**
            - **ST_DWithin 기반 신고·도로 알림 반경 분석**
            """
        )

    with col2:
        st.markdown("### 다음 구현 단계")
        st.markdown(
            """
            - 기상청 API 실시간 연동
            - 서울시 침수 Polygon 자동 적재
            - TOPIS 도로 통제 데이터 자동 연동
            - 공간 분석 결과를 활용한 추천 로직 고도화
            """
        )

    st.markdown("### 연동 상태")
    status_col1, status_col2, status_col3 = st.columns(3)

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

    with status_col3:
        if not has_supabase(client):
            st.warning("Supabase 연결 후 PostGIS 상태를 확인할 수 있습니다.")
        else:
            try:
                status = get_postgis_status(client)
                version = status.get("postgis_version", "확인됨")
                polygon_count = status.get("flood_polygon_count", 0)
                st.success(f"PostGIS {version} · 침수 Polygon {polygon_count}개")
            except SpatialAnalysisError as error:
                st.warning("PostGIS SQL 적용이 필요합니다.")
                st.caption(str(error))

    st.info(
        "로그인 상태에서 실행한 경로 검색은 세 경로 테이블에 자동 저장됩니다. "
        "침수 GeoJSON이 유효한 Polygon이면 ST_Intersects로 실제 교차를 판별하고, "
        "Polygon이 없는 기존 행은 중심점 100m 보조 방식으로 처리합니다."
    )
