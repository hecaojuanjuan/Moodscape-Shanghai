import unittest


class AppTest(unittest.TestCase):
    def test_generate_script_endpoint_returns_excel_route_and_mock_script(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/generate-script",
            json={
                "selected_tags": ["想一个人静静"],
                "user_text": "我今天有点累，想一个人慢慢走",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("route", data)
        self.assertIn("script", data)
        self.assertIn("matched_tags", data)
        self.assertIn("matched_mindsets", data)
        self.assertIn("recommendation_reason", data)
        self.assertIn("spots", data)

        route = data["route"]
        self.assertEqual(route["route_id"], "R03")
        self.assertEqual(route["route_name"], "武康路书香独处线")
        self.assertIn("想一个人静静", route["matched_tags"])
        self.assertIn("独处", data["matched_mindsets"])
        self.assertEqual(data["spots"], route["spots"])
        self.assertEqual(data["recommendation_reason"], route["reason"])
        self.assertIn("武康路书香独处线", data["script"])
        self.assertGreaterEqual(len(route["spots"]), 3)

        for spot in route["spots"]:
            self.assertIn("name", spot)
            self.assertIn("description", spot)
            self.assertIn("lat", spot)
            self.assertIn("lng", spot)

    def test_generate_script_endpoint_accepts_mindset_tag(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/generate-script",
            json={
                "selected_tags": ["疗愈"],
                "user_text": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        route = data["route"]

        self.assertEqual(route["route_id"], "R26")
        self.assertIn("疗愈", data["matched_mindsets"])
        self.assertEqual(data["spots"], route["spots"])
        self.assertIn("Mock AI", data["script"])

    def test_static_tags_json_is_available_to_frontend(self):
        from app import app

        client = app.test_client()
        response = client.get("/static/data/tags.json")

        self.assertEqual(response.status_code, 200)
        tags = response.get_json()
        response.close()
        self.assertEqual(len(tags), 15)
        self.assertEqual(tags[0]["emotion_tag"], "想一个人静静")
        self.assertEqual(tags[0]["user_button_text"], "一个人静静")

    def test_recommend_routes_endpoint_remains_available(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/recommend-routes",
            json={
                "selected_tags": ["想被夜景治愈"],
                "user_text": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("routes", data)
        self.assertEqual(data["routes"][0]["route_id"], "R01")


if __name__ == "__main__":
    unittest.main()
