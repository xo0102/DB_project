from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import cos, hypot, radians
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from config import RISK_TYPE_LABELS
from db.queries import (
    get_active_risk_zones_with_reports,
    get_active_road_alerts,
    get_flood_zones,
    get_latest_weather,
)
from services.spatial_service import (
    SpatialAnalysisError,
    SpatialRiskHit,
    query_route_spatial_risks,
)
from services.tmap_service import PedestrianRoute, TmapApiError, search_pedestrian_route
from utils.formatters import format_error_message, to_float, to_int

MapPoint = Tuple[float, float]
RouteSearcher = Callable[..., PedestrianRoute]
RouteAnalyzer = Callable[[Sequence[MapPoint], "RouteRiskContext"], "RouteRiskAnalysis"]

RISK_TRIGGER_SCORE = 50
FLOOD_ROUTE_RADIUS_M = 100
ROAD_ALERT_ROUTE_RADIUS_M = 80
MAX_DETOUR_HAZARDS = 3
MAX_PASS_POINTS = 5
METERS_PER_DEGREE_LAT = 111_320.0


@dataclass(frozen=True)
class RouteRiskContext:
    report_zones: List[Dict[str, Any]] = field(default_factory=list)
    flood_zones: List[Dict[str, Any]] = field(default_factory=list)
    road_alerts: List[Dict[str, Any]] = field(default_factory=list)
    weather: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RouteRiskItem:
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
    spatial_method: str = "python_distance"
    overlap_length_m: float = 0.0
    hazard_geojson: Optional[Dict[str, Any]] = None

    @property
    def is_spatial(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True)
class RouteRiskAnalysis:
    total_score: int
    items: List[RouteRiskItem]
    category_scores: Dict[str, int]
    has_recent_report: bool
    analysis_engine: str = "python_approximation"
    analysis_warning: str = ""

    @property
    def should_offer_alternative(self) -> bool:
        return self.total_score >= RISK_TRIGGER_SCORE or self.has_recent_report

    @property
    def recent_report_count(self) -> int:
        return sum(1 for item in self.items if item.recent_report)

    @property
    def spatial_items(self) -> List[RouteRiskItem]:
        return [item for item in self.items if item.is_spatial]


@dataclass(frozen=True)
class RouteRecommendation:
    primary_route: PedestrianRoute
    primary_analysis: Optional[RouteRiskAnalysis]
    alternative_route: Optional[PedestrianRoute] = None
    alternative_analysis: Optional[RouteRiskAnalysis] = None
    alternative_pass_points: List[MapPoint] = field(default_factory=list)
    alternative_attempts: int = 0
    risk_context_warnings: List[str] = field(default_factory=list)
    alternative_error: str = ""

    @property
    def triggered_alternative_search(self) -> bool:
        return bool(self.primary_analysis and self.primary_analysis.should_offer_alternative)

    @property
    def alternative_fully_avoids_trigger(self) -> bool:
        analysis = self.alternative_analysis
        return bool(
            analysis
            and not analysis.has_recent_report
            and analysis.total_score < RISK_TRIGGER_SCORE
        )

    @property
    def alternative_improves_risk(self) -> bool:
        if not self.primary_analysis or not self.alternative_analysis:
            return False
        return _analysis_rank(self.alternative_analysis) < _analysis_rank(self.primary_analysis)


@dataclass(frozen=True)
class _ClosestRoutePoint:
    distance_m: float
    segment_index: int
    segment_ratio: float
    point: MapPoint

    @property
    def route_position(self) -> float:
        return self.segment_index + self.segment_ratio


def _meters_per_degree_lng(latitude: float) -> float:
    return max(1.0, METERS_PER_DEGREE_LAT * cos(radians(latitude)))


def _to_local_xy(point: MapPoint, origin: MapPoint) -> Tuple[float, float]:
    latitude, longitude = point
    origin_lat, origin_lng = origin
    east_m = (longitude - origin_lng) * _meters_per_degree_lng(origin_lat)
    north_m = (latitude - origin_lat) * METERS_PER_DEGREE_LAT
    return east_m, north_m


