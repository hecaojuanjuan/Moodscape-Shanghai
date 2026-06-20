from flask import Flask, jsonify, render_template, request

from services.recommender import load_mindset_tags, load_tags, recommend_route, recommend_routes


NEEDS_INPUT_MESSAGE = "请在左侧选择标签，或者写入你的心情状态。"


app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


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

    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=user_text,
        profile_answers=profile_answers,
        limit=3,
    )
    for route in routes:
        route["script"] = generate_excel_script(route)

    first_route = routes[0] if routes else {}
    return jsonify(
        {
            "routes": routes,
            "route": first_route,
            "script": first_route.get("script", ""),
            "needs_input": False,
            "message": "",
            "matched_tags": first_route.get("matched_tags", []),
            "matched_mindsets": first_route.get("matched_mindsets", []),
            "recommendation_reason": first_route.get("match_reason", ""),
            "spots": first_route.get("spots", []),
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
                "matched_tags": [],
                "matched_mindsets": [],
                "recommendation_reason": "",
                "spots": [],
            }
        )
    return response


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


def _script_part(value):
    return str(value or "").strip().rstrip("。；; ")


if __name__ == "__main__":
    app.run(debug=True)
