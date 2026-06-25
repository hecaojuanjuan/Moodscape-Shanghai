import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import Workbook

from services.excel_data import load_excel_data
from services.recommender import (
    _experience_tag_score,
    load_routes,
    load_tags,
    recommend_route,
    recommend_routes,
)


class RecommenderTest(unittest.TestCase):
    MINDSET_LABELS = ["独处", "疗愈", "灵感", "怀旧", "成长", "浪漫", "探索", "社交"]

    def test_excel_loader_uses_workbook_as_source_of_truth(self):
        data = load_excel_data()
        routes = data["routes"]
        tags = data["tags"]

        self.assertEqual(len(routes), 28)
        self.assertEqual(sum(len(route["spots"]) for route in routes), 102)
        self.assertEqual(len(data["spots"]), 102)
        self.assertEqual(len(tags), 15)
        self.assertEqual(data["mindset_tags"], self.MINDSET_LABELS)

        self.assertEqual([tag["user_button_text"] for tag in tags[:3]], ["一个人静静", "夜景治愈", "拍照出片"])
        self.assertEqual(tags[0]["recommended_routes"], ["R03", "R13", "R14", "R16", "R20"])

        bund_route = next(route for route in routes if route["route_id"] == "R01")
        self.assertEqual(bund_route["primary_emotion_tags"], ["想被夜景治愈", "想认识上海第一面"])
        self.assertEqual(bund_route["spots"][0]["lat"], 31.238056)
        self.assertEqual(bund_route["spots"][0]["lng"], 121.486111)
        self.assertEqual(set(bund_route["mindset_scores"]), set(self.MINDSET_LABELS))
        self.assertIn("source_note", bund_route["spots"][0])

    def test_excel_loader_keeps_unassigned_spots_in_spot_pool(self):
        with TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "spots.xlsx"
            _write_minimal_workbook(workbook_path)
            load_excel_data.cache_clear()

            data = load_excel_data(workbook_path)

        self.assertEqual([spot["spot_id"] for spot in data["spots"]], ["S001", "S999"])
        self.assertEqual([spot["spot_id"] for spot in data["routes"][0]["spots"]], ["S001"])
        self.assertEqual(data["spots"][1]["route_id"], "")
        self.assertEqual(data["spots"][1]["name"], "新加入的安静花园")

    def test_compat_loaders_read_excel_not_static_json(self):
        self.assertEqual(len(load_routes()), 28)
        self.assertEqual(len(load_tags()), 15)

    def test_recommend_routes_returns_three_excel_candidates_with_distinct_match_percent(self):
        routes = recommend_routes(selected_tags=["疗愈"], user_text="")

        self.assertEqual(len(routes), 3)
        self.assertEqual(routes[0]["route_id"], "R26")
        self.assertEqual(routes[0]["route_name"], "松江郊野文化疗愈线")
        self.assertNotIn("动态组合线", routes[0]["route_name"])
        self.assertIn("is_dynamic", routes[0])
        self.assertIn("route_distance_km", routes[0])
        self.assertIn("疗愈", routes[0]["matched_mindsets"])

        percents = [route["match_percent"] for route in routes]
        self.assertTrue(all(0 < percent < 100 for percent in percents))
        self.assertGreater(len(set(percents)), 1)
        self.assertEqual(percents, sorted(percents, reverse=True))

        for route in routes:
            self.assertFalse(route["route_id"].startswith("DYN-"))
            self.assertNotIn("动态组合线", route["route_name"])
            self.assertGreater(len(route["spots"]), 0)
            self.assertIn("match_reason", route)
            self.assertIn("suggested_card_copy", route)

    def test_match_percent_uses_fixed_scale_instead_of_current_top_route(self):
        data = load_excel_data()
        top_percents = [
            recommend_routes(selected_tags=[tag["emotion_tag"]], user_text="")[0]["match_percent"]
            for tag in data["tags"][:5]
        ]

        self.assertNotIn(96, top_percents)
        self.assertGreater(len(set(top_percents)), 1)

    def test_selected_excel_tag_uses_mapping_priority_and_reasons(self):
        routes = recommend_routes(selected_tags=["想一个人静静"], user_text="")

        self.assertEqual([route["route_id"] for route in routes], ["R03", "R13", "R14"])
        self.assertEqual(routes[0]["route_name"], "武康路书香独处线")
        self.assertNotIn("动态组合线", routes[0]["route_name"])
        self.assertGreater(routes[0]["match_percent"], 90)
        self.assertIn("想一个人静静", routes[0]["matched_tags"])
        self.assertIn("武康大楼", routes[0]["match_reason"])
        self.assertIn("文学故居", routes[0]["suggested_card_copy"])

    def test_selected_tag_score_outweighs_qwen_inferred_tag_score(self):
        data = load_excel_data()
        route = next(route for route in data["routes"] if route["route_id"] == "R03")
        mapping_by_pair = {
            (mapping["emotion_tag"], mapping["route_id"]): mapping
            for mapping in data["mappings"]
        }

        selected_score, _ = _experience_tag_score(
            route,
            "想一个人静静",
            mapping_by_pair,
            selected=True,
        )
        inferred_score, _ = _experience_tag_score(
            route,
            "想一个人静静",
            mapping_by_pair,
            selected=False,
        )

        self.assertGreater(selected_score, inferred_score)

    def test_qwen_inferred_tags_participate_with_text_match_weight(self):
        routes = recommend_routes(
            selected_tags=[],
            inferred_experience_tags=["想被夜景治愈"],
            user_text="这是一句不会命中 Excel 关键词的描述",
        )

        self.assertEqual(routes[0]["route_id"], "R01")
        self.assertIn("想被夜景治愈", routes[0]["matched_tags"])

    def test_user_text_matches_only_excel_fields(self):
        routes = recommend_routes(selected_tags=[], user_text="低噪音 慢节奏 可独处 可停留")

        self.assertEqual(routes[0]["route_id"], "R03")
        self.assertEqual(routes[0]["route_name"], "武康路书香独处线")
        self.assertNotIn("动态组合线", routes[0]["route_name"])
        self.assertIn("想一个人静静", routes[0]["matched_tags"])

    def test_dynamic_routes_can_insert_nearby_unassigned_spot_into_seed_route(self):
        seed_spots = [
            _spot("S001", "安静书店", 31.2000, 121.4400, route_id="R01"),
            _spot("S002", "邻近花园", 31.2010, 121.4410, route_id="R01"),
            _spot("S003", "街角咖啡", 31.2020, 121.4420, route_id="R01"),
        ]
        data = _dynamic_test_data(
            seed_spots
            + [
                _spot("S999", "新加入的安静花园", 31.2005, 121.4405, route_id=""),
            ],
            routes=[_seed_route("R01", "旧版安静路线", seed_spots)],
        )

        with patch("services.recommender.load_excel_data", return_value=data):
            routes = recommend_routes(selected_tags=["想一个人静静"], user_text="", limit=1)

        self.assertEqual(routes[0]["route_id"], "R01")
        self.assertEqual(routes[0]["route_name"], "旧版安静路线")
        self.assertNotIn("动态组合线", routes[0]["route_name"])
        self.assertTrue(routes[0]["is_dynamic"])
        spot_names = [spot["name"] for spot in routes[0]["spots"]]
        self.assertIn("新加入的安静花园", spot_names)
        self.assertGreaterEqual(len([spot for spot in routes[0]["spots"] if spot["route_id"] == "R01"]), 2)
        self.assertEqual(routes[0]["source_route_ids"], ["R01"])
        self.assertGreater(routes[0]["match_percent"], 90)

    def test_dynamic_routes_reject_far_unassigned_spots_and_keep_seed_route(self):
        seed_spots = [
            _spot("S001", "安静书店", 31.2000, 121.4400, route_id="R01"),
            _spot("S002", "邻近花园", 31.2010, 121.4410, route_id="R01"),
            _spot("S003", "街角咖啡", 31.2020, 121.4420, route_id="R01"),
        ]
        data = _dynamic_test_data(
            seed_spots
            + [
                _spot("S900", "远方森林", 30.1000, 120.1000, route_id="R99"),
            ],
            routes=[_seed_route("R01", "旧版安静路线", seed_spots)],
        )

        with patch("services.recommender.load_excel_data", return_value=data):
            routes = recommend_routes(selected_tags=["想一个人静静"], user_text="", limit=1)

        spot_names = [spot["name"] for spot in routes[0]["spots"]]
        self.assertEqual(spot_names, ["安静书店", "邻近花园", "街角咖啡"])
        self.assertFalse(routes[0]["is_dynamic"])
        self.assertLess(routes[0]["route_distance_km"], 1)

    def test_recommend_routes_falls_back_to_seed_routes_when_dynamic_spots_are_insufficient(self):
        seed_spots = [
            _spot("S001", "安静书店", 31.2000, 121.4400, route_id="R01"),
            _spot("S002", "邻近花园", 31.2010, 121.4410, route_id="R01"),
        ]
        data = _dynamic_test_data(seed_spots)
        data["routes"] = [_seed_route("R01", "旧版安静路线", seed_spots)]

        with patch("services.recommender.load_excel_data", return_value=data):
            routes = recommend_routes(selected_tags=["想一个人静静"], user_text="", limit=1)

        self.assertEqual(routes[0]["route_id"], "R01")
        self.assertFalse(routes[0]["is_dynamic"])
        self.assertEqual(routes[0]["source_route_ids"], ["R01"])
        self.assertIn("route_distance_km", routes[0])

    def test_profile_answers_do_not_trigger_recommendations_without_current_input(self):
        routes = recommend_routes(
            selected_tags=[],
            user_text="",
            profile_answers={
                "pace": "slow_stop",
                "healing_space": "quiet_street",
                "shanghai_style": "old_shanghai",
            },
        )

        self.assertEqual(routes, [])

    def test_profile_similarity_enhances_triggered_recommendations(self):
        routes = recommend_routes(
            selected_tags=["想一个人静静"],
            user_text="",
            profile_answers={
                "pace": "slow_stop",
                "healing_space": "quiet_street",
                "shanghai_style": "old_shanghai",
                "companion": "solo",
                "travel_persona": "low_stimulation",
            },
        )

        self.assertEqual(len(routes), 3)
        self.assertGreater(routes[0]["profile_similarity"], 0)
        self.assertIn("慢节奏", routes[0]["matched_profile_traits"])
        self.assertIn("profile_similarity", routes[0])
        self.assertIn("matched_profile_traits", routes[0])

    def test_recommend_route_keeps_first_route_compatibility(self):
        route = recommend_route(selected_tags=["想被夜景治愈"], user_text="")

        self.assertEqual(route["route_id"], "R01")
        self.assertEqual(route["route_name"], "外滩初见上海线")
        self.assertNotIn("动态组合线", route["route_name"])
        self.assertIn("想被夜景治愈", route["matched_tags"])
        self.assertIn("match_percent", route)


