from __future__ import annotations

import streamlit as st

from config import DB_TABLES
from db.client import has_supabase, show_supabase_warning
from db.queries import fetch_table_rows
from utils.formatters import format_error_message


def render_db_viewer(client) -> None:
    st.header("DB 테이블 조회")
    st.write("Supabase PostgreSQL의 주요 테이블을 최대 100개 행까지 조회합니다.")

    if not has_supabase(client):
        show_supabase_warning()
        return

    table_name = st.selectbox("조회할 테이블 선택", DB_TABLES)

    if st.button("테이블 조회", type="primary"):
        try:
            data = fetch_table_rows(client, table_name, limit=100)

            st.write(f"### `{table_name}` 테이블")
            st.write(f"조회된 행 수: {len(data)}개")

            if data:
                st.dataframe(data, use_container_width=True)
            else:
                st.info("현재 저장된 데이터가 없습니다.")

        except Exception as e:
            st.error("테이블 조회 중 오류가 발생했습니다.")
            st.caption(format_error_message(e))
