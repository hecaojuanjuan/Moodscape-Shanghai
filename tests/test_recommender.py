import json
import tempfile
import unittest
from pathlib import Path


class RecommenderTest(unittest.TestCase):
    def test_recommend_routes_prioritizes_matching_tags_and_text(self):
        from services.recommender import recommend_routes

        routes = [
            {
                "route_id": "R01",
                "route_name": "外滩初见上海线",
                "tags": ["想被夜景治愈", "想认识上海第一面"],
                "reason": "第一次来上海，先从外滩、南京路和豫园进入这座城市。",
                "spots": [],
                "estimated_time": "3-4小时",
                "budget_level": "低-中",
            },
            {
                "route_id": "R03",
                "route_name": "武康路书香独处线",
                "tags": ["想一个人静静", "想慢慢走不赶路", "想找回老上海"],
                "reason": "从武康大楼走到书院与文学故居，在梧桐树影里把节奏放下来。",
                "spots": [],
                "estimated_time": "2-3小时",
                "budget_level": "低",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            routes_path = Path(tmpdir) / "routes.json"
            routes_path.write_text(json.dumps(routes, ensure_ascii=False), encoding="utf-8")

            recommended = recommend_routes(
                selected_tags=["想一个人静静"],
                user_text="今天想一个人慢慢走，不赶路",
                routes_path=routes_path,
            )

        self.assertEqual(recommended[0]["route_id"], "R03")


if __name__ == "__main__":
    unittest.main()
