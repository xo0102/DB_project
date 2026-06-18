from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

import requests

from utils.formatters import to_float, to_int

TMAP_PEDESTRIAN_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian"
REQUEST_TIMEOUT = (5, 20)


class TmapApiError(RuntimeError):
    """TMAP API 호출 또는 응답 해석 과정의 사용자 처리 가능 오류."""


@dataclass(frozen=True)
class PedestrianRoute:
    """TMAP 보행자 경로 응답을 앱에서 사용하기 쉬운 형태로 정리한 결과."""

    distance_m: int
    duration_sec: int
    route_coordinates: List[Tuple[float, float]]
    guide_points: List[Dict[str, Any]]
    raw_geojson: Dict[str, Any]

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000

    @property
    def duration_minutes(self) -> int:
        if self.duration_sec <= 0:
            return 0
        return max(1, round(self.duration_sec / 60))


def _validate_coordinate(lat: float, lng: float, label: str) -> None:
    if not (-90 <= lat <= 90):
        raise TmapApiError(f"{label} 위도는 -90~90 범위여야 합니다.")
    if not (-180 <= lng <= 180):
        raise TmapApiError(f"{label} 경도는 -180~180 범위여야 합니다.")


def _validate_request(
    app_key: str,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> None:
    if not app_key.strip():
        raise TmapApiError("TMAP_APP_KEY가 설정되지 않았습니다.")

    _validate_coordinate(start_lat, start_lng, "출발지")
    _validate_coordinate(end_lat, end_lng, "도착지")

    if abs(start_lat - end_lat) < 1e-9 and abs(start_lng - end_lng) < 1e-9:
        raise TmapApiError("출발지와 도착지는 서로 다른 위치여야 합니다.")


def _feature_index(feature: Mapping[str, Any]) -> int:
    properties = feature.get("properties") or {}
    return to_int(properties.get("index"), 0)


def _ordered_features(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise TmapApiError("TMAP 응답에 경로 features가 없습니다.")

    valid_features = [feature for feature in features if isinstance(feature, dict)]
    if not valid_features:
        raise TmapApiError("TMAP 응답의 경로 형식을 해석할 수 없습니다.")

    return sorted(valid_features, key=_feature_index)


def _iter_linestring_coordinates(geometry: Mapping[str, Any]) -> Iterable[Sequence[Any]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "LineString" and isinstance(coordinates, list):
        yield from coordinates
        return

    if geometry_type == "MultiLineString" and isinstance(coordinates, list):
        for line in coordinates:
            if isinstance(line, list):
                yield from line


def _extract_route_coordinates(features: Sequence[Mapping[str, Any]]) -> List[Tuple[float, float]]:
    """
    GeoJSON의 [경도, 위도]를 Folium에서 바로 쓸 수 있는 (위도, 경도)로 변환한다.
    여러 LineString 구간은 API index 순서대로 이어 붙이고 인접 중복 좌표를 제거한다.
    """
    route_coordinates: List[Tuple[float, float]] = []

    for feature in features:
        geometry = feature.get("geometry") or {}
        if not isinstance(geometry, Mapping):
            continue

        for coordinate in _iter_linestring_coordinates(geometry):
            if not isinstance(coordinate, Sequence) or len(coordinate) < 2:
                continue

            lng = to_float(coordinate[0], float("nan"))
            lat = to_float(coordinate[1], float("nan"))
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                continue

            point = (lat, lng)
            if not route_coordinates or route_coordinates[-1] != point:
                route_coordinates.append(point)

    if len(route_coordinates) < 2:
        raise TmapApiError("TMAP 응답에서 보행 경로 좌표를 찾지 못했습니다.")

    return route_coordinates


def _extract_totals(features: Sequence[Mapping[str, Any]]) -> Tuple[int, int]:
    total_distance = 0
    total_time = 0

    # 보행자 응답은 일반적으로 시작 Point의 properties에 전체 거리/시간을 담는다.
    for feature in features:
        properties = feature.get("properties") or {}
        if not isinstance(properties, Mapping):
            continue

        if total_distance <= 0:
            total_distance = to_int(properties.get("totalDistance"), 0)
        if total_time <= 0:
            total_time = to_int(properties.get("totalTime"), 0)

        if total_distance > 0 and total_time > 0:
            break

    # 응답 형식 변화에 대비해 LineString 구간 합계를 보조값으로 사용한다.
    if total_distance <= 0 or total_time <= 0:
        line_distance = 0
        line_time = 0
        for feature in features:
            geometry = feature.get("geometry") or {}
            properties = feature.get("properties") or {}
            if not isinstance(geometry, Mapping) or not isinstance(properties, Mapping):
                continue
            if geometry.get("type") not in {"LineString", "MultiLineString"}:
                continue
            line_distance += to_int(properties.get("distance"), 0)
            line_time += to_int(properties.get("time"), 0)

        total_distance = total_distance or line_distance
        total_time = total_time or line_time

    if total_distance <= 0:
        raise TmapApiError("TMAP 응답에서 전체 이동 거리를 확인하지 못했습니다.")

    return total_distance, max(total_time, 0)


def _extract_guide_points(features: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    guide_points: List[Dict[str, Any]] = []

    for feature in features:
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        if not isinstance(geometry, Mapping) or not isinstance(properties, Mapping):
            continue
        if geometry.get("type") != "Point":
            continue

        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, Sequence) or len(coordinates) < 2:
            continue

        description = str(properties.get("description") or properties.get("name") or "").strip()
        point_type = str(properties.get("pointType") or "").strip()

        guide_points.append(
            {
                "순서": len(guide_points) + 1,
                "안내": description or "경로 안내 지점",
                "지점 유형": point_type,
                "위도": to_float(coordinates[1]),
                "경도": to_float(coordinates[0]),
            }
        )

    return guide_points


def parse_pedestrian_response(data: Mapping[str, Any]) -> PedestrianRoute:
    """TMAP GeoJSON 응답에서 거리, 시간, 경로 좌표와 안내 지점을 추출한다."""
    if not isinstance(data, Mapping):
        raise TmapApiError("TMAP 응답이 JSON 객체 형식이 아닙니다.")

    features = _ordered_features(data)
    distance_m, duration_sec = _extract_totals(features)
    route_coordinates = _extract_route_coordinates(features)
    guide_points = _extract_guide_points(features)

    return PedestrianRoute(
        distance_m=distance_m,
        duration_sec=duration_sec,
        route_coordinates=route_coordinates,
        guide_points=guide_points,
        raw_geojson=dict(data),
    )


def _response_error_message(response: requests.Response) -> str:
    detail = ""
    try:
        body = response.json()
        if isinstance(body, Mapping):
            error = body.get("error")
            if isinstance(error, Mapping):
                detail = str(error.get("message") or error.get("code") or "").strip()
            if not detail:
                detail = str(
                    body.get("errorMessage")
                    or body.get("message")
                    or body.get("msg")
                    or ""
                ).strip()
    except ValueError:
        detail = response.text.strip()[:200]

    if response.status_code in {401, 403}:
        base = "TMAP 인증에 실패했습니다. appKey와 TMAP 상품 사용 신청 상태를 확인해주세요."
    elif response.status_code == 429:
        base = "TMAP API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
    elif response.status_code == 400:
        base = "TMAP 요청 좌표 또는 입력값이 올바르지 않습니다."
    elif 500 <= response.status_code:
        base = "TMAP 서버에서 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    else:
        base = f"TMAP API 요청이 실패했습니다. HTTP {response.status_code}"

    return f"{base} 상세: {detail}" if detail else base


def search_pedestrian_route(
    *,
    app_key: str,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    start_name: str = "출발지",
    end_name: str = "도착지",
    pass_points: Optional[Sequence[Tuple[float, float]]] = None,
) -> PedestrianRoute:
    """TMAP 보행자 경로 API를 호출하고 앱용 경로 결과를 반환한다."""
    _validate_request(app_key, start_lat, start_lng, end_lat, end_lng)

    normalized_pass_points = list(pass_points or [])
    if len(normalized_pass_points) > 5:
        raise TmapApiError("보행자 경로의 경유지는 최대 5개까지 사용할 수 있습니다.")

    for index, (pass_lat, pass_lng) in enumerate(normalized_pass_points, start=1):
        _validate_coordinate(float(pass_lat), float(pass_lng), f"경유지 {index}")

    payload = {
        "startX": f"{start_lng:.7f}",
        "startY": f"{start_lat:.7f}",
        "endX": f"{end_lng:.7f}",
        "endY": f"{end_lat:.7f}",
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "startName": quote(start_name.strip() or "출발지"),
        "endName": quote(end_name.strip() or "도착지"),
        "searchOption": "0",
        "sort": "index",
    }

    if normalized_pass_points:
        # TMAP 보행자 경로 API는 경유지를 "경도,위도_경도,위도" 형식으로 받는다.
        payload["passList"] = "_".join(
            f"{float(pass_lng):.7f},{float(pass_lat):.7f}"
            for pass_lat, pass_lng in normalized_pass_points
        )
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "appKey": app_key.strip(),
    }

    try:
        response = requests.post(
            TMAP_PEDESTRIAN_URL,
            params={"version": "1"},
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout as error:
        raise TmapApiError("TMAP API 응답 시간이 초과되었습니다. 네트워크 상태를 확인해주세요.") from error
    except requests.RequestException as error:
        raise TmapApiError(f"TMAP API에 연결하지 못했습니다: {error}") from error

    if not response.ok:
        raise TmapApiError(_response_error_message(response))

    try:
        data = response.json()
    except ValueError as error:
        raise TmapApiError("TMAP API가 올바른 JSON 응답을 반환하지 않았습니다.") from error

    return parse_pedestrian_response(data)
