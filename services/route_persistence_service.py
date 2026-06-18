from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from services.route_risk_service import (
    RouteRecommendation,
    RouteRiskAnalysis,
    RouteRiskItem,
)
from services.tmap_service import PedestrianRoute
from utils.formatters import format_error_message, to_int

MapPoint = Tuple[float, float]


class RoutePersistenceError(RuntimeError):
    """경로 검색 결과를 Supabase에 저장하지 못했을 때 발생하는 오류."""


@dataclass(frozen=True)
class SavedRouteRecommendation:
    search_log_id: int
    route_result_ids: Dict[str, int]
    route_count: int
    risk_detail_count: int


def _route_geojson(
    *,
    route: PedestrianRoute,
    result_type: str,
    route_role: str,
    start: MapPoint,
    end: MapPoint,
    start_name: str,
    end_name: str,
    pass_points: Optional[Sequence[MapPoint]] = None,
) -> Dict[str, Any]:
    """
    TMAP 경로를 표준 GeoJSON Feature/LineString으로 정규화한다.

    Folium 경로 좌표는 (위도, 경도)를 사용하지만 GeoJSON은 [경도, 위도] 순서다.
    """
    coordinates = [
        [float(longitude), float(latitude)]
        for latitude, longitude in route.route_coordinates
    ]

    if len(coordinates) < 2:
        raise RoutePersistenceError("경로 GeoJSON을 저장하려면 좌표가 2개 이상 필요합니다.")

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "provider": "TMAP",
            "result_type": result_type,
            "route_role": route_role,
            "distance_m": int(route.distance_m),
            "duration_sec": int(route.duration_sec),
            "start": {
                "name": start_name,
                "lat": float(start[0]),
                "lng": float(start[1]),
            },
            "end": {
                "name": end_name,
                "lat": float(end[0]),
                "lng": float(end[1]),
            },
            "pass_points": [
                {"lat": float(latitude), "lng": float(longitude)}
                for latitude, longitude in (pass_points or [])
            ],
        },
    }


def _risk_detail_reason(item: RouteRiskItem) -> str:
    parts: List[str] = []

    if item.reason.strip():
        parts.append(item.reason.strip())

    if item.recent_report:
        description = item.report_description.strip() or "설명 없음"
        parts.append(f"신고 내용: {description}")
        if item.report_created_at:
            parts.append(f"신고 시각: {item.report_created_at}")
        if item.duplicate_count:
            parts.append(f"누적 신고: {item.duplicate_count}건")

    if item.distance_to_route_m is not None:
        parts.append(f"경로와의 최소 거리: 약 {item.distance_to_route_m:.1f}m")

    if item.overlap_length_m > 0:
        parts.append(f"경로와 위험 Polygon의 실제 교차 길이: 약 {item.overlap_length_m:.1f}m")

    if item.spatial_method:
        parts.append(f"공간 판별 방식: {item.spatial_method}")

    return " | ".join(parts) or item.title


def _risk_detail_payload(item: RouteRiskItem) -> Dict[str, Any]:
    return {
        "source_type": item.source_type,
        "source_id": item.source_id,
        "risk_type": item.risk_type,
        "risk_score": max(0, min(100, int(item.risk_score))),
        "reason": _risk_detail_reason(item),
    }


def _analysis_payload(analysis: Optional[RouteRiskAnalysis]) -> List[Dict[str, Any]]:
    if analysis is None:
        return []
    return [_risk_detail_payload(item) for item in analysis.items]


def _alternative_is_best(recommendation: RouteRecommendation) -> bool:
    return bool(
        recommendation.alternative_route
        and recommendation.alternative_analysis
        and (
            recommendation.alternative_fully_avoids_trigger
            or recommendation.alternative_improves_risk
        )
    )


