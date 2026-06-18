from flask import Flask, jsonify, render_template, request

from services.recommender import recommend_route, recommend_routes


app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/generate-script")
def generate_script_api():
    payload = request.get_json(silent=True) or {}
    selected_tags, user_text = _read_recommendation_payload(payload)

    route = recommend_route(selected_tags=selected_tags, user_text=user_text)
    script = generate_mock_script(route, user_text)

    return jsonify({"route": route, "script": script})


@app.post("/api/recommend-routes")
def recommend_routes_api():
    payload = request.get_json(silent=True) or {}
    selected_tags, user_text = _read_recommendation_payload(payload)

    routes = recommend_routes(selected_tags=selected_tags, user_text=user_text)
    return jsonify({"routes": routes})


def _read_recommendation_payload(payload):
    selected_tags = payload.get("selected_tags", [])
    user_text = payload.get("user_text", "")

    if not isinstance(selected_tags, list):
        selected_tags = []
    if not isinstance(user_text, str):
        user_text = ""

    selected_tags = [tag for tag in selected_tags if isinstance(tag, str)]
    return selected_tags, user_text.strip()


def generate_mock_script(route, user_text=""):
    if not route:
        return "这里是模拟生成的 AI 城市旅游剧本。暂时没有找到可用路线。"

    spots = route.get("spots", [])
    spot_names = "、".join(spot.get("name", "") for spot in spots if spot.get("name"))
    mood_line = f"你刚才写下的心情是：{user_text}。" if user_text else "即使没有输入心情，也可以先把脚步交给城市。"

    first_spot = spots[0]["name"] if spots else "第一站"
    last_spot = spots[-1]["name"] if spots else "终点"

    return (
        f"这里是模拟生成的 AI 城市旅游剧本：今天为你选择的是「{route.get('route_name', '上海情绪路线')}」。"
        f"{mood_line}"
        f"这条路线会从{first_spot}开始，把节奏放慢，再一路经过{spot_names}。"
        f"推荐理由是：{route.get('reason', '这条路线适合此刻的你。')}"
        f"走到{last_spot}时，可以停下来拍一张照片，或者给自己留一句今天的城市旁白。"
    )


if __name__ == "__main__":
    app.run(debug=True)
