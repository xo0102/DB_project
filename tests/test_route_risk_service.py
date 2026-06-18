from __future__ import annotations

import unittest
from typing import Any

from services.route_risk_service import (
    RouteRiskContext,
    analyze_route_risk,
    build_detour_pass_points,
    create_route_recommendation,
)
from services.tmap_service import PedestrianRoute


PRIMARY_ROUTE = PedestrianRoute(
    distance_m=1000,
    duration_sec=720,
    route_coordinates=[
        (37.0000, 127.0000),
        (37.0000, 127.0050),
        (37.0000, 127.0100),
    ],
    guide_points=[],
    raw_geojson={"type": "FeatureCollection", "features": []},
)

SAFE_ROUTE = PedestrianRoute(
    distance_m=1300,
    duration_sec=900,
    route_coordinates=[
        (37.0000, 127.0000),
        (37.0020, 127.0020),
        (37.0020, 127.0080),
        (37.0000, 127.0100),
    ],
    guide_points=[],
    raw_geojson={"type": "FeatureCollection", "features": []},
)


class RouteRiskServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.context = RouteRiskContext(
            report_zones=[
                {
                    "id": 10,
                    "report_id": 100,
                    "risk_type": "flood",
                    "center_lat": 37.0000,
                    "center_lng": 127.0050,
                    "radius_m": 50,
                    "risk_score": 10,
                    "report": {
                        "id": 100,
                        "risk_type": "flood",
                        "description": "보행로에 물이 고여 있습니다.",
                        "duplicate_count": 2,
                        "created_at": "2026-06-18T09:00:00+00:00",
                    },
                }
            ],
            flood_zones=[],
            road_alerts=[],
            weather=None,
        )

    def test_recent_report_triggers_alternative_even_below_50(self) -> None:
        analysis = analyze_route_risk(PRIMARY_ROUTE.route_coordinates, self.context)

        self.assertEqual(analysis.total_score, 10)
        self.assertTrue(analysis.has_recent_report)
        self.assertTrue(analysis.should_offer_alternative)
        self.assertEqual(analysis.recent_report_count, 1)
        self.assertIn("물이 고여", analysis.items[0].report_description)

    def test_builds_detour_pass_point(self) -> None:
        analysis = analyze_route_risk(PRIMARY_ROUTE.route_coordinates, self.context)
        pass_points = build_detour_pass_points(
            PRIMARY_ROUTE.route_coordinates,
            analysis.spatial_items,
            side=1,
            extra_clearance_m=60,
        )

        self.assertEqual(len(pass_points), 1)
        self.assertNotAlmostEqual(pass_points[0][0], 37.0000, places=5)

    def test_selects_route_without_recent_report(self) -> None:
        calls: list[dict[str, Any]] = []

        def fake_searcher(**kwargs: Any) -> PedestrianRoute:
            calls.append(kwargs)
            self.assertTrue(kwargs.get("pass_points"))
            return SAFE_ROUTE

        recommendation = create_route_recommendation(
            primary_route=PRIMARY_ROUTE,
            context=self.context,
            app_key="test-key",
            start=(37.0000, 127.0000),
            end=(37.0000, 127.0100),
            start_name="출발",
            end_name="도착",
            route_searcher=fake_searcher,
        )

        self.assertTrue(calls)
        self.assertIsNotNone(recommendation.alternative_route)
        self.assertIsNotNone(recommendation.alternative_analysis)
        self.assertFalse(recommendation.alternative_analysis.has_recent_report)
        self.assertTrue(recommendation.alternative_fully_avoids_trigger)

    def test_collapses_duplicate_flood_zones_at_same_location(self) -> None:
        context = RouteRiskContext(
            flood_zones=[
                {
                    "id": 1,
                    "zone_name": "학교 정문 침수 예상 구역",
                    "center_lat": 37.0000,
                    "center_lng": 127.0050,
                    "base_score": 30,
                    "risk_level": "high",
                },
                {
                    "id": 2,
                    "zone_name": "학교 정문 침수 이력 구역",
                    "center_lat": 37.0000,
                    "center_lng": 127.0050,
                    "base_score": 30,
                    "risk_level": "high",
                },
                {
                    "id": 3,
                    "zone_name": "학교 정문 침수 중복 데이터",
                    "center_lat": 37.0000,
                    "center_lng": 127.0050,
                    "base_score": 30,
                    "risk_level": "high",
                },
            ],
            weather={"id": 1, "risk_score": 20},
        )

        analysis = analyze_route_risk(PRIMARY_ROUTE.route_coordinates, context)

        flood_items = [item for item in analysis.items if item.source_type == "flood_zone"]
        self.assertEqual(len(flood_items), 1)
        self.assertEqual(flood_items[0].raw_risk_score, 30)
        self.assertEqual(flood_items[0].risk_score, 30)
        self.assertIn("중복 데이터 3건", flood_items[0].reason)
        self.assertEqual(analysis.category_scores["flood_zone"], 30)
        self.assertEqual(analysis.total_score, 50)

    def test_applies_category_caps_without_exceeding_100(self) -> None:
        context = RouteRiskContext(
            report_zones=[
                {
                    "id": 10,
                    "report_id": 100,
                    "risk_type": "flood",
                    "center_lat": 37.0000,
                    "center_lng": 127.0040,
                    "radius_m": 60,
                    "risk_score": 20,
                    "report": {
                        "id": 100,
                        "description": "통행이 어렵습니다.",
                        "duplicate_count": 5,
                    },
                }
            ],
            flood_zones=[
                {
                    "id": 1,
                    "zone_name": "침수 구역 A",
                    "center_lat": 37.0000,
                    "center_lng": 127.0030,
                    "base_score": 30,
                },
                {
                    "id": 2,
                    "zone_name": "침수 구역 B",
                    "center_lat": 37.0000,
                    "center_lng": 127.0070,
                    "base_score": 30,
                },
            ],
            road_alerts=[
                {
                    "id": 1,
                    "title": "도로 통제 A",
                    "alert_type": "road_control",
                    "center_lat": 37.0000,
                    "center_lng": 127.0020,
                    "risk_score": 20,
                    "description": "통제 중",
                },
                {
                    "id": 2,
                    "title": "도로 통제 B",
                    "alert_type": "road_control",
                    "center_lat": 37.0000,
                    "center_lng": 127.0080,
                    "risk_score": 20,
                    "description": "통제 중",
                },
            ],
            weather={"id": 1, "risk_score": 20},
        )

        analysis = analyze_route_risk(PRIMARY_ROUTE.route_coordinates, context)

        self.assertEqual(analysis.category_scores["flood_zone"], 50)
        self.assertEqual(analysis.category_scores["road_alert"], 20)
        self.assertEqual(analysis.category_scores["user_report"], 10)
        self.assertEqual(analysis.category_scores["weather"], 20)
        self.assertEqual(analysis.total_score, 100)
        self.assertEqual(sum(item.risk_score for item in analysis.items), 100)
        self.assertTrue(any(item.raw_risk_score > item.risk_score for item in analysis.items))


if __name__ == "__main__":
    unittest.main()
