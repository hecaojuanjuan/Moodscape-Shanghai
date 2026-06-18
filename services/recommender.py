import json
from pathlib import Path


DEFAULT_ROUTES_PATH = Path(__file__).resolve().parents[1] / "static" / "data" / "routes.json"

TEXT_KEYWORDS = {
    "想一个人静静": ["一个人", "独处", "安静", "静静", "散心"],
    "想慢慢走不赶路": ["慢慢", "不赶路", "散步", "city walk", "漫步"],
    "想被夜景治愈": ["夜景", "夜晚", "灯光", "治愈"],
    "想认识上海第一面": ["第一次", "初到", "经典", "上海第一面"],
    "想体验未来城市": ["未来", "高楼", "摩天", "科技", "陆家嘴"],
    "想被城市震撼": ["震撼", "天际线", "俯瞰", "高空"],
    "想和TA约会": ["约会", "情侣", "ta", "TA", "浪漫"],
    "想找回老上海": ["老上海", "老洋房", "梧桐", "历史", "怀旧"],
    "想看展充电": ["看展", "展览", "艺术", "充电", "博物馆"],
    "想探索冷门角落": ["冷门", "探索", "工业", "小众", "角落"],
    "想拍照发朋友圈": ["拍照", "出片", "打卡", "朋友圈", "摄影"],
    "想边走边吃": ["吃", "美食", "小吃", "烟火气"],
    "想夜晚继续玩": ["夜晚", "夜游", "晚上", "继续玩"],
    "想低预算也有仪式感": ["低预算", "便宜", "免费", "省钱", "仪式感"],
}


def load_routes(routes_path=DEFAULT_ROUTES_PATH):
    path = Path(routes_path)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def recommend_routes(selected_tags=None, user_text="", routes_path=DEFAULT_ROUTES_PATH, limit=3):
    selected_tags = [tag for tag in (selected_tags or []) if isinstance(tag, str)]
    user_text = user_text or ""
    routes = load_routes(routes_path)

    scored_routes = []
    for index, route in enumerate(routes):
        score = _score_route(route, selected_tags, user_text)
        scored_routes.append((score, index, route))

    scored_routes.sort(key=lambda item: (-item[0], item[1]))
    recommendations = [route for score, _, route in scored_routes if score > 0]

    if not recommendations:
        recommendations = routes

    return recommendations[:limit]


def _score_route(route, selected_tags, user_text):
    route_tags = set(route.get("tags", []))
    score = 0

    for tag in selected_tags:
        if tag in route_tags:
            score += 4

    lowered_text = user_text.lower()
    for tag in route_tags:
        if tag in user_text:
            score += 3

        for keyword in TEXT_KEYWORDS.get(tag, []):
            if keyword.lower() in lowered_text:
                score += 2

    route_text = " ".join(
        [
            route.get("route_name", ""),
            route.get("reason", ""),
            " ".join(route.get("tags", [])),
        ]
    )
    for word in _tokenize_user_text(user_text):
        if word in route_text:
            score += 1

    return score


def _tokenize_user_text(user_text):
    separators = "，。！？、,.!?;； \n\t"
    normalized = user_text
    for separator in separators:
        normalized = normalized.replace(separator, " ")
    return [word for word in normalized.split(" ") if len(word) >= 2]
