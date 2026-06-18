from flask import Flask, jsonify, render_template, request

from services.recommender import recommend_routes


app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/recommend-routes")
def recommend_routes_api():
    payload = request.get_json(silent=True) or {}
    selected_tags = payload.get("selected_tags", [])
    user_text = payload.get("user_text", "")

    if not isinstance(selected_tags, list):
        selected_tags = []
    if not isinstance(user_text, str):
        user_text = ""

    routes = recommend_routes(selected_tags=selected_tags, user_text=user_text)
    return jsonify({"routes": routes})


if __name__ == "__main__":
    app.run(debug=True)
