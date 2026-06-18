import unittest


class AppTest(unittest.TestCase):
    def test_recommend_routes_endpoint_returns_matching_routes(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/recommend-routes",
            json={
                "selected_tags": ["想一个人静静"],
                "user_text": "今天想一个人慢慢走",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("routes", data)
        self.assertGreaterEqual(len(data["routes"]), 1)
        self.assertEqual(data["routes"][0]["route_id"], "R03")


if __name__ == "__main__":
    unittest.main()
