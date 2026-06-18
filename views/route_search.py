from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import streamlit as st

from components.map_components import create_route_selection_map, render_folium_map
from config import DEFAULT_LAT, DEFAULT_LNG
from services.tmap_service import PedestrianRoute, TmapApiError, search_pedestrian_route
from utils.geo_utils import distance_meters
from utils.secret_utils import read_secret
from utils.state_utils import get_clicked_point

SESSION_RESULT_KEY = "tmap_pedestrian_route_result"
DIRECT_DISTANCE_KEY = "tmap_direct_distance"
START_LAT_KEY = "route_start_lat"
START_LNG_KEY = "route_start_lng"
END_LAT_KEY = "route_end_lat"
END_LNG_KEY = "route_end_lng"
START_NAME_KEY = "route_start_name"
END_NAME_KEY = "route_end_name"
SELECT_TARGET_KEY = "route_select_target"
SELECT_TARGET_WIDGET_KEY = "route_select_target_widget"
LAST_CLICK_KEY = "route_last_processed_click"
MAP_VERSION_KEY = "route_map_version"
FLASH_MESSAGE_KEY = "route_flash_message"

DEFAULT_END_LAT = DEFAULT_LAT + 0.003
DEFAULT_END_LNG = DEFAULT_LNG + 0.003


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