def _write_minimal_workbook(path):
    workbook = Workbook()
    routes = workbook.active
    routes.title = "Routes"
    spots = workbook.create_sheet("Spots")
    tags = workbook.create_sheet("Tags")
    mappings = workbook.create_sheet("Mappings")

    _write_table(
        routes,
        [
            "route_id",
            "route_name",
            "route_intro_user_facing",
            "primary_emotion_tags",
            "secondary_emotion_tags",
            "backend_scene_tags",
            "suitable_mood",
            "estimated_time",
            "budget_level",
            "route_spots",
            "ai_script_angle",
        ],
        [
            {
                "route_id": "R01",
                "route_name": "安静种子线",
                "route_intro_user_facing": "一条用于测试的安静路线",
                "primary_emotion_tags": "想一个人静静",
                "backend_scene_tags": "独处；阅读",
                "estimated_time": "2小时",
                "budget_level": "低",
                "route_spots": "安静书店",
            }
        ],
    )
    _write_table(
        spots,
        [
            "spot_id",
            "route_id",
            "spot_order",
            "spot_name",
            "district",
            "经纬度（WGS84）",
            "emotion_tags",
            "scene_tags",
            "user_experience_value",
            "open_time",
            "ticket_reservation",
            "feedback_keywords",
            "source_note",
            "source_url",
            "update_note",
            "地址",
            "安静度 Quietness",
            "自然度 Nature",
            "文化度 Culture",
            "艺术度 Art",
            "学习度 Learning",
            "社交度 Social",
            "探索度 Exploration",
            "心境指数（图1百分比计算）",
        ],
        [
            {
                "spot_id": "S001",
                "route_id": "R01",
                "spot_order": 1,
                "spot_name": "安静书店",
                "district": "徐汇区",
                "经纬度（WGS84）": "31.2000, 121.4400",
                "emotion_tags": "想一个人静静",
                "scene_tags": "独处；阅读",
                "user_experience_value": "适合慢慢阅读",
                "安静度 Quietness": 9,
                "心境指数（图1百分比计算）": "独处:90；疗愈:80",
            },
            {
                "spot_id": "S999",
                "route_id": "",
                "spot_order": 1,
                "spot_name": "新加入的安静花园",
                "district": "徐汇区",
                "经纬度（WGS84）": "31.2010, 121.4410",
                "emotion_tags": "想一个人静静",
                "scene_tags": "独处；花园",
                "user_experience_value": "新增但还没有归入路线的点位",
                "安静度 Quietness": 8,
                "心境指数（图1百分比计算）": "独处:88；疗愈:82",
            },
        ],
    )
    _write_table(
        tags,
        [
            "tag_id",
            "emotion_tag",
            "user_button_text",
            "user_state",
            "experience_need",
            "recommended_routes",
            "example_spots",
            "website_display_copy",
            "ai_script_tone",
            "backend_scene_tags",
        ],
        [
            {
                "tag_id": "E01",
                "emotion_tag": "想一个人静静",
                "user_button_text": "一个人静静",
                "experience_need": "低噪音、慢节奏、可独处",
                "backend_scene_tags": "独处；阅读",
            }
        ],
    )
    _write_table(mappings, ["tag_id", "emotion_tag", "route_id", "route_name", "priority", "match_reason", "suggested_card_copy"], [])
    workbook.save(path)