def _from_local_xy(east_m: float, north_m: float, origin: MapPoint) -> MapPoint:
    origin_lat, origin_lng = origin
    latitude = origin_lat + north_m / METERS_PER_DEGREE_LAT
    longitude = origin_lng + east_m / _meters_per_degree_lng(origin_lat)
    return latitude, longitude


def _closest_point_on_route(point: MapPoint, route: Sequence[MapPoint]) -> _ClosestRoutePoint:
    if not route:
        return _ClosestRoutePoint(float("inf"), 0, 0.0, point)

    if len(route) == 1:
        east_m, north_m = _to_local_xy(route[0], point)
        return _ClosestRoutePoint(hypot(east_m, north_m), 0, 0.0, route[0])

    best: Optional[_ClosestRoutePoint] = None

    for segment_index in range(len(route) - 1):
        start_xy = _to_local_xy(route[segment_index], point)
        end_xy = _to_local_xy(route[segment_index + 1], point)
        segment_x = end_xy[0] - start_xy[0]
        segment_y = end_xy[1] - start_xy[1]
        segment_length_sq = segment_x * segment_x + segment_y * segment_y

        if segment_length_sq <= 1e-9:
            ratio = 0.0
        else:
            ratio = -(
                start_xy[0] * segment_x + start_xy[1] * segment_y
            ) / segment_length_sq
            ratio = max(0.0, min(1.0, ratio))

        closest_x = start_xy[0] + segment_x * ratio
        closest_y = start_xy[1] + segment_y * ratio
        distance_m = hypot(closest_x, closest_y)
        closest_point = _from_local_xy(closest_x, closest_y, point)
        candidate = _ClosestRoutePoint(
            distance_m=distance_m,
            segment_index=segment_index,
            segment_ratio=ratio,
            point=closest_point,
        )

        if best is None or candidate.distance_m < best.distance_m:
            best = candidate

    return best or _ClosestRoutePoint(float("inf"), 0, 0.0, point)


def distance_point_to_route_m(point: MapPoint, route: Sequence[MapPoint]) -> float:
    """PostGIS 도입 전 단계에서 점과 경로선 사이의 최소 거리를 근사 계산한다."""
    return _closest_point_on_route(point, route).distance_m


def load_route_risk_context(client) -> RouteRiskContext:
    """경로 분석에 필요한 위험 데이터를 조회하되, 일부 테이블 실패 시 가능한 데이터로 계속 진행한다."""
    warnings: List[str] = []
    report_zones: List[Dict[str, Any]] = []
    flood_zones: List[Dict[str, Any]] = []
    road_alerts: List[Dict[str, Any]] = []
    weather: Optional[Dict[str, Any]] = None

    try:
        report_zones = get_active_risk_zones_with_reports(client)
    except Exception as error:
        warnings.append(f"최근 신고 데이터 조회 실패: {format_error_message(error)}")

    try:
        flood_zones = get_flood_zones(client)
    except Exception as error:
        warnings.append(f"침수 구역 조회 실패: {format_error_message(error)}")

    try:
        road_alerts = get_active_road_alerts(client)
    except Exception as error:
        warnings.append(f"도로 통제 조회 실패: {format_error_message(error)}")

    try:
        weather = get_latest_weather(client)
    except Exception as error:
        warnings.append(f"날씨 데이터 조회 실패: {format_error_message(error)}")

    return RouteRiskContext(
        report_zones=report_zones,
        flood_zones=flood_zones,
        road_alerts=road_alerts,
        weather=weather,
        warnings=warnings,
    )


def _dedupe_key(prefix: str, title: str, latitude: float, longitude: float) -> Tuple[str, str, float, float]:
    return prefix, title.strip(), round(latitude, 5), round(longitude, 5)


