import os

from flask import Flask, jsonify, render_template, request

from services.recommender import load_mindset_tags, load_tags, recommend_route, recommend_routes
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
    generated_scripts = _generate_route_scripts(routes, user_text, intent)
    for route in routes:
        generated_script = generated_scripts.get(route.get("route_id"))
        if generated_script:
            route["script"] = generated_script["script"]
            route["script_sections"] = generated_script["script_sections"]
        else:
            route["script"] = generate_excel_script(route)
            route["script_sections"] = generate_excel_script_sections(route)
        route["script_source"] = "qwen" if generated_script else "fallback"

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
    try:
        return qwen_service.generate_route_scripts(routes, user_text, intent)
    except Exception:
        return {}


def _fallback_intent(user_text):
    return {
        "summary": str(user_text or "").strip()[:80],
        "inferred_experience_tags": [],
        "inferred_mindset_tags": [],
        "source": "fallback",
    }


def generate_excel_script(route):
    if not route:
        return ""

    spot_lines = []
    for spot in route.get("spots", []):
        keywords = "、".join(spot.get("feedback_keywords", []))
        spot_lines.append(
            " / ".join(
                part
                for part in [
                    spot.get("name", ""),
                    spot.get("description", ""),
                    spot.get("open_time", ""),
                    spot.get("ticket_reservation", ""),
                    keywords,
                ]
                if part
            )
        )

    return "。".join(
        part
        for part in [
            _script_part(route.get("route_name", "")),
            _script_part(route.get("route_intro_user_facing", "")),
            _script_part(route.get("ai_script_angle", "")),
            _script_part(route.get("route_spots", "")),
            "；".join(spot_lines),
        ]
        if part
    )


def generate_excel_script_sections(route):
    if not route:
        return []

    route_name = _script_part(route.get("route_name", ""))
    route_intro = _script_part(route.get("route_intro_user_facing", ""))
    script_angle = _script_part(route.get("ai_script_angle", ""))
    match_reason = _script_part(route.get("match_reason", ""))
    opening_text = "。".join(
        part
        for part in [
            f"这条路线会从{route_name}展开" if route_name else "",
            route_intro,
            script_angle,
            match_reason,
        ]
        if part
    )
    sections = [
        {
            "type": "opening",
            "title": "开场",
            "text": opening_text or "这条路线会把此刻的心情，慢慢带进上海的街道里。",
        }
    ]

    for index, spot in enumerate(route.get("spots", []), start=1):
        spot_name = _script_part(spot.get("name", ""))
        description = _script_part(spot.get("description", ""))
        keywords = "、".join(spot.get("feedback_keywords", []))
        practical_info = " / ".join(
            part
            for part in [
                spot.get("open_time", ""),
                spot.get("ticket_reservation", ""),
            ]
            if part
        )
        text = "。".join(
            part
            for part in [
                f"你会在{spot_name}停下来" if spot_name else "",
                description,
                f"这里的关键词是{keywords}" if keywords else "",
                practical_info,
            ]
            if part
        )
        sections.append(
            {
                "type": "spot",
                "spot_id": str(spot.get("spot_id", "")).strip(),
                "spot_name": spot_name,
                "title": f"{_section_number(index)}幕｜{spot_name}" if spot_name else f"{_section_number(index)}幕",
                "text": text or "这一站适合放慢脚步，给路线留出一点停顿。",
            }
        )

    closing_parts = [
        route.get("route_spots", ""),
        route.get("estimated_time", ""),
        route.get("budget_level", ""),
    ]
    closing_detail = " / ".join(str(part).strip() for part in closing_parts if str(part or "").strip())
    sections.append(
        {
            "type": "closing",
            "title": "收束",
            "text": (
                f"走完这些点位后，{closing_detail}会成为这段上海预览的轮廓。"
                if closing_detail
                else "走完这些点位后，这段路线会把今天的心情收束成一段更安静的城市记忆。"
            ),
        }
    )
    return sections


def _script_part(value):
    return str(value or "").strip().rstrip("。；; ")


def _section_number(index):
    numbers = ["零", "第一", "第二", "第三", "第四", "第五", "第六", "第七", "第八", "第九", "第十"]
    if 0 < index < len(numbers):
        return numbers[index]
    return f"第{index}"


if __name__ == "__main__":
    app.run(debug=True)
