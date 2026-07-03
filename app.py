import os

from flask import Flask, jsonify, render_template, request

from services.intent_matching import (
    add_legacy_intent_tags,
    build_route_summaries,
    fallback_intent,
)
from services.recommender import load_mindset_tags, load_routes, load_tags, recommend_routes
from services.qwen_service import QwenService


try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


NEEDS_INPUT_MESSAGE = "请选择标签或输入心情描述"
QWEN_MISSING_ROUTE_MESSAGE = "千问未返回该路线剧本，请重试。"
QWEN_ERROR_MESSAGES = {
    "qwen_not_configured": "千问未配置，请在 .env 中填写 QWEN_API_KEY 后重试。",
    "qwen_request_failed": "千问调用失败，请稍后重试。",
    "qwen_invalid_response": "千问返回格式不正确，请重试。",
    "qwen_incomplete_response": "千问未返回路线剧本，请重试。",
}


app = Flask(__name__)
qwen_service = QwenService()


@app.get("/")
def index():
    return render_template(
        "index.html",
        frontend_config={
            "amapJsKey": os.getenv("AMAP_JS_KEY", ""),
            "amapSecurityJsCode": os.getenv("AMAP_SECURITY_JS_CODE", ""),
        },
    )


@app.get("/api/tags")
def tags_api():
    return jsonify(
        {
            "experience_tags": load_tags(),
            "mindset_tags": load_mindset_tags(),
        }
    )


@app.post("/api/generate-script")
def generate_script_api():
    payload = request.get_json(silent=True) or {}
    selected_tags, mood_text, profile_answers = _read_recommendation_payload(payload)
    if _needs_current_input(selected_tags, mood_text):
        return jsonify(_needs_input_response(include_script=True)), 400

    intent = _analyze_intent(selected_tags, mood_text)
    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=mood_text,
        profile_answers=profile_answers,
        inferred_experience_tags=intent["inferred_experience_tags"],
        inferred_mindset_tags=intent["inferred_mindset_tags"],
        intent=intent,
        limit=3,
    )
    generated_scripts = {}
    qwen_error_code = ""
    if not qwen_service.enabled:
        qwen_error_code = "qwen_not_configured"
    else:
        generated_scripts = _generate_route_scripts(routes, mood_text, intent, selected_tags)
        qwen_error_code = getattr(qwen_service, "last_script_error", "")
        if generated_scripts:
            missing_routes = _routes_missing_scripts(routes, generated_scripts)
            if missing_routes:
                retry_scripts = _generate_route_scripts(missing_routes, mood_text, intent, selected_tags)
                if retry_scripts:
                    generated_scripts.update(retry_scripts)
                qwen_error_code = (
                    getattr(qwen_service, "last_script_error", "")
                    or qwen_error_code
                    or "qwen_incomplete_response"
                )

    if not isinstance(generated_scripts, dict):
        generated_scripts = {}

    missing_message = (
        QWEN_MISSING_ROUTE_MESSAGE
        if generated_scripts
        else _qwen_error_message(qwen_error_code or "qwen_incomplete_response")
    )
    _apply_generated_scripts(routes, generated_scripts, missing_message)

    if not any(route.get("script_source") == "qwen" for route in routes):
        error_code = qwen_error_code or "qwen_incomplete_response"
        message = _qwen_error_message(error_code)
        return jsonify(_script_response_payload(
            routes=routes,
            intent=intent,
            error_code=error_code,
            message=message,
        )), 502

    return jsonify(_script_response_payload(routes=routes, intent=intent))


def _routes_missing_scripts(routes, generated_scripts):
    if not isinstance(generated_scripts, dict):
        return list(routes or [])
    return [
        route
        for route in routes or []
        if not _script_payload_is_complete(generated_scripts.get(route.get("route_id")), route)
    ]


def _apply_generated_scripts(routes, generated_scripts, missing_message):
    qwen_source_message = _script_source_message("qwen")
    for route in routes:
        generated_script = generated_scripts.get(route.get("route_id"))
        if _script_payload_is_complete(generated_script, route):
            _apply_script_payload(route, generated_script)
            route["script_source"] = "qwen"
            route["script_source_message"] = qwen_source_message
        else:
            _apply_script_payload(route, {})
            route["script_source"] = "qwen_missing"
            route["script_source_message"] = missing_message


def _script_response_payload(routes, intent, error_code="", message=""):
    first_route = routes[0] if routes else {}
    payload = {
        "routes": routes,
        "route": first_route,
        "script": first_route.get("script", ""),
        "script_sections": first_route.get("script_sections", []),
        "needs_input": False,
        "message": message,
        "matched_tags": first_route.get("matched_tags", []),
        "matched_mindsets": first_route.get("matched_mindsets", []),
        "recommendation_reason": first_route.get("match_reason", ""),
        "spots": first_route.get("spots", []),
        "intent": intent,
        "script_source": first_route.get("script_source", ""),
        "script_source_message": first_route.get("script_source_message", ""),
    }
    if error_code:
        payload["error_code"] = error_code
        payload["error"] = message
    return payload


@app.post("/api/recommend-routes")
def recommend_routes_api():
    payload = request.get_json(silent=True) or {}
    selected_tags, mood_text, profile_answers = _read_recommendation_payload(payload)
    if _needs_current_input(selected_tags, mood_text):
        return jsonify(_needs_input_response()), 400

    intent = _analyze_intent(selected_tags, mood_text)
    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=mood_text,
        profile_answers=profile_answers,
        inferred_experience_tags=intent["inferred_experience_tags"],
        inferred_mindset_tags=intent["inferred_mindset_tags"],
        intent=intent,
        limit=3,
    )
    return jsonify({"routes": routes, "needs_input": False, "message": "", "intent": intent})


def _read_recommendation_payload(payload):
    selected_tags = payload.get("selected_tags")
    if selected_tags is None:
        selected_tags = payload.get("tags", [])
    mood_text = (
        payload.get("mood_text")
        or payload.get("mood")
        or payload.get("description")
        or payload.get("user_text")
        or ""
    )
    profile_answers = payload.get("profile_answers", {})

    if not isinstance(selected_tags, list):
        selected_tags = []
    if not isinstance(mood_text, str):
        mood_text = ""
    if not isinstance(profile_answers, dict):
        profile_answers = {}

    selected_tags = [tag.strip() for tag in selected_tags if isinstance(tag, str) and tag.strip()]
    profile_answers = {
        key: value
        for key, value in profile_answers.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    return selected_tags, mood_text.strip(), profile_answers


def _needs_current_input(selected_tags, user_text):
    return not selected_tags and not user_text.strip()


def _needs_input_response(include_script=False):
    response = {
        "routes": [],
        "needs_input": True,
        "error": NEEDS_INPUT_MESSAGE,
        "message": NEEDS_INPUT_MESSAGE,
    }
    if include_script:
        response.update(
            {
                "route": {},
                "script": "",
                "script_sections": [],
                "matched_tags": [],
                "matched_mindsets": [],
                "recommendation_reason": "",
                "spots": [],
                "intent": _fallback_intent([], ""),
            }
        )
    return response


def _analyze_intent(selected_tags, mood_text):
    experience_tags = [tag["emotion_tag"] for tag in load_tags() if tag.get("emotion_tag")]
    mindset_tags = load_mindset_tags()
    available_tags = experience_tags + [tag for tag in mindset_tags if tag not in experience_tags]
    route_summaries = build_route_summaries(load_routes())
    try:
        intent = qwen_service.parse_user_intent_with_llm(
            selected_tags=selected_tags,
            mood_text=mood_text,
            available_tags=available_tags,
            route_summaries=route_summaries,
        )
    except Exception as exc:
        qwen_service.log_exception(exc)
        intent = fallback_intent(selected_tags, mood_text, available_tags)
    return add_legacy_intent_tags(intent, experience_tags, mindset_tags)


def _generate_route_scripts(routes, mood_text, intent, selected_tags):
    qwen_service.last_script_error = ""
    try:
        scripts = qwen_service.generate_route_scripts(
            routes,
            mood_text,
            intent,
            selected_tags=selected_tags,
            mood_text=mood_text,
        )
        return scripts if isinstance(scripts, dict) else {}
    except Exception as exc:
        qwen_service.log_exception(exc)
        qwen_service.last_script_error = "qwen_request_failed"
        return {}


def _fallback_intent(selected_tags, mood_text):
    experience_tags = [tag["emotion_tag"] for tag in load_tags() if tag.get("emotion_tag")]
    mindset_tags = load_mindset_tags()
    available_tags = experience_tags + [tag for tag in mindset_tags if tag not in experience_tags]
    return add_legacy_intent_tags(
        fallback_intent(selected_tags, mood_text, available_tags),
        experience_tags,
        mindset_tags,
    )


SCRIPT_PAYLOAD_KEYS = (
    "script",
    "script_sections",
    "script_title",
)


def _apply_script_payload(route, script_payload):
    for key in SCRIPT_PAYLOAD_KEYS:
        route[key] = script_payload.get(key, [] if key == "script_sections" else "")


def _script_source_message(source, error_code=""):
    if source == "qwen":
        return "来自千问。"
    return QWEN_MISSING_ROUTE_MESSAGE


def _qwen_error_message(error_code):
    return QWEN_ERROR_MESSAGES.get(error_code, QWEN_ERROR_MESSAGES["qwen_incomplete_response"])


def _script_payload_is_complete(script_payload, route=None):
    if not isinstance(script_payload, dict):
        return False
    sections = script_payload.get("script_sections")
    if not all(
        [
            script_payload.get("script"),
            script_payload.get("script_title"),
            isinstance(sections, list),
            sections,
            all(
                isinstance(section, dict)
                and section.get("type") == "spot"
                and section.get("title")
                and section.get("text")
                and section.get("paragraphs")
                for section in sections
            ),
        ]
    ):
        return False

    expected_spot_keys = [_spot_key(spot) for spot in (route or {}).get("spots", []) if _spot_key(spot)]
    section_spot_keys = [_spot_key(section) for section in sections if _spot_key(section)]
    return not expected_spot_keys or _spot_keys_follow_route_order(section_spot_keys, expected_spot_keys)


def _spot_keys_follow_route_order(section_spot_keys, expected_spot_keys):
    if not section_spot_keys:
        return False

    seen = set()
    last_index = -1
    for key in section_spot_keys:
        if key in seen or key not in expected_spot_keys:
            return False
        index = expected_spot_keys.index(key)
        if index <= last_index:
            return False
        seen.add(key)
        last_index = index
    return True


def _spot_key(value):
    spot_id = _script_part(value.get("spot_id", ""))
    if spot_id:
        return f"id:{spot_id}"
    spot_name = _script_part(value.get("spot_name") or value.get("name"))
    if spot_name:
        return f"name:{spot_name}"
    return ""


def _script_part(value):
    return str(value or "").strip().rstrip("。；; ")


if __name__ == "__main__":
    app.run(debug=True)
