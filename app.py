import os

from flask import Flask, jsonify, render_template, request

from services.recommender import load_mindset_tags, load_tags, recommend_routes
from services.qwen_service import QwenService


try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


NEEDS_INPUT_MESSAGE = "请在左侧选择标签，或者写入你的心情状态。"


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
    selected_tags, user_text, profile_answers = _read_recommendation_payload(payload)
    if _needs_current_input(selected_tags, user_text):
        return jsonify(_needs_input_response(include_script=True))

    intent = _analyze_intent(user_text)
    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=user_text,
        profile_answers=profile_answers,
        inferred_experience_tags=intent["inferred_experience_tags"],
        inferred_mindset_tags=intent["inferred_mindset_tags"],
        limit=3,
    )
    generated_scripts = {}
    fallback_error_code = ""
    if not qwen_service.enabled:
        fallback_error_code = "qwen_not_configured"
    else:
        generated_scripts = _generate_route_scripts(routes, user_text, intent)

    fallback_error_code = (
        fallback_error_code
        or getattr(qwen_service, "last_script_error", "")
        or "qwen_incomplete_response"
    )
    qwen_source_message = _script_source_message("qwen")
    fallback_source_message = _script_source_message("fallback", fallback_error_code)
    for route in routes:
        generated_script = generated_scripts.get(route.get("route_id"))
        if _script_payload_is_complete(generated_script, route):
            _apply_script_payload(route, generated_script)
            route["script_source"] = "qwen"
            route["script_source_message"] = qwen_source_message
        else:
            _apply_script_payload(route, _generate_fallback_script_payload(route))
            route["script_source"] = "fallback"
            route["script_source_message"] = fallback_source_message

    first_route = routes[0] if routes else {}
    return jsonify(
        {
            "routes": routes,
            "route": first_route,
            "script": first_route.get("script", ""),
            "script_sections": first_route.get("script_sections", []),
            "needs_input": False,
            "message": "",
            "matched_tags": first_route.get("matched_tags", []),
            "matched_mindsets": first_route.get("matched_mindsets", []),
            "recommendation_reason": first_route.get("match_reason", ""),
            "spots": first_route.get("spots", []),
            "intent": intent,
            "script_source": first_route.get("script_source", ""),
            "script_source_message": first_route.get("script_source_message", ""),
        }
    )


@app.post("/api/recommend-routes")
def recommend_routes_api():
    payload = request.get_json(silent=True) or {}
    selected_tags, user_text, profile_answers = _read_recommendation_payload(payload)
    if _needs_current_input(selected_tags, user_text):
        return jsonify(_needs_input_response())

    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=user_text,
        profile_answers=profile_answers,
        limit=3,
    )
    return jsonify({"routes": routes, "needs_input": False, "message": ""})


def _read_recommendation_payload(payload):
    selected_tags = payload.get("selected_tags", [])
    user_text = payload.get("user_text", "")
    profile_answers = payload.get("profile_answers", {})

    if not isinstance(selected_tags, list):
        selected_tags = []
    if not isinstance(user_text, str):
        user_text = ""
    if not isinstance(profile_answers, dict):
        profile_answers = {}

    selected_tags = [tag.strip() for tag in selected_tags if isinstance(tag, str) and tag.strip()]
    profile_answers = {
        key: value
        for key, value in profile_answers.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    return selected_tags, user_text.strip(), profile_answers


def _needs_current_input(selected_tags, user_text):
    return not selected_tags and not user_text.strip()


def _needs_input_response(include_script=False):
    response = {
        "routes": [],
        "needs_input": True,
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
                "intent": _fallback_intent(""),
            }
        )
    return response


def _analyze_intent(user_text):
    experience_tags = [
        tag["emotion_tag"]
        for tag in load_tags()
        if tag.get("emotion_tag")
    ]
    mindset_tags = load_mindset_tags()
    try:
        return qwen_service.analyze_intent(
            user_text,
            allowed_experience_tags=experience_tags,
            allowed_mindset_tags=mindset_tags,
        )
    except Exception:
        return _fallback_intent(user_text)


def _generate_route_scripts(routes, user_text, intent):
    qwen_service.last_script_error = ""
    try:
        return qwen_service.generate_route_scripts(routes, user_text, intent)
    except Exception:
        qwen_service.last_script_error = "qwen_request_failed"
        return {}


def _fallback_intent(user_text):
    return {
        "summary": str(user_text or "").strip()[:80],
        "inferred_experience_tags": [],
        "inferred_mindset_tags": [],
        "source": "fallback",
    }


SCRIPT_PAYLOAD_KEYS = (
    "script",
    "script_sections",
    "script_title",
)


def _apply_script_payload(route, script_payload):
    for key in SCRIPT_PAYLOAD_KEYS:
        route[key] = script_payload.get(key, [] if key == "script_sections" else "")


def _generate_fallback_script_payload(route):
    spots = route.get("spots", [])
    sections = [
        _generate_fallback_script_section(spot, index)
        for index, spot in enumerate(spots, start=1)
    ]
    spot_names = "、".join(spot.get("name", "") for spot in spots if spot.get("name"))
    route_name = _script_part(route.get("route_name")) or "这条路线"
    script = (
        f"这是本地模板生成的分幕剧本，沿着{spot_names or route_name}慢慢展开。"
        "它保留真实点位顺序和必要事实，也把此刻的情绪放轻一点。"
    )
    return {
        "script": script,
        "script_title": _fallback_script_title(route),
        "script_sections": sections,
    }


def _generate_fallback_script_section(spot, index):
    spot_name = _script_part(spot.get("name")) or f"第{index}站"
    description = _trim_sentence(spot.get("description"), 34)
    keywords = "、".join((spot.get("feedback_keywords") or [])[:2])
    paragraphs = [
        f"来到{spot_name}，先让脚步比刚才更慢一点。",
        _fallback_spot_fact_sentence(spot_name, description, keywords),
        _fallback_spot_mood_sentence(index),
    ]
    text = "\n\n".join(paragraphs)
    return {
        "type": "spot",
        "spot_id": _script_part(spot.get("spot_id")),
        "spot_name": spot_name,
        "title": f"{_section_number(index)}幕｜{_fallback_scene_title(spot_name, keywords, index)}",
        "text": text,
        "paragraphs": paragraphs,
    }


def _fallback_script_title(route):
    angle = _script_part(route.get("ai_script_angle"))
    route_name = _script_part(route.get("route_name"))
    if angle and angle != route_name and "路线推荐" not in angle:
        return f"{angle}里的慢慢停留"
    return "把脚步交还给城市的一段路"


def _fallback_scene_title(spot_name, keywords, index):
    scene_titles = [
        "先把脚步放慢。",
        "把注意力留在这里。",
        "让城市声音低下来。",
        "继续往轻一点的地方走。",
        "把今天慢慢收好。",
    ]
    if keywords:
        first_keyword = keywords.split("、")[0]
        return f"{first_keyword}在这里停一停。"
    if spot_name:
        return f"{spot_name}先替你停留。"
    return scene_titles[(index - 1) % len(scene_titles)]


def _fallback_spot_fact_sentence(spot_name, description, keywords):
    if description:
        return f"{spot_name}的重点不必急着看完，{description}"
    if keywords:
        return f"这里适合{keywords}，也适合把注意力从行程表里收回来。"
    return "这里不需要被匆忙解释，留一点空白给现场就好。"


def _fallback_spot_mood_sentence(index):
    sentences = [
        "不必急着赶往下一站，等这一幕的情绪自然安静下来。",
        "如果愿意，可以多停一会儿，让今天的节奏重新变得柔和。",
        "走到这里时，真正被放慢的也许是一直紧绷的注意力。",
    ]
    return sentences[(index - 1) % len(sentences)]


def _trim_sentence(value, max_length):
    text = _script_part(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip()}。"


def _script_source_message(source, error_code=""):
    if source == "qwen":
        return "来自千问。"
    fallback_reasons = {
        "qwen_not_configured": "千问未配置",
        "qwen_request_failed": "千问调用失败",
        "qwen_invalid_response": "千问返回格式不正确",
        "qwen_incomplete_response": "千问返回不完整",
    }
    reason = fallback_reasons.get(error_code, "千问未成功返回")
    return f"本地模板，{reason}。"


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
    return not expected_spot_keys or section_spot_keys == expected_spot_keys


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


def _section_number(index):
    numbers = ["零", "第一", "第二", "第三", "第四", "第五", "第六", "第七", "第八", "第九", "第十"]
    if 0 < index < len(numbers):
        return numbers[index]
    return f"第{index}"


if __name__ == "__main__":
    app.run(debug=True)
