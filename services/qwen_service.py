import json
import os


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.5-plus"
DEFAULT_TIMEOUT_SECONDS = 20.0


class QwenService:
    def __init__(
        self,
        api_key=None,
        base_url=None,
        model=None,
        timeout_seconds=None,
        client=None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("QWEN_API_KEY", "")
        self.base_url = base_url or os.getenv("QWEN_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.getenv("QWEN_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = _positive_float(
            timeout_seconds if timeout_seconds is not None else os.getenv("LLM_TIMEOUT_SECONDS"),
            DEFAULT_TIMEOUT_SECONDS,
        )
        self._provided_client = client
        self._client_instance = None

    @property
    def enabled(self):
        return bool(self.api_key.strip())

    def analyze_intent(self, user_text, allowed_experience_tags, allowed_mindset_tags):
        fallback = _fallback_intent(user_text)
        if not self.enabled or not str(user_text or "").strip():
            return fallback

        prompt = {
            "task": "分析用户在上海旅行时此刻的体验需求，只能从给定标签中选择。",
            "user_text": str(user_text).strip(),
            "allowed_experience_tags": list(allowed_experience_tags or []),
            "allowed_mindset_tags": list(allowed_mindset_tags or []),
            "output_schema": {
                "summary": "不超过40字的中文摘要",
                "experience_tags": ["零个或多个允许的体验标签"],
                "mindset_tags": ["零个或多个允许的心境标签"],
            },
        }

        try:
            result = self._request_json(
                system_prompt=(
                    "你是旅行意图解析器。必须返回 JSON 对象，不得输出 Markdown；"
                    "不得创造输入列表之外的标签。"
                ),
                user_prompt=json.dumps(prompt, ensure_ascii=False),
                max_tokens=500,
            )
        except Exception:
            return fallback

        experience_tags = _filter_allowed(
            result.get("experience_tags"),
            allowed_experience_tags,
        )
        mindset_tags = _filter_allowed(
            result.get("mindset_tags"),
            allowed_mindset_tags,
        )
        summary = _clean_text(result.get("summary")) or fallback["summary"]
        return {
            "summary": summary[:80],
            "inferred_experience_tags": experience_tags,
            "inferred_mindset_tags": mindset_tags,
            "source": "qwen",
        }

    def generate_route_scripts(self, routes, user_text, intent):
        if not self.enabled or not routes:
            return {}

        route_payloads = [_route_prompt_payload(route) for route in routes]
        request_payload = {
            "task": "为候选上海路线分别生成简洁、有氛围但事实准确的旅行剧本。",
            "user_text": str(user_text or "").strip(),
            "intent": intent or {},
            "routes": route_payloads,
            "rules": [
                "每个 route_id 最多返回一条剧本。",
                "只能使用输入中提供的路线和点位。",
                "不得新增景点、改变点位顺序或虚构开放时间、票务信息。",
                "每条剧本使用中文，约120至220字。",
            ],
            "output_schema": {
                "scripts": [
                    {
                        "route_id": "输入中的 route_id",
                        "script": "该路线的旅行剧本",
                    }
                ]
            },
        }

        try:
            result = self._request_json(
                system_prompt=(
                    "你是上海城市旅行文案编辑。必须严格依据输入事实并返回 JSON 对象，"
                    "不得输出 Markdown。"
                ),
                user_prompt=json.dumps(request_payload, ensure_ascii=False),
                max_tokens=2400,
            )
        except Exception:
            return {}

        allowed_ids = {
            route.get("route_id")
            for route in routes
            if isinstance(route, dict) and route.get("route_id")
        }
        scripts = {}
        raw_scripts = result.get("scripts")
        if not isinstance(raw_scripts, list):
            return scripts

        for item in raw_scripts:
            if not isinstance(item, dict):
                continue
            route_id = _clean_text(item.get("route_id"))
            script = _clean_text(item.get("script"))
            if route_id in allowed_ids and script and route_id not in scripts:
                scripts[route_id] = script
        return scripts

    def _request_json(self, system_prompt, user_prompt, max_tokens):
        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=max_tokens,
            timeout=self.timeout_seconds,
        )
        content = response.choices[0].message.content
        parsed = json.loads(_strip_code_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("Qwen response must be a JSON object.")
        return parsed

    def _get_client(self):
        if self._provided_client is not None:
            return self._provided_client
        if self._client_instance is None:
            from openai import OpenAI

            self._client_instance = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        return self._client_instance


def _fallback_intent(user_text):
    return {
        "summary": _clean_text(user_text)[:80],
        "inferred_experience_tags": [],
        "inferred_mindset_tags": [],
        "source": "fallback",
    }


def _filter_allowed(values, allowed_values):
    if not isinstance(values, list):
        return []
    allowed = set(allowed_values or [])
    filtered = []
    for value in values:
        clean_value = _clean_text(value)
        if clean_value in allowed and clean_value not in filtered:
            filtered.append(clean_value)
    return filtered


def _route_prompt_payload(route):
    return {
        "route_id": route.get("route_id", ""),
        "route_name": route.get("route_name", ""),
        "match_reason": route.get("match_reason", ""),
        "spots": [
            {
                "name": spot.get("name", ""),
                "description": spot.get("description", ""),
                "open_time": spot.get("open_time", ""),
                "ticket_reservation": spot.get("ticket_reservation", ""),
            }
            for spot in route.get("spots", [])
        ],
    }


def _strip_code_fence(value):
    text = str(value or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


def _clean_text(value):
    return str(value or "").strip()


def _positive_float(value, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback
