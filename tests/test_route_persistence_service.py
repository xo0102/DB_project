from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Dict, List

from services.route_persistence_service import (
    RoutePersistenceError,
    build_route_result_payloads,
    save_route_recommendation,
)
from services.route_risk_service import (
    RouteRecommendation,
    RouteRiskAnalysis,
    RouteRiskItem,
)
from services.tmap_service import PedestrianRoute


PRIMARY_ROUTE = PedestrianRoute(
    distance_m=500,
    duration_sec=420,
    route_coordinates=[
        (37.2792, 127.9001),
        (37.2800, 127.9010),
        (37.2822, 127.9031),
    ],
    guide_points=[],
    raw_geojson={"type": "FeatureCollection", "features": []},
)

SAFE_ROUTE = PedestrianRoute(
    distance_m=650,
    duration_sec=520,
    route_coordinates=[
        (37.2792, 127.9001),
        (37.2810, 127.9003),
        (37.2822, 127.9031),
    ],
    guide_points=[],
    raw_geojson={"type": "FeatureCollection", "features": []},
)

REPORT_ITEM = RouteRiskItem(
    source_type="user_report",
    source_id=77,
    risk_type="flood",
    title="최근 사용자 신고 · 침수 위험",
    risk_score=10,
    reason="최근 신고 위험 구역이 경로와 겹칩니다.",
    latitude=37.2800,
    longitude=127.9010,
    distance_to_route_m=3.2,
    influence_radius_m=50,
    recent_report=True,
    report_description="보행로에 물이 고여 있습니다.",
    report_created_at="2026-06-18T09:00:00+00:00",
    duplicate_count=2,
)

PRIMARY_ANALYSIS = RouteRiskAnalysis(
    total_score=10,
    items=[REPORT_ITEM],
    category_scores={"user_report": 10},
    has_recent_report=True,
)

SAFE_ANALYSIS = RouteRiskAnalysis(
    total_score=0,
    items=[],
    category_scores={},
    has_recent_report=False,
)


def make_recommendation() -> RouteRecommendation:
    return RouteRecommendation(
        primary_route=PRIMARY_ROUTE,
        primary_analysis=PRIMARY_ANALYSIS,
        alternative_route=SAFE_ROUTE,
        alternative_analysis=SAFE_ANALYSIS,
        alternative_pass_points=[(37.2810, 127.9003)],
    )


@dataclass
class FakeResponse:
    data: Any


class FakeRpcCall:
    def __init__(self, response: FakeResponse):
        self.response = response

    def execute(self) -> FakeResponse:
        return self.response


class FakeClient:
    def __init__(self, response_data: Any = None, error: Exception | None = None):
        self.response_data = response_data
        self.error = error
        self.rpc_name = ""
        self.rpc_params: Dict[str, Any] = {}

    def rpc(self, name: str, params: Dict[str, Any]) -> FakeRpcCall:
        self.rpc_name = name
        self.rpc_params = params
        if self.error:
            raise self.error
        return FakeRpcCall(FakeResponse(self.response_data))


class RoutePersistenceServiceTest(unittest.TestCase):
    def test_payload_geojson_uses_lng_lat_coordinate_order(self) -> None:
        payloads = build_route_result_payloads(
            recommendation=make_recommendation(),
            start=(37.2792, 127.9001),
            end=(37.2822, 127.9031),
            start_name="출발",
            end_name="도착",
        )

        primary_payload = next(
            payload for payload in payloads
            if payload["route_geojson"]["properties"]["route_role"] == "primary"
        )
        coordinates = primary_payload["route_geojson"]["geometry"]["coordinates"]
        self.assertEqual(coordinates[0], [127.9001, 37.2792])
        self.assertEqual(primary_payload["route_geojson"]["geometry"]["type"], "LineString")

    def test_safer_alternative_is_saved_as_best(self) -> None:
        payloads = build_route_result_payloads(
            recommendation=make_recommendation(),
            start=(37.2792, 127.9001),
            end=(37.2822, 127.9031),
            start_name="출발",
            end_name="도착",
        )

        alternative_payload = next(
            payload for payload in payloads
            if payload["route_geojson"]["properties"]["route_role"] == "alternative"
        )
        primary_payload = next(
            payload for payload in payloads
            if payload["route_geojson"]["properties"]["route_role"] == "primary"
        )

        self.assertEqual(alternative_payload["result_type"], "best")
        self.assertEqual(primary_payload["result_type"], "alternative_1")
        self.assertEqual(alternative_payload["total_risk_score"], 0)

    def test_risk_detail_keeps_report_description_and_time(self) -> None:
        payloads = build_route_result_payloads(
            recommendation=make_recommendation(),
            start=(37.2792, 127.9001),
            end=(37.2822, 127.9031),
            start_name="출발",
            end_name="도착",
        )
        primary_payload = next(
            payload for payload in payloads
            if payload["route_geojson"]["properties"]["route_role"] == "primary"
        )
        reason = primary_payload["risk_details"][0]["reason"]

        self.assertIn("보행로에 물이", reason)
        self.assertIn("2026-06-18", reason)
        self.assertIn("누적 신고: 2건", reason)

    def test_calls_transaction_rpc_and_parses_ids(self) -> None:
        client = FakeClient(
            response_data={
                "search_log_id": 100,
                "route_results": [
                    {"id": 201, "result_type": "alternative_1"},
                    {"id": 202, "result_type": "best"},
                ],
            }
        )

        summary = save_route_recommendation(
            client=client,
            recommendation=make_recommendation(),
            start=(37.2792, 127.9001),
            end=(37.2822, 127.9031),
            start_name="출발",
            end_name="도착",
        )

        self.assertEqual(client.rpc_name, "save_route_recommendation")
        self.assertEqual(len(client.rpc_params["p_results"]), 2)
        self.assertEqual(summary.search_log_id, 100)
        self.assertEqual(summary.route_result_ids["best"], 202)
        self.assertEqual(summary.route_count, 2)
        self.assertEqual(summary.risk_detail_count, 1)

    def test_explains_missing_rpc_function(self) -> None:
        client = FakeClient(error=RuntimeError("Could not find the function save_route_recommendation in schema cache"))

        with self.assertRaises(RoutePersistenceError) as context:
            save_route_recommendation(
                client=client,
                recommendation=make_recommendation(),
                start=(37.2792, 127.9001),
                end=(37.2822, 127.9031),
                start_name="출발",
                end_name="도착",
            )

        self.assertIn("sql/route_persistence.sql", str(context.exception))


if __name__ == "__main__":
    unittest.main()
