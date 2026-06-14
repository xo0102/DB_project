from __future__ import annotations

import streamlit as st

from db.client import has_supabase, show_supabase_warning


def render_home(client) -> None:
    st.header("홈")
    st.subheader("비 오는 날 야간 도보 이동을 위한 웹 DB 응용 기본틀")

    st.write(
        "이 프로젝트는 침수 위험 구역, 도로 통제 정보, 날씨 정보, 사용자 신고 데이터를 "
        "Supabase DB와 연결하여 확인하는 Streamlit 기반 웹 DB 응용 기본틀입니다."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 현재 기본틀에 포함된 기능")
        st.markdown(
            """
            - Supabase 연결 구조
            - 회원가입 / 로그인 / 로그아웃
            - 사용자 위험 신고 저장
            - 신고 기반 위험 구역 생성
            - Folium 기반 위험 지도 표시
            - 선택 위치 기준 간단 위험도 계산
            - 주요 DB 테이블 조회
            - 경로 검색 데모 화면
            """
        )

    with col2:
        st.markdown("### 추후 구현 예정 기능")
        st.markdown(
            """
            - TMAP API 기반 실제 도보 경로 탐색
            - 경로별 위험도 비교
            - 기상청 API 실시간 연동
            - 도로 통제 데이터 자동 연동
            - PostGIS 기반 공간 연산
            - 경로 LineString과 침수 Polygon 교차 판별
            """
        )

    st.markdown("### Supabase 연결 상태")
    if has_supabase(client):
        st.success("Supabase 클라이언트가 생성되었습니다. DB 조회와 입력 기능을 테스트할 수 있습니다.")
    else:
        show_supabase_warning()
        client_error = st.session_state.get("supabase_client_error")
        if client_error:
            st.caption(f"클라이언트 생성 오류: {client_error}")

    st.info(
        "이번 단계는 완성형 서비스가 아니라, DB와 웹 화면이 연결되는 흐름을 보여주는 기본틀입니다."
    )