def _primary_reason(
    recommendation: RouteRecommendation,
    *,
    stored_as_best: bool,
) -> str:
    analysis = recommendation.primary_analysis

    if analysis is None:
        return "TMAP 기본 보행 경로입니다. Supabase 위험 분석은 수행되지 않았습니다."

    if stored_as_best:
        if analysis.has_recent_report:
            return (
                f"최근 사용자 신고 {analysis.recent_report_count}건이 포함되지만 "
                "더 안전한 대안 경로를 찾지 못해 기본 경로를 추천 결과로 저장했습니다."
            )
        if analysis.total_score >= 50:
            return (
                f"총 위험도는 {analysis.total_score}점이지만 더 안전한 대안 경로를 찾지 못해 "
                "기본 경로를 추천 결과로 저장했습니다."
            )
        return (
            f"최근 사용자 신고가 없고 총 위험도 {analysis.total_score}점으로 "
            "기준 50점 미만인 기본 경로입니다."
        )

    return (
        f"TMAP이 처음 반환한 비교용 기본 경로입니다. "
        f"총 위험도 {analysis.total_score}점, 최근 신고 {analysis.recent_report_count}건이 반영되었습니다."
    )


def _alternative_reason(
    recommendation: RouteRecommendation,
    *,
    stored_as_best: bool,
) -> str:
    analysis = recommendation.alternative_analysis
    primary_analysis = recommendation.primary_analysis

    if analysis is None:
        return "위험 회피를 위해 생성한 TMAP 대안 경로입니다."

    if stored_as_best and recommendation.alternative_fully_avoids_trigger:
        return (
            f"최근 사용자 신고를 포함하지 않고 총 위험도를 {analysis.total_score}점으로 낮춘 "
            "위험 회피 추천 경로입니다."
        )

    if stored_as_best and recommendation.alternative_improves_risk and primary_analysis:
        return (
            f"기본 경로 위험도 {primary_analysis.total_score}점보다 낮은 "
            f"{analysis.total_score}점의 위험 회피 추천 경로입니다."
        )

    return (
        f"위험 회피를 시도한 비교용 대안 경로이며, 현재 계산된 총 위험도는 "
        f"{analysis.total_score}점입니다."
    )


def _build_result_row(
    *,
    route: PedestrianRoute,
    analysis: Optional[RouteRiskAnalysis],
    result_type: str,
    route_role: str,
    recommendation_reason: str,
    start: MapPoint,
    end: MapPoint,
    start_name: str,
    end_name: str,
    pass_points: Optional[Sequence[MapPoint]] = None,
) -> Dict[str, Any]:
    return {
        "result_type": result_type,
        "distance_m": max(0, int(route.distance_m)),
        "duration_sec": max(0, int(route.duration_sec)),
        "total_risk_score": (
            max(0, min(100, int(analysis.total_score))) if analysis else 0
        ),
        "route_geojson": _route_geojson(
            route=route,
            result_type=result_type,
            route_role=route_role,
            start=start,
            end=end,
            start_name=start_name,
            end_name=end_name,
            pass_points=pass_points,
        ),
        "recommendation_reason": recommendation_reason,
        "risk_details": _analysis_payload(analysis),
    }


def build_route_result_payloads(
    *,
    recommendation: RouteRecommendation,
    start: MapPoint,
    end: MapPoint,
    start_name: str,
    end_name: str,
) -> List[Dict[str, Any]]:
    """RPC가 route_results와 route_risk_details에 저장할 JSON 배열을 만든다."""
    alternative_is_best = _alternative_is_best(recommendation)
    payloads: List[Dict[str, Any]] = []

    if alternative_is_best and recommendation.alternative_route:
        payloads.append(
            _build_result_row(
                route=recommendation.alternative_route,
                analysis=recommendation.alternative_analysis,
                result_type="best",
                route_role="risk_avoidance",
                recommendation_reason=_alternative_reason(
                    recommendation,
                    stored_as_best=True,
                ),
                start=start,
                end=end,
                start_name=start_name,
                end_name=end_name,
                pass_points=recommendation.alternative_pass_points,
            )
        )
        payloads.append(
            _build_result_row(
                route=recommendation.primary_route,
                analysis=recommendation.primary_analysis,
                result_type="alternative_1",
                route_role="tmap_primary",
                recommendation_reason=_primary_reason(
                    recommendation,
                    stored_as_best=False,
                ),
                start=start,
                end=end,
                start_name=start_name,
                end_name=end_name,
            )
        )
        return payloads

    payloads.append(
        _build_result_row(
            route=recommendation.primary_route,
            analysis=recommendation.primary_analysis,
            result_type="best",
            route_role="tmap_primary",
            recommendation_reason=_primary_reason(
                recommendation,
                stored_as_best=True,
            ),
            start=start,
            end=end,
            start_name=start_name,
            end_name=end_name,
        )
    )

    if recommendation.alternative_route:
        payloads.append(
            _build_result_row(
                route=recommendation.alternative_route,
                analysis=recommendation.alternative_analysis,
                result_type="alternative_1",
                route_role="risk_avoidance",
                recommendation_reason=_alternative_reason(
                    recommendation,
                    stored_as_best=False,
                ),
                start=start,
                end=end,
                start_name=start_name,
                end_name=end_name,
                pass_points=recommendation.alternative_pass_points,
            )
        )

    return payloads