def analyze_route_risk(
    route_coordinates: Sequence[MapPoint],
    context: RouteRiskContext,
) -> RouteRiskAnalysis:
    """
    경로와 위험 데이터의 중심 좌표·반경을 비교해 위험 점수와 상세 근거를 만든다.

    현재 단계는 PostGIS 도입 전이므로 중심점과 반경 기반 근사 판별이다.
    """
    items: List[RouteRiskItem] = []
    seen_keys: set[Tuple[Any, ...]] = set()

    for zone in context.report_zones:
        latitude = to_float(zone.get("center_lat"), float("nan"))
        longitude = to_float(zone.get("center_lng"), float("nan"))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue

        radius_m = max(1, to_int(zone.get("radius_m"), 50))
        closest = _closest_point_on_route((latitude, longitude), route_coordinates)
        if closest.distance_m > radius_m:
            continue

        report = zone.get("report") if isinstance(zone.get("report"), dict) else {}
        report_id = zone.get("report_id") or report.get("id")
        key = ("user_report", report_id or zone.get("id"))
        if key in seen_keys:
            continue
        seen_keys.add(key)

        risk_type = str(zone.get("risk_type") or report.get("risk_type") or "other")
        risk_label = RISK_TYPE_LABELS.get(risk_type, risk_type)
        score = max(0, to_int(zone.get("risk_score"), 10))
        description = str(report.get("description") or "신고 설명이 입력되지 않았습니다.").strip()
        duplicate_count = max(1, to_int(report.get("duplicate_count"), 1))

        items.append(
            RouteRiskItem(
                source_type="user_report",
                source_id=to_int(report_id, 0) or None,
                risk_type=risk_type,
                title=f"최근 사용자 신고 · {risk_label}",
                risk_score=score,
                reason=(
                    f"최근 신고 위험 구역(반경 {radius_m}m)이 경로와 겹칩니다. "
                    f"경로와 신고 중심의 최소 거리는 약 {closest.distance_m:.1f}m입니다."
                ),
                latitude=latitude,
                longitude=longitude,
                distance_to_route_m=closest.distance_m,
                influence_radius_m=radius_m,
                recent_report=True,
                report_description=description,
                report_created_at=str(report.get("created_at") or zone.get("created_at") or ""),
                duplicate_count=duplicate_count,
                route_position=closest.route_position,
            )
        )

    for zone in context.flood_zones:
        latitude = to_float(zone.get("center_lat"), float("nan"))
        longitude = to_float(zone.get("center_lng"), float("nan"))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue

        title = str(zone.get("zone_name") or "침수 위험 구역")
        key = _dedupe_key("flood_zone", title, latitude, longitude)
        if key in seen_keys:
            continue

        closest = _closest_point_on_route((latitude, longitude), route_coordinates)
        if closest.distance_m > FLOOD_ROUTE_RADIUS_M:
            continue

        seen_keys.add(key)
        score = max(0, to_int(zone.get("base_score"), 0))
        risk_level = str(zone.get("risk_level") or "unknown")
        items.append(
            RouteRiskItem(
                source_type="flood_zone",
                source_id=to_int(zone.get("id"), 0) or None,
                risk_type="flood",
                title=title,
                risk_score=score,
                reason=(
                    f"침수 이력·예상 구역 중심에서 경로까지 약 {closest.distance_m:.1f}m입니다. "
                    f"위험 수준은 {risk_level}입니다."
                ),
                latitude=latitude,
                longitude=longitude,
                distance_to_route_m=closest.distance_m,
                influence_radius_m=FLOOD_ROUTE_RADIUS_M,
                route_position=closest.route_position,
            )
        )

    for alert in context.road_alerts:
        latitude = to_float(alert.get("center_lat"), float("nan"))
        longitude = to_float(alert.get("center_lng"), float("nan"))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue

        title = str(alert.get("title") or "도로 위험 알림")
        key = _dedupe_key("road_alert", title, latitude, longitude)
        if key in seen_keys:
            continue

        closest = _closest_point_on_route((latitude, longitude), route_coordinates)
        if closest.distance_m > ROAD_ALERT_ROUTE_RADIUS_M:
            continue

        seen_keys.add(key)
        score = max(0, to_int(alert.get("risk_score"), 0))
        description = str(alert.get("description") or "상세 설명 없음").strip()
        alert_type = str(alert.get("alert_type") or "road_control")
        items.append(
            RouteRiskItem(
                source_type="road_alert",
                source_id=to_int(alert.get("id"), 0) or None,
                risk_type=alert_type,
                title=title,
                risk_score=score,
                reason=(
                    f"활성 도로 알림이 경로에서 약 {closest.distance_m:.1f}m 떨어져 있습니다. "
                    f"{description}"
                ),
                latitude=latitude,
                longitude=longitude,
                distance_to_route_m=closest.distance_m,
                influence_radius_m=ROAD_ALERT_ROUTE_RADIUS_M,
                route_position=closest.route_position,
            )
        )

    weather = context.weather or {}
    weather_score = max(0, to_int(weather.get("risk_score"), 0))
    if weather_score:
        rain_current = to_float(weather.get("rain_current_mm"), 0.0)
        rain_forecast = to_float(weather.get("rain_forecast_mm"), 0.0)
        items.append(
            RouteRiskItem(
                source_type="weather",
                source_id=to_int(weather.get("id"), 0) or None,
                risk_type="weather",
                title="최신 강수 위험",
                risk_score=weather_score,
                reason=(
                    f"현재 강수량 {rain_current:g}mm, 예보 강수량 {rain_forecast:g}mm가 "
                    f"모든 경로에 공통으로 반영됩니다."
                ),
            )
        )

    return _finalize_analysis(items, analysis_engine="python_approximation")


