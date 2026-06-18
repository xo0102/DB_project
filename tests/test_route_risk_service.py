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


if __name__ == "__main__":
    unittest.main()