def _write_table(sheet, headers, rows):
    for column, header in enumerate(headers, 1):
        sheet.cell(row=4, column=column, value=header)
    for row_index, row in enumerate(rows, 5):
        for column, header in enumerate(headers, 1):
            sheet.cell(row=row_index, column=column, value=row.get(header))


def _dynamic_test_data(spots, routes=None):
    return {
        "routes": routes or [],
        "spots": spots,
        "tags": [
            {
                "tag_id": "E01",
                "emotion_tag": "想一个人静静",
                "user_button_text": "一个人静静",
                "user_state": "想安静",
                "experience_need": "低噪音 慢节奏 可独处",
                "recommended_routes": [],
                "example_spots": [],
                "website_display_copy": "慢慢走",
                "ai_script_tone": "安静",
                "backend_scene_tags": ["独处", "阅读"],
            }
        ],
        "mappings": [
            {
                "tag_id": "E01",
                "emotion_tag": "想一个人静静",
                "route_id": "R01",
                "route_name": "旧版安静路线",
                "priority": 1,
                "match_reason": "旧版路线的安静点位很适合独处。",
                "suggested_card_copy": "保留原路线的安静骨架。",
            }
        ],
        "mindset_tags": ["独处", "疗愈"],
    }


def _spot(spot_id, name, lat, lng, route_id):
    return {
        "spot_id": spot_id,
        "route_id": route_id,
        "spot_order": 1,
        "name": name,
        "description": f"{name}适合低噪音慢节奏停留",
        "district": "徐汇区",
        "lat": lat,
        "lng": lng,
        "emotion_tags": ["想一个人静静"],
        "scene_tags": ["独处", "阅读"],
        "open_time": "全天",
        "ticket_reservation": "免费",
        "feedback_keywords": ["低噪音", "慢节奏", "可独处"],
        "source_note": "",
        "source_url": "",
        "update_note": "",
        "address": name,
        "feature_scores": {
            "quietness": 9,
            "nature": 4,
            "culture": 5,
            "art": 3,
            "learning": 5,
            "social": 1,
            "exploration": 4,
        },
        "mindset_scores": {"独处": 90, "疗愈": 80},
    }


def _seed_route(route_id, name, spots):
    return {
        "route_id": route_id,
        "route_name": name,
        "route_intro_user_facing": "旧版路线兜底",
        "reason": "旧版路线兜底",
        "primary_emotion_tags": ["想一个人静静"],
        "secondary_emotion_tags": [],
        "backend_scene_tags": ["独处", "阅读"],
        "tags": ["想一个人静静"],
        "suitable_mood": "安静独处",
        "estimated_time": "2小时",
        "budget_level": "低",
        "route_spots": "安静书店 → 邻近花园",
        "ai_script_angle": "安静兜底",
        "spots": spots,
        "mindset_scores": {"独处": 90, "疗愈": 80},
        "dominant_mindsets": ["独处", "疗愈"],
    }


if __name__ == "__main__":
    unittest.main()