def _finalize_analysis(
    items: Sequence[RouteRiskItem],
    *,
    analysis_engine: str,
    analysis_warning: str = "",
) -> RouteRiskAnalysis:
    normalized_items = list(items)
    category_scores: Dict[str, int] = {}
    for item in normalized_items:
        category_scores[item.source_type] = (
            category_scores.get(item.source_type, 0) + max(0, item.risk_score)
        )

    total_score = min(sum(max(0, item.risk_score) for item in normalized_items), 100)
    has_recent_report = any(item.recent_report for item in normalized_items)

    return RouteRiskAnalysis(
        total_score=total_score,
        items=normalized_items,
        category_scores=category_scores,
        has_recent_report=has_recent_report,
        analysis_engine=analysis_engine,
        analysis_warning=analysis_warning,
    )


def _spatial_hit_to_item(hit: SpatialRiskHit) -> RouteRiskItem:
    return RouteRiskItem(
        source_type=hit.source_type,
        source_id=hit.source_id,
        risk_type=hit.risk_type,
        title=hit.title,
        risk_score=hit.risk_score,
        reason=hit.reason,
        latitude=hit.latitude,
        longitude=hit.longitude,
        distance_to_route_m=hit.distance_to_route_m,
        influence_radius_m=hit.influence_radius_m,
        recent_report=hit.recent_report,
        report_description=hit.report_description,
        report_created_at=hit.report_created_at,
        duplicate_count=hit.duplicate_count,
        route_position=hit.route_position,
        spatial_method=hit.spatial_method,
        overlap_length_m=hit.overlap_length_m,
        hazard_geojson=hit.hazard_geojson,
    )


def analyze_route_risk_postgis(
    client,
    route_coordinates: Sequence[MapPoint],
    context: RouteRiskContext,
) -> RouteRiskAnalysis:
    """PostGIS의 ST_Intersects·ST_DWithin 결과와 최신 날씨 점수를 결합한다."""
    hits = query_route_spatial_risks(client, route_coordinates)
    items = [_spatial_hit_to_item(hit) for hit in hits]

    weather = context.weather or {}
    weather_score = max(0, to_int(weather.get("risk_score"), 0))
    if weather_score:
        rain_current = to_float(weather.get("rain_current_mm"), 0.0)
        rain_forecast = to_float(weather.get("rain_forecast_mm"), 0.0)
        items.append(
            RouteRiskItem(
                source_type="weather",
                source_id=to_int(weather.get("id"), 0) or None,
                risk_type="weather",
                title="최신 강수 위험",
                risk_score=weather_score,
                reason=(
                    f"현재 강수량 {rain_current:g}mm, 예보 강수량 {rain_forecast:g}mm가 "
                    f"모든 경로에 공통으로 반영됩니다."
                ),
                spatial_method="global_weather",
            )
        )

    return _finalize_analysis(items, analysis_engine="postgis")


