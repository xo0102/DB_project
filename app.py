from __future__ import annotations

import streamlit as st

from components.sidebar import render_sidebar
from config import APP_SUBTITLE, APP_TITLE
from db.client import get_supabase_client
from views.auth import render_login, render_signup
from views.db_viewer import render_db_viewer
from views.home import render_home
from views.risk_calculator import render_simple_risk_calculator
from views.risk_map import render_risk_map
from views.risk_report import render_risk_report
from views.route_search import render_route_search


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    client = get_supabase_client()
    menu = render_sidebar()

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    if menu == "홈":
        render_home(client)
    elif menu == "로그인":
        render_login(client)
    elif menu == "회원가입":
        render_signup(client)
    elif menu == "위험 지도":
        render_risk_map(client)
    elif menu == "위험 신고":
        render_risk_report(client)
    elif menu == "간단 위험도 계산":
        render_simple_risk_calculator(client)
    elif menu == "DB 테이블 조회":
        render_db_viewer(client)
    elif menu == "경로 검색":
        render_route_search(client)


if __name__ == "__main__":
    main()