def _normalize_rpc_data(data: Any) -> Mapping[str, Any]:
    if isinstance(data, Mapping):
        return data

    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        return data[0]

    raise RoutePersistenceError("DB 저장 응답에서 생성된 ID 정보를 확인하지 못했습니다.")


def _parse_route_result_ids(value: Any) -> Dict[str, int]:
    if not isinstance(value, list):
        return {}

    result: Dict[str, int] = {}
    for row in value:
        if not isinstance(row, Mapping):
            continue
        result_type = str(row.get("result_type") or "").strip()
        result_id = to_int(row.get("id"), 0)
        if result_type and result_id:
            result[result_type] = result_id
    return result


def save_route_recommendation(
    *,
    client: Any,
    recommendation: RouteRecommendation,
    start: MapPoint,
    end: MapPoint,
    start_name: str,
    end_name: str,
) -> SavedRouteRecommendation:
    """
    Supabase RPC를 호출해 검색 로그, 경로 결과, 위험 상세를 한 트랜잭션으로 저장한다.

    사전에 sql/route_persistence.sql을 Supabase SQL Editor에서 실행해야 한다.
    """
    payloads = build_route_result_payloads(
        recommendation=recommendation,
        start=start,
        end=end,
        start_name=start_name,
        end_name=end_name,
    )
    risk_detail_count = sum(len(row.get("risk_details") or []) for row in payloads)

    try:
        response = client.rpc(
            "save_route_recommendation",
            {
                "p_start_lat": float(start[0]),
                "p_start_lng": float(start[1]),
                "p_end_lat": float(end[0]),
                "p_end_lng": float(end[1]),
                "p_results": payloads,
            },
        ).execute()
    except Exception as error:
        message = format_error_message(error)
        lower_message = message.lower()

        if "save_route_recommendation" in lower_message and (
            "could not find" in lower_message
            or "schema cache" in lower_message
            or "function" in lower_message
        ):
            raise RoutePersistenceError(
                "Supabase 저장 함수가 아직 없습니다. "
                "프로젝트의 `sql/route_persistence.sql` 내용을 Supabase SQL Editor에서 실행해주세요."
            ) from error

        if "row-level security" in lower_message or "permission denied" in lower_message:
            raise RoutePersistenceError(
                "경로 저장 권한이 거절되었습니다. 로그인 상태와 route_* 테이블의 RLS 정책을 확인해주세요."
            ) from error

        raise RoutePersistenceError(
            f"경로 검색 결과 DB 저장에 실패했습니다: {message}"
        ) from error

    data = _normalize_rpc_data(getattr(response, "data", None))
    search_log_id = to_int(data.get("search_log_id"), 0)
    route_result_ids = _parse_route_result_ids(data.get("route_results"))
    route_count = to_int(data.get("route_count"), len(payloads))
    saved_risk_detail_count = to_int(data.get("risk_detail_count"), risk_detail_count)

    if not search_log_id:
        raise RoutePersistenceError("route_search_logs의 생성 ID를 확인하지 못했습니다.")

    return SavedRouteRecommendation(
        search_log_id=search_log_id,
        route_result_ids=route_result_ids,
        route_count=route_count,
        risk_detail_count=saved_risk_detail_count,
    )