def _init_route_state() -> None:
    defaults: Dict[str, Any] = {
        START_LAT_KEY: DEFAULT_LAT,
        START_LNG_KEY: DEFAULT_LNG,
        END_LAT_KEY: DEFAULT_END_LAT,
        END_LNG_KEY: DEFAULT_END_LNG,
        START_NAME_KEY: "연세대학교 미래캠퍼스",
        END_NAME_KEY: "도착지",
        SELECT_TARGET_KEY: "출발지",
        SELECT_TARGET_WIDGET_KEY: "출발지",
        MAP_VERSION_KEY: 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_route_result() -> None:
    st.session_state.pop(SESSION_RESULT_KEY, None)
    st.session_state.pop(DIRECT_DISTANCE_KEY, None)


def _sync_select_target_from_widget() -> None:
    st.session_state[SELECT_TARGET_KEY] = st.session_state.get(
        SELECT_TARGET_WIDGET_KEY,
        "출발지",
    )


def _refresh_map_component() -> None:
    st.session_state[MAP_VERSION_KEY] = int(st.session_state.get(MAP_VERSION_KEY, 0)) + 1
    st.session_state.pop(LAST_CLICK_KEY, None)


def _swap_points() -> None:
    start_lat = st.session_state[START_LAT_KEY]
    start_lng = st.session_state[START_LNG_KEY]
    start_name = st.session_state[START_NAME_KEY]

    st.session_state[START_LAT_KEY] = st.session_state[END_LAT_KEY]
    st.session_state[START_LNG_KEY] = st.session_state[END_LNG_KEY]
    st.session_state[START_NAME_KEY] = st.session_state[END_NAME_KEY]

    st.session_state[END_LAT_KEY] = start_lat
    st.session_state[END_LNG_KEY] = start_lng
    st.session_state[END_NAME_KEY] = start_name

    _clear_route_result()
    _refresh_map_component()


def _reset_points() -> None:
    st.session_state[START_LAT_KEY] = DEFAULT_LAT
    st.session_state[START_LNG_KEY] = DEFAULT_LNG
    st.session_state[END_LAT_KEY] = DEFAULT_END_LAT
    st.session_state[END_LNG_KEY] = DEFAULT_END_LNG
    st.session_state[START_NAME_KEY] = "연세대학교 미래캠퍼스"
    st.session_state[END_NAME_KEY] = "도착지"
    st.session_state[SELECT_TARGET_KEY] = "출발지"
    st.session_state[SELECT_TARGET_WIDGET_KEY] = "출발지"

    _clear_route_result()
    _refresh_map_component()


def _point_signature(point: Tuple[float, float]) -> str:
    return f"{point[0]:.7f},{point[1]:.7f}"


def _process_map_click(map_data: Optional[Dict[str, Any]]) -> None:
    """새 지도 클릭을 현재 선택 모드의 출발지 또는 도착지에 반영한다."""
    point = get_clicked_point(map_data)
    if point is None:
        return

    signature = _point_signature(point)
    if st.session_state.get(LAST_CLICK_KEY) == signature:
        return

    st.session_state[LAST_CLICK_KEY] = signature
    lat, lng = point

    if st.session_state[SELECT_TARGET_KEY] == "출발지":
        st.session_state[START_LAT_KEY] = lat
        st.session_state[START_LNG_KEY] = lng
        st.session_state[SELECT_TARGET_KEY] = "도착지"
        st.session_state[FLASH_MESSAGE_KEY] = "출발지를 설정했습니다. 이제 지도에서 도착지를 선택하세요."
    else:
        st.session_state[END_LAT_KEY] = lat
        st.session_state[END_LNG_KEY] = lng
        st.session_state[FLASH_MESSAGE_KEY] = "도착지를 설정했습니다. 경로 검색 버튼을 눌러주세요."

    _clear_route_result()
    _refresh_map_component()
    st.rerun()


def _show_point_summary() -> None:
    start_lat = float(st.session_state[START_LAT_KEY])
    start_lng = float(st.session_state[START_LNG_KEY])
    end_lat = float(st.session_state[END_LAT_KEY])
    end_lng = float(st.session_state[END_LNG_KEY])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🟢 출발지")
        st.code(f"위도 {start_lat:.7f}\n경도 {start_lng:.7f}", language="text")

    with col2:
        st.markdown("#### 🔴 도착지")
        st.code(f"위도 {end_lat:.7f}\n경도 {end_lng:.7f}", language="text")


def _search_route(app_key: str) -> None:
    start_lat = float(st.session_state[START_LAT_KEY])
    start_lng = float(st.session_state[START_LNG_KEY])
    end_lat = float(st.session_state[END_LAT_KEY])
    end_lng = float(st.session_state[END_LNG_KEY])

    try:
        with st.spinner("TMAP에서 보행 경로를 검색하고 있습니다..."):
            result = search_pedestrian_route(
                app_key=app_key,
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=end_lat,
                end_lng=end_lng,
                start_name=str(st.session_state[START_NAME_KEY]),
                end_name=str(st.session_state[END_NAME_KEY]),
            )

        st.session_state[SESSION_RESULT_KEY] = result
        st.session_state[DIRECT_DISTANCE_KEY] = distance_meters(
            start_lat,
            start_lng,
            end_lat,
            end_lng,
        )
        st.session_state[FLASH_MESSAGE_KEY] = "TMAP 경로 검색에 성공했습니다. 지도에 실제 도보 경로를 표시했습니다."
        _refresh_map_component()
        st.rerun()

    except TmapApiError as error:
        _clear_route_result()
        st.error(str(error))
    except Exception as error:
        _clear_route_result()
        st.error(f"예상하지 못한 오류가 발생했습니다: {error}")


def _show_result(result: PedestrianRoute, direct_distance: float) -> None:
    st.markdown("### 경로 검색 결과")

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


def render_route_search() -> None:
    _init_route_state()

    st.header("TMAP 도보 경로 검색")
    st.write(
        "지도에서 출발지와 도착지를 차례대로 선택하면 TMAP 보행자 경로 API를 호출하고, "
        "실제 도보 경로를 지도 위 선으로 표시합니다."
    )

    flash_message = st.session_state.pop(FLASH_MESSAGE_KEY, None)
    if flash_message:
        st.success(flash_message)

    app_key = read_secret("TMAP_APP_KEY")
    if not app_key:
        st.warning(
            "TMAP appKey가 설정되지 않았습니다. "
            "`.streamlit/secrets.toml`에 `TMAP_APP_KEY` 값을 추가한 뒤 앱을 다시 실행해주세요."
        )

    with st.expander("지점 이름 설정", expanded=False):
        name_col1, name_col2 = st.columns(2)
        with name_col1:
            st.text_input("출발지 이름", key=START_NAME_KEY)
        with name_col2:
            st.text_input("도착지 이름", key=END_NAME_KEY)

    st.markdown("### 1. 지도에서 지점 선택")
    # 지도 클릭 후 내부 선택 모드가 자동 전환되면, 다음 rerun에서 라디오에도 반영한다.
    st.session_state[SELECT_TARGET_WIDGET_KEY] = st.session_state[SELECT_TARGET_KEY]
    st.radio(
        "현재 지도 클릭으로 설정할 지점",
        options=["출발지", "도착지"],
        horizontal=True,
        key=SELECT_TARGET_WIDGET_KEY,
        on_change=_sync_select_target_from_widget,
        help="출발지를 선택하면 자동으로 도착지 선택 모드로 넘어갑니다.",
    )

    action_col1, action_col2, action_col3 = st.columns([1, 1, 3])
    with action_col1:
        st.button("출발·도착 바꾸기", on_click=_swap_points, use_container_width=True)
    with action_col2:
        st.button("초기화", on_click=_reset_points, use_container_width=True)
    with action_col3:
        current_target = st.session_state[SELECT_TARGET_KEY]
        st.info(f"현재 선택 모드: **{current_target}** — 아래 지도에서 원하는 위치를 클릭하세요.")

    _show_point_summary()

    stored_result: Optional[PedestrianRoute] = st.session_state.get(SESSION_RESULT_KEY)
    route_coordinates = stored_result.route_coordinates if stored_result else None

    start = (
        float(st.session_state[START_LAT_KEY]),
        float(st.session_state[START_LNG_KEY]),
    )
    end = (
        float(st.session_state[END_LAT_KEY]),
        float(st.session_state[END_LNG_KEY]),
    )

    route_map = create_route_selection_map(
        start=start,
        end=end,
        route_coordinates=route_coordinates,
        start_name=str(st.session_state[START_NAME_KEY]),
        end_name=str(st.session_state[END_NAME_KEY]),
    )
    map_key = f"route_selection_map_{st.session_state[MAP_VERSION_KEY]}"
    map_data = render_folium_map(
        route_map,
        key=map_key,
        height=620,
        returned_objects=["last_clicked"],
    )
    _process_map_click(map_data)

    st.caption("초록 마커는 출발지, 빨간 마커는 도착지이며, 검색 후 파란 선이 실제 TMAP 도보 경로입니다.")

    st.markdown("### 2. 실제 경로 검색")
    search_disabled = not bool(app_key)
    if st.button(
        "선택한 두 지점으로 도보 경로 검색",
        type="primary",
        disabled=search_disabled,
        use_container_width=True,
    ):
        if not app_key:
            st.error("TMAP_APP_KEY를 먼저 설정해주세요.")
        else:
            _search_route(app_key)

    if stored_result:
        direct_distance = float(st.session_state.get(DIRECT_DISTANCE_KEY, 0.0))
        _show_result(stored_result, direct_distance)
