import json
import unittest
from types import SimpleNamespace

from services.qwen_service import QwenService


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=response),
                )
            ]
        )


class FakeClient:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


class QwenServiceTest(unittest.TestCase):
    def test_analyze_intent_filters_unknown_tags_and_returns_qwen_source(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "summary": "想安静地慢慢走",
                        "experience_tags": ["想一个人静静", "不存在的标签"],
                        "mindset_tags": ["疗愈", "未知心境"],
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        intent = service.analyze_intent(
            "今天有点累，想一个人慢慢走",
            allowed_experience_tags=["想一个人静静", "想慢慢走不赶路"],
            allowed_mindset_tags=["独处", "疗愈"],
        )

        self.assertEqual(intent["summary"], "想安静地慢慢走")
        self.assertEqual(intent["inferred_experience_tags"], ["想一个人静静"])
        self.assertEqual(intent["inferred_mindset_tags"], ["疗愈"])
        self.assertEqual(intent["source"], "qwen")

    def test_analyze_intent_falls_back_on_invalid_json_or_timeout(self):
        for response in ["not-json", TimeoutError("timed out")]:
            with self.subTest(response=response):
                service = QwenService(
                    api_key="test-key",
                    client=FakeClient([response]),
                )

                intent = service.analyze_intent(
                    "想看夜景",
                    allowed_experience_tags=["想被夜景治愈"],
                    allowed_mindset_tags=["浪漫"],
                )

                self.assertEqual(intent["summary"], "想看夜景")
                self.assertEqual(intent["inferred_experience_tags"], [])
                self.assertEqual(intent["inferred_mindset_tags"], [])
                self.assertEqual(intent["source"], "fallback")

    def test_disabled_service_returns_fallback_without_calling_api(self):
        service = QwenService(api_key="", client=FakeClient([]))

        intent = service.analyze_intent(
            "想看展",
            allowed_experience_tags=["想看展充电"],
            allowed_mindset_tags=["灵感"],
        )
        scripts = service.generate_route_scripts(
            routes=[_route("R01", "测试路线")],
            user_text="想看展",
            intent=intent,
        )

        self.assertEqual(intent["source"], "fallback")
        self.assertEqual(scripts, {})

    def test_generate_route_scripts_returns_structured_sections_and_filters_invalid_items(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "从第一站开始慢慢走，让城市的声音慢下来。",
                                "script_title": "把自己还给自己的半日",
                                "script_opening": "如果今天的你不太想说话，这条路线会把你带进更安静的节奏。",
                                "script_role": "今天的你是一位短暂逃离日常的人。",
                                "script_sensory": {
                                    "see": "树影、街角和低饱和的城市画面。",
                                    "hear": "脚步声、风声和远处车流。",
                                    "smell": "雨后路面和植物气息。",
                                    "do": "慢走、停留、拍照、写下一句话。",
                                },
                                "script_closing": "情绪落点：这条路线会给你一个缓慢恢复的下午。",
                                "script_sections": [
                                    {
                                        "type": "opening",
                                        "title": "开场",
                                        "text": "你会从第一站进入这条安静路线。",
                                        "emotion_experience": "把疲惫放低一点，先进入安静。",
                                        "action_guide": "先把脚步放慢，不急着打卡。",
                                        "scene_image": "街角的光落在墙面上，城市声音慢下来。",
                                    },
                                    {
                                        "type": "spot",
                                        "spot_id": "S01",
                                        "spot_name": "第一站",
                                        "title": "第一幕｜第一站",
                                        "location": "第一站",
                                        "experience": "慢走、观察街角、拍一张低饱和照片。",
                                        "emotion_shift": "从紧绷切换到可停留。",
                                        "text": "先把脚步放慢，留意街角的安静。",
                                        "emotion_experience": "从紧绷切换到可停留。",
                                        "action_guide": "在第一站停一会儿，观察周围的细节。",
                                        "scene_image": "安静的街角把注意力收回来。",
                                    },
                                    {
                                        "type": "spot",
                                        "spot_id": "S02",
                                        "spot_name": "第二站",
                                        "title": "第二幕｜第二站",
                                        "location": "第二站",
                                        "experience": "继续散步，留出几分钟发呆。",
                                        "emotion_shift": "情绪继续变轻，散步开始有余地。",
                                        "text": "再把散步交给下一处可以停留的地方。",
                                        "emotion_experience": "情绪继续变轻，散步开始有余地。",
                                        "action_guide": "按原路线走到第二站，把节奏留给自己。",
                                        "scene_image": "下一处停留点像一个缓慢展开的空白。",
                                    },
                                    {
                                        "type": "closing",
                                        "title": "收束",
                                        "text": "最后把这段散步收进今天的余光里。",
                                        "emotion_experience": "把松下来的感觉带走。",
                                        "action_guide": "离开前回看这条路线里最安静的一幕。",
                                        "scene_image": "余光把一路的停顿收成一段城市记忆。",
                                    },
                                ],
                            },
                            {
                                "route_id": "R02",
                                "script": "这条路线没有合法分幕。",
                                "script_sections": [],
                            },
                            {
                                "route_id": "R99",
                                "script": "这条路线并不存在。",
                                "script_sections": [
                                    {"type": "opening", "title": "开场", "text": "不存在。"}
                                ],
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)
        routes = [_route("R01", "路线一"), _route("R02", "路线二")]
        original_routes = json.loads(json.dumps(routes, ensure_ascii=False))

        scripts = service.generate_route_scripts(
            routes=routes,
            user_text="想安静散步",
            intent={
                "summary": "安静散步",
                "inferred_experience_tags": ["想慢慢走不赶路"],
                "inferred_mindset_tags": ["疗愈"],
                "source": "qwen",
            },
        )

        self.assertEqual(set(scripts), {"R01"})
        script = scripts["R01"]
        self.assertEqual(script["script"], "从第一站开始慢慢走，让城市的声音慢下来。")
        self.assertEqual(script["script_title"], "把自己还给自己的半日")
        self.assertEqual(script["script_opening"], "如果今天的你不太想说话，这条路线会把你带进更安静的节奏。")
        self.assertEqual(script["script_role"], "今天的你是一位短暂逃离日常的人。")
        self.assertEqual(script["script_sensory"]["see"], "树影、街角和低饱和的城市画面。")
        self.assertEqual(script["script_sensory"]["hear"], "脚步声、风声和远处车流。")
        self.assertEqual(script["script_sensory"]["smell"], "雨后路面和植物气息。")
        self.assertEqual(script["script_sensory"]["do"], "慢走、停留、拍照、写下一句话。")
        self.assertIn("情绪落点", script["script_closing"])
        self.assertEqual(script["script_sections"][1]["location"], "第一站")
        self.assertEqual(script["script_sections"][1]["experience"], "慢走、观察街角、拍一张低饱和照片。")
        self.assertEqual(script["script_sections"][1]["emotion_shift"], "从紧绷切换到可停留。")
        self.assertEqual(routes, original_routes)

    def test_generate_route_scripts_prompt_includes_immersive_route_context(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "从第一站开始慢慢走，让城市的声音慢下来。",
                                "script_sections": [
                                    {"type": "opening", "title": "开场", "text": "开场。"},
                                    {
                                        "type": "spot",
                                        "spot_id": "S01",
                                        "spot_name": "第一站",
                                        "title": "第一幕｜第一站",
                                        "text": "第一幕。",
                                    },
                                    {
                                        "type": "spot",
                                        "spot_id": "S02",
                                        "spot_name": "第二站",
                                        "title": "第二幕｜第二站",
                                        "text": "第二幕。",
                                    },
                                    {"type": "closing", "title": "收束", "text": "收束。"},
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        service.generate_route_scripts(
            routes=[_route("R01", "测试路线")],
            user_text="想安静散步",
            intent={
                "summary": "安静散步",
                "inferred_experience_tags": ["想慢慢走不赶路"],
                "inferred_mindset_tags": ["疗愈"],
                "source": "qwen",
            },
        )

        request = client.completions.requests[0]
        user_prompt = request["messages"][1]["content"]
        self.assertIn("用户心境为主线", user_prompt)
        self.assertIn("不要生成普通旅游攻略", user_prompt)
        self.assertIn("剧本标题", user_prompt)
        self.assertIn("开场白", user_prompt)
        self.assertIn("角色设定", user_prompt)
        self.assertIn("分幕路线", user_prompt)
        self.assertIn("感官描写", user_prompt)
        self.assertIn("结尾收束", user_prompt)
        self.assertIn("上海独处路线推荐", user_prompt)
        self.assertIn("情绪体验", user_prompt)
        self.assertIn("行动引导", user_prompt)
        self.assertIn("场景画面", user_prompt)
        self.assertIn("ai_script_angle", user_prompt)
        self.assertIn("suitable_mood", user_prompt)
        self.assertIn("feedback_keywords", user_prompt)

    def test_generate_route_scripts_ignores_invalid_structured_response(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "这条路线缺少合法分幕。",
                                "script_sections": "not-a-list",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        scripts = service.generate_route_scripts(
            routes=[_route("R01", "路线一")],
            user_text="想安静散步",
            intent={"summary": "安静散步", "source": "qwen"},
        )

        self.assertEqual(scripts, {})

    def test_generate_route_scripts_requires_all_route_spots_in_order(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "这条路线漏掉了第二站。",
                                "script_sections": [
                                    {"type": "opening", "title": "开场", "text": "开场。"},
                                    {
                                        "type": "spot",
                                        "spot_id": "S01",
                                        "spot_name": "第一站",
                                        "title": "第一幕｜第一站",
                                        "text": "第一幕。",
                                    },
                                    {"type": "closing", "title": "收束", "text": "收束。"},
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        scripts = service.generate_route_scripts(
            routes=[_route("R01", "路线一")],
            user_text="想安静散步",
            intent={"summary": "安静散步", "source": "qwen"},
        )

        self.assertEqual(scripts, {})


def _route(route_id, name):
    return {
        "route_id": route_id,
        "route_name": name,
        "route_intro_user_facing": "适合慢慢预览的一条路线。",
        "suitable_mood": "想独处、想散心",
        "ai_script_angle": "一个人的城市信件",
        "matched_tags": ["想一个人静静"],
        "matched_mindsets": ["疗愈"],
        "match_reason": "符合此刻的心情",
        "spots": [
            {
                "spot_id": "S01",
                "name": "第一站",
                "description": "安静的街角",
                "open_time": "全天",
                "ticket_reservation": "免费",
                "feedback_keywords": ["安静", "慢走"],
            },
            {
                "spot_id": "S02",
                "name": "第二站",
                "description": "适合散步",
                "open_time": "全天",
                "ticket_reservation": "免费",
                "feedback_keywords": ["停留", "放松"],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