def make_route_analyzer(client) -> RouteAnalyzer:
    """PostGIS를 우선 사용하고, 실패하면 같은 검색 동안 Python 근사 분석으로 대체한다."""
    postgis_error = ""

    def analyzer(
        route_coordinates: Sequence[MapPoint],
        context: RouteRiskContext,
    ) -> RouteRiskAnalysis:
        nonlocal postgis_error

        if not postgis_error:
            try:
                return analyze_route_risk_postgis(client, route_coordinates, context)
            except SpatialAnalysisError as error:
                postgis_error = str(error)

        fallback = analyze_route_risk(route_coordinates, context)
        return replace(
            fallback,
            analysis_engine="python_fallback",
            analysis_warning=(
                "PostGIS 분석을 사용할 수 없어 기존 중심 좌표·반경 방식으로 계산했습니다. "
                f"상세: {postgis_error}"
            ),
        )

    return analyzer


def _analysis_rank(analysis: RouteRiskAnalysis) -> Tuple[int, int, int, int]:
    """최근 신고 회피 여부를 가장 먼저, 그 다음 50점 미만 여부와 총점·위험 개수를 비교한다."""
    return (
        1 if analysis.has_recent_report else 0,
        1 if analysis.total_score >= RISK_TRIGGER_SCORE else 0,
        analysis.total_score,
        len(analysis.spatial_items),
    )


def _select_avoidance_items(analysis: RouteRiskAnalysis) -> List[RouteRiskItem]:
    spatial_items = analysis.spatial_items
    if not spatial_items:
        return []

    # 최근 신고는 점수와 무관하게 최우선 회피 대상으로 둔다.
    ranked = sorted(
        spatial_items,
        key=lambda item: (
            0 if item.recent_report else 1,
            -item.risk_score,
            item.route_position,
        ),
    )

    selected: List[RouteRiskItem] = []
    for item in ranked:
        if item.recent_report or analysis.total_score >= RISK_TRIGGER_SCORE:
            if any(
                existing.latitude is not None
                and existing.longitude is not None
                and item.latitude is not None
                and item.longitude is not None
                and abs(existing.latitude - item.latitude) < 1e-5
                and abs(existing.longitude - item.longitude) < 1e-5
                for existing in selected
            ):
                continue
            selected.append(item)
        if len(selected) >= MAX_DETOUR_HAZARDS:
            break

    return sorted(selected, key=lambda item: item.route_position)


def build_detour_pass_points(
    route_coordinates: Sequence[MapPoint],
    avoidance_items: Sequence[RouteRiskItem],
    *,
    side: int,
    extra_clearance_m: float,
) -> List[MapPoint]:
    """위험 중심을 기준으로 원래 경로의 좌·우 측에 경유점을 생성한다."""
    if side not in {-1, 1}:
        raise ValueError("side는 -1 또는 1이어야 합니다.")
    if len(route_coordinates) < 2:
        return []

    pass_points: List[MapPoint] = []

    for item in avoidance_items:
        if item.latitude is None or item.longitude is None:
            continue

        hazard_point = (item.latitude, item.longitude)
        closest = _closest_point_on_route(hazard_point, route_coordinates)
        segment_index = min(closest.segment_index, len(route_coordinates) - 2)
        segment_start = route_coordinates[segment_index]
        segment_end = route_coordinates[segment_index + 1]

        segment_end_xy = _to_local_xy(segment_end, segment_start)
        segment_length = hypot(segment_end_xy[0], segment_end_xy[1])
        if segment_length <= 1e-6:
            continue

        # 진행 방향의 왼쪽/오른쪽 단위 법선 벡터를 만든다.
        normal_east = side * (-segment_end_xy[1] / segment_length)
        normal_north = side * (segment_end_xy[0] / segment_length)
        clearance_m = max(90.0, float(item.influence_radius_m) + extra_clearance_m)
        detour_point = _from_local_xy(
            normal_east * clearance_m,
            normal_north * clearance_m,
            closest.point,
        )

        if not (-90 <= detour_point[0] <= 90 and -180 <= detour_point[1] <= 180):
            continue

        if pass_points:
            previous = pass_points[-1]
            previous_distance = _closest_point_on_route(previous, [detour_point, detour_point]).distance_m
            if previous_distance < 20:
                continue

        pass_points.append(detour_point)
        if len(pass_points) >= MAX_PASS_POINTS:
            break

    return pass_points


