from __future__ import annotations

import unittest

from services.tmap_service import TmapApiError, parse_pedestrian_response


SAMPLE_RESPONSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [127.9001, 37.2792]},
            "properties": {
                "index": 0,
                "totalDistance": 420,
                "totalTime": 360,
                "description": "출발지",
                "pointType": "SP",
            },
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [127.9001, 37.2792],
                    [127.9010, 37.2800],
                ],
            },
            "properties": {"index": 1, "distance": 200, "time": 180},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [127.9010, 37.2800]},
            "properties": {
                "index": 2,
                "description": "오른쪽 방향으로 이동",
                "pointType": "GP",
            },
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [127.9010, 37.2800],
                    [127.9031, 37.2822],
                ],
            },
            "properties": {"index": 3, "distance": 220, "time": 180},
        },
    ],
}


class ParsePedestrianResponseTest(unittest.TestCase):
    def test_parses_totals_and_merges_linestrings(self) -> None:
        result = parse_pedestrian_response(SAMPLE_RESPONSE)

        self.assertEqual(result.distance_m, 420)
        self.assertEqual(result.duration_sec, 360)
        self.assertEqual(
            result.route_coordinates,
            [
                (37.2792, 127.9001),
                (37.2800, 127.9010),
                (37.2822, 127.9031),
            ],
        )
        self.assertEqual(len(result.guide_points), 2)

    def test_rejects_empty_features(self) -> None:
        with self.assertRaises(TmapApiError):
            parse_pedestrian_response({"type": "FeatureCollection", "features": []})


if __name__ == "__main__":
    unittest.main()
