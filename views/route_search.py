from __future__ import annotations

from typing import Optional

import streamlit as st

from config import DEFAULT_LAT, DEFAULT_LNG
from services.tmap_service import PedestrianRoute, TmapApiError, search_pedestrian_route
from utils.geo_utils import distance_meters
from utils.secret_utils import read_secret

SESSION_RESULT_KEY = "tmap_pedestrian_route_result"


def _format_distance(distance_m: int) -> str:
    if distance_m >= 1000:
        return f"{distance_m / 1000:.2f} km"
    return f"{distance_m:,} m"


def _format_duration(duration_sec: int) -> str:
    if duration_sec <= 0:
        return "정보 없음"

    minutes = max(1, round(duration_sec / 60))
    hours, remain_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {remain_minutes}분"
    return f"약 {minutes}분"


def _show_result(result: PedestrianRoute, direct_distance: float) -> None:
    st.success("TMAP 보행자 경로 API 호출에 성공했습니다.")

    col1, col2, col3 = st.columns(3)
    col1.metric("실제 보행 경로 거리", _format_distance(result.distance_m))
    col2.metric("예상 소요 시간", _format_duration(result.duration_sec))
    col3.metric("수신한 경로 좌표", f"{len(result.route_coordinates):,}개")

    st.caption(f"참고용 출발지-도착지 직선거리: 약 {direct_distance:,.1f}m")

    if result.guide_points:
        st.markdown("### 주요 경로 안내")
        st.dataframe(result.guide_points, use_container_width=True, hide_index=True)
    else:
        st.info("경로 좌표는 정상 수신했지만 별도의 안내 지점은 반환되지 않았습니다.")

    with st.expander("개발 확인용 API 응답 요약"):
        st.write(f"GeoJSON feature 개수: {len(result.raw_geojson.get('features', []))}개")
        st.write(f"LineString 통합 좌표 개수: {len(result.route_coordinates)}개")
        st.json(
            {
                "distance_m": result.distance_m,
                "duration_sec": result.duration_sec,
                "first_route_points": result.route_coordinates[:5],
            }
        )

    st.info(
        "1단계에서는 실제 경로 좌표·거리·시간을 받아오는 것까지 구현했습니다. "
        "다음 커밋에서 이 좌표를 Folium PolyLine으로 지도에 표시합니다."
    )


def render_route_search() -> None:
    st.header("TMAP 도보 경로 검색")
    st.write(
        "출발지와 도착지 좌표를 입력하면 TMAP 보행자 경로 API를 호출하여 "
        "실제 보행 거리, 예상 시간, 경로 좌표를 받아옵니다."
    )

    app_key = read_secret("TMAP_APP_KEY")
    if not app_key:
        st.warning(
            "TMAP appKey가 설정되지 않았습니다. "
            "`.streamlit/secrets.toml`에 `TMAP_APP_KEY` 값을 추가한 뒤 앱을 다시 실행해주세요."
        )

    with st.form("tmap_route_form"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 출발지")
            start_name = st.text_input("출발지 이름", value="연세대학교 미래캠퍼스")
            start_lat = st.number_input("출발지 위도", value=DEFAULT_LAT, format="%.7f")
            start_lng = st.number_input("출발지 경도", value=DEFAULT_LNG, format="%.7f")

        with col2:
            st.markdown("### 도착지")
            end_name = st.text_input("도착지 이름", value="도착지")
            end_lat = st.number_input("도착지 위도", value=DEFAULT_LAT + 0.003, format="%.7f")
            end_lng = st.number_input("도착지 경도", value=DEFAULT_LNG + 0.003, format="%.7f")

        submitted = st.form_submit_button("실제 도보 경로 검색", type="primary")

    if submitted:
        if not app_key:
            st.error("TMAP_APP_KEY를 먼저 설정해주세요.")
            return

        try:
            with st.spinner("TMAP에서 보행 경로를 검색하고 있습니다..."):
                result = search_pedestrian_route(
                    app_key=app_key,
                    start_lat=float(start_lat),
                    start_lng=float(start_lng),
                    end_lat=float(end_lat),
                    end_lng=float(end_lng),
                    start_name=start_name,
                    end_name=end_name,
                )
            st.session_state[SESSION_RESULT_KEY] = result
            st.session_state["tmap_direct_distance"] = distance_meters(
                start_lat,
                start_lng,
                end_lat,
                end_lng,
            )
        except TmapApiError as error:
            st.session_state.pop(SESSION_RESULT_KEY, None)
            st.error(str(error))
        except Exception as error:
            st.session_state.pop(SESSION_RESULT_KEY, None)
            st.error(f"예상하지 못한 오류가 발생했습니다: {error}")

    stored_result: Optional[PedestrianRoute] = st.session_state.get(SESSION_RESULT_KEY)
    if stored_result:
        direct_distance = float(st.session_state.get("tmap_direct_distance", 0.0))
        _show_result(stored_result, direct_distance)