def _candidate_specs() -> Iterable[Tuple[int, float]]:
    # 가까운 우회부터 시도하고, 경로가 위험 구역을 계속 지나면 더 멀리 우회한다.
    return ((-1, 60.0), (1, 60.0), (-1, 120.0), (1, 120.0))


def create_route_recommendation(
    *,
    primary_route: PedestrianRoute,
    context: RouteRiskContext,
    app_key: str,
    start: MapPoint,
    end: MapPoint,
    start_name: str,
    end_name: str,
    route_searcher: RouteSearcher = search_pedestrian_route,
    route_analyzer: RouteAnalyzer = analyze_route_risk,
) -> RouteRecommendation:
    """
    기본 경로를 분석하고, 50점 이상이거나 최근 신고가 포함되면 경유점 기반 대안 경로를 탐색한다.

    TMAP 자체에 임의의 위험 Polygon을 직접 제외시키는 요청은 하지 못하므로,
    위험 구간 좌·우에 경유점을 만들어 여러 후보를 요청한 뒤 가장 안전한 후보를 고른다.
    """
    primary_analysis = route_analyzer(primary_route.route_coordinates, context)

    if not primary_analysis.should_offer_alternative:
        return RouteRecommendation(
            primary_route=primary_route,
            primary_analysis=primary_analysis,
            risk_context_warnings=context.warnings,
        )

    avoidance_items = _select_avoidance_items(primary_analysis)
    if not avoidance_items:
        return RouteRecommendation(
            primary_route=primary_route,
            primary_analysis=primary_analysis,
            risk_context_warnings=context.warnings,
            alternative_error=(
                "총 위험도는 높지만 우회 가능한 위치 기반 위험 요소가 없습니다. "
                "날씨 위험처럼 모든 경로에 공통 적용되는 요소는 경로 변경만으로 피할 수 없습니다."
            ),
        )

    candidates: List[Tuple[PedestrianRoute, RouteRiskAnalysis, List[MapPoint]]] = []
    errors: List[str] = []
    attempts = 0

    for side, extra_clearance_m in _candidate_specs():
        pass_points = build_detour_pass_points(
            primary_route.route_coordinates,
            avoidance_items,
            side=side,
            extra_clearance_m=extra_clearance_m,
        )
        if not pass_points:
            continue

        attempts += 1
        try:
            route = route_searcher(
                app_key=app_key,
                start_lat=start[0],
                start_lng=start[1],
                end_lat=end[0],
                end_lng=end[1],
                start_name=start_name,
                end_name=end_name,
                pass_points=pass_points,
            )
            analysis = route_analyzer(route.route_coordinates, context)
            candidates.append((route, analysis, pass_points))
        except TmapApiError as error:
            errors.append(str(error))
        except Exception as error:
            errors.append(format_error_message(error))

    if not candidates:
        return RouteRecommendation(
            primary_route=primary_route,
            primary_analysis=primary_analysis,
            alternative_attempts=attempts,
            risk_context_warnings=context.warnings,
            alternative_error=(
                "위험 구간을 우회하는 TMAP 경로 후보를 만들지 못했습니다. "
                + (f"마지막 오류: {errors[-1]}" if errors else "다른 출발지·도착지를 선택해보세요.")
            ),
        )

    candidates.sort(
        key=lambda candidate: (
            *_analysis_rank(candidate[1]),
            candidate[0].distance_m,
            candidate[0].duration_sec,
        )
    )
    alternative_route, alternative_analysis, pass_points = candidates[0]

    return RouteRecommendation(
        primary_route=primary_route,
        primary_analysis=primary_analysis,
        alternative_route=alternative_route,
        alternative_analysis=alternative_analysis,
        alternative_pass_points=pass_points,
        alternative_attempts=attempts,
        risk_context_warnings=context.warnings,
        alternative_error="; ".join(errors[-2:]),
    )
