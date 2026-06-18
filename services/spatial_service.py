from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from utils.formatters import format_error_message, to_float, to_int

MapPoint = Tuple[float, float]


class SpatialAnalysisError(RuntimeError):
    """PostGIS RPC 호출 또는 응답 해석에 실패했을 때 발생하는 오류."""


@dataclass(frozen=True)
class SpatialRiskHit:
    source_type: str
    source_id: Optional[int]
    risk_type: str
    title: str
    risk_score: int
    reason: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_to_route_m: Optional[float] = None
    influence_radius_m: int = 0
    recent_report: bool = False
    report_description: str = ""
    report_created_at: str = ""
    duplicate_count: int = 0
    route_position: float = 0.0
    spatial_method: str = "postgis"
    overlap_length_m: float = 0.0
    hazard_geojson: Optional[Dict[str, Any]] = None


def route_coordinates_to_geojson(route_coordinates: Sequence[MapPoint]) -> Dict[str, Any]:
    """(위도, 경도) 배열을 GeoJSON Feature/LineString으로 변환한다."""
    coordinates: List[List[float]] = []

    for point in route_coordinates:
        if len(point) != 2:
            raise SpatialAnalysisError("경로 좌표는 (위도, 경도) 쌍이어야 합니다.")

        latitude = float(point[0])
        longitude = float(point[1])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise SpatialAnalysisError("경로 좌표 범위가 올바르지 않습니다.")

        # GeoJSON은 [경도, 위도] 순서다.
        coordinates.append([longitude, latitude])

    if len(coordinates) < 2:
        raise SpatialAnalysisError("PostGIS 공간 분석에는 경로 좌표가 2개 이상 필요합니다.")

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "provider": "TMAP",
            "analysis_target": "route",
        },
    }


def _normalize_rpc_rows(data: Any) -> List[Mapping[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping)]
    if isinstance(data, Mapping):
        return [data]
    raise SpatialAnalysisError("PostGIS 분석 응답 형식을 해석하지 못했습니다.")


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_spatial_hit(row: Mapping[str, Any]) -> SpatialRiskHit:
    return SpatialRiskHit(
        source_type=str(row.get("source_type") or "unknown"),
        source_id=_optional_int(row.get("source_id")),
        risk_type=str(row.get("risk_type") or "other"),
        title=str(row.get("title") or "공간 위험 요소"),
        risk_score=max(0, min(100, to_int(row.get("risk_score"), 0))),
        reason=str(row.get("reason") or "PostGIS 공간 분석에서 위험 요소가 감지되었습니다."),
        latitude=_optional_float(row.get("latitude")),
        longitude=_optional_float(row.get("longitude")),
        distance_to_route_m=_optional_float(row.get("distance_to_route_m")),
        influence_radius_m=max(0, to_int(row.get("influence_radius_m"), 0)),
        recent_report=bool(row.get("recent_report")),
        report_description=str(row.get("report_description") or ""),
        report_created_at=str(row.get("report_created_at") or ""),
        duplicate_count=max(0, to_int(row.get("duplicate_count"), 0)),
        route_position=max(0.0, min(1.0, to_float(row.get("route_position"), 0.0))),
        spatial_method=str(row.get("spatial_method") or "postgis"),
        overlap_length_m=max(0.0, to_float(row.get("overlap_length_m"), 0.0)),
        hazard_geojson=(
            dict(row.get("hazard_geojson"))
            if isinstance(row.get("hazard_geojson"), Mapping)
            else None
        ),
    )


def query_route_spatial_risks(
    client,
    route_coordinates: Sequence[MapPoint],
) -> List[SpatialRiskHit]:
    """경로와 위험 공간 데이터의 교차·근접 여부를 PostGIS RPC로 조회한다."""
    if client is None:
        raise SpatialAnalysisError("Supabase 클라이언트가 없어 PostGIS 분석을 수행할 수 없습니다.")

    route_geojson = route_coordinates_to_geojson(route_coordinates)

    try:
        response = client.rpc(
            "analyze_route_spatial",
            {
                "p_route_geojson": route_geojson,
                "p_flood_fallback_radius_m": 100,
                "p_road_alert_radius_m": 80,
            },
        ).execute()
    except Exception as error:
        message = format_error_message(error)
        if "analyze_route_spatial" in message or "PGRST202" in message:
            raise SpatialAnalysisError(
                "PostGIS 분석 함수가 DB에 없습니다. sql/postgis_spatial_analysis.sql을 "
                "Supabase SQL Editor에서 먼저 실행해주세요."
            ) from error
        raise SpatialAnalysisError(f"PostGIS 공간 분석 호출에 실패했습니다: {message}") from error

    try:
        rows = _normalize_rpc_rows(getattr(response, "data", None))
        return [_parse_spatial_hit(row) for row in rows]
    except SpatialAnalysisError:
        raise
    except Exception as error:
        raise SpatialAnalysisError(
            f"PostGIS 공간 분석 응답을 처리하지 못했습니다: {format_error_message(error)}"
        ) from error


def get_postgis_status(client) -> Dict[str, Any]:
    """PostGIS 설치 및 공간 컬럼 변환 상태를 확인한다."""
    if client is None:
        raise SpatialAnalysisError("Supabase 클라이언트가 없습니다.")

    try:
        response = client.rpc("postgis_healthcheck").execute()
    except Exception as error:
        raise SpatialAnalysisError(
            "PostGIS 상태 확인에 실패했습니다. sql/postgis_spatial_analysis.sql 실행 여부를 확인해주세요. "
            f"상세: {format_error_message(error)}"
        ) from error

    data = getattr(response, "data", None)
    if isinstance(data, Mapping):
        return dict(data)
    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        return dict(data[0])
    raise SpatialAnalysisError("PostGIS 상태 확인 응답 형식을 해석하지 못했습니다.")
