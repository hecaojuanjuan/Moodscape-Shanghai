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

    def test_generate_route_scripts_ignores_unknown_and_missing_route_ids(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {"route_id": "R01", "script": "从第一站开始慢慢走。"},
                            {"route_id": "R99", "script": "这条路线并不存在。"},
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

        self.assertEqual(scripts, {"R01": "从第一站开始慢慢走。"})
        self.assertEqual(routes, original_routes)


def _route(route_id, name):
    return {
        "route_id": route_id,
        "route_name": name,
        "match_reason": "符合此刻的心情",
        "spots": [
            {
                "name": "第一站",
                "description": "安静的街角",
                "open_time": "全天",
                "ticket_reservation": "免费",
            },
            {
                "name": "第二站",
                "description": "适合散步",
                "open_time": "全天",
                "ticket_reservation": "免费",
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
