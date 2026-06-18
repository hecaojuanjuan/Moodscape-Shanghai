import unittest


class AppTest(unittest.TestCase):
    def test_generate_script_endpoint_returns_route_and_mock_script(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/generate-script",
            json={
                "selected_tags": ["独处", "治愈"],
                "user_text": "我今天有点累，想一个人慢慢走",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("route", data)
        self.assertIn("script", data)
        self.assertIn("安静城市漫步路线", data["script"])

        route = data["route"]
        self.assertEqual(route["route_id"], "route_001")
        self.assertGreater(route["score"], 0)
        self.assertIn("matched_tags", route)
        self.assertGreaterEqual(len(route["spots"]), 1)

        for spot in route["spots"]:
            self.assertIn("name", spot)
            self.assertIn("description", spot)
            self.assertIn("lat", spot)
            self.assertIn("lng", spot)

    def test_recommend_routes_endpoint_remains_available(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/recommend-routes",
            json={
                "selected_tags": ["独处"],
                "user_text": "想一个人安静散步",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("routes", data)
        self.assertEqual(data["routes"][0]["route_id"], "route_001")


if __name__ == "__main__":
    unittest.main()
