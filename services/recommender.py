import copy
import json
import re
from pathlib import Path


DEFAULT_ROUTES_PATH = Path(__file__).resolve().parents[1] / "static" / "data" / "routes.json"

# 每个情绪标签对应一组容易出现在自然语言心情描述里的关键词。
TEXT_KEYWORDS = {
    "独处": ["一个人", "独处", "自己", "安静", "静静", "不想说话"],
    "治愈": ["累", "疲惫", "放松", "治愈", "疗愈", "缓一缓", "散心"],
    "慢走": ["慢慢", "慢走", "不赶路", "散步", "city walk", "漫步"],
    "低预算": ["低预算", "便宜", "免费", "省钱", "少花钱"],
    "夜景": ["夜景", "夜晚", "晚上", "灯光", "夜游"],
    "拍照": ["拍照", "出片", "打卡", "朋友圈", "摄影"],
    "经典": ["第一次", "初见", "经典", "地标", "游客"],
    "城市漫步": ["城市漫步", "city walk", "步行", "街区", "走走"],
    "未来感": ["未来", "科技", "高楼", "摩天", "陆家嘴"],
    "高空": ["高空", "俯瞰", "天际线", "观景", "震撼"],
    "展览": ["展览", "看展", "博物馆", "艺术", "充电"],
    "约会": ["约会", "情侣", "浪漫", "ta", "TA", "喜欢的人"],
    "老上海": ["老上海", "老洋房", "梧桐", "历史", "怀旧"],
    "咖啡": ["咖啡", "书店", "下午茶", "聊天", "小坐"],
    "小众": ["小众", "冷门", "探索", "角落", "人少"],
    "艺术": ["艺术", "画廊", "影像", "创意", "美术馆"],
    "工业风": ["工业", "仓库", "厂房", "粗粝", "苏州河"],
}


def load_routes(routes_path=DEFAULT_ROUTES_PATH):
    path = Path(routes_path)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def recommend_route(selected_tags=None, user_text="", routes_path=DEFAULT_ROUTES_PATH):
    selected_tags = _clean_selected_tags(selected_tags)
    user_text = user_text if isinstance(user_text, str) else ""
    routes = load_routes(routes_path)

    if not routes:
        return {}

    scored_routes = []
    for index, route in enumerate(routes):
        score, matched_tags = _score_route(route, selected_tags, user_text)
        scored_routes.append((score, index, route, matched_tags))

    scored_routes.sort(key=lambda item: (-item[0], item[1]))
    best_score, _, best_route, matched_tags = scored_routes[0]

    result = copy.deepcopy(best_route)
    if best_score <= 0:
        result = copy.deepcopy(routes[0])
        result["matched_tags"] = []
        result["score"] = 0
        return result

    result["matched_tags"] = matched_tags
    result["score"] = min(best_score, 100)
    return result


def recommend_routes(selected_tags=None, user_text="", routes_path=DEFAULT_ROUTES_PATH, limit=3):
    """兼容旧接口：旧版返回路线列表，新版核心逻辑只返回最佳路线。"""
    route = recommend_route(
        selected_tags=selected_tags,
        user_text=user_text,
        routes_path=routes_path,
    )
    return [route] if route else []


def _score_route(route, selected_tags, user_text):
    route_tags = [tag for tag in route.get("tags", []) if isinstance(tag, str)]
    route_tag_set = set(route_tags)
    matched_tags = []
    score = 0

    for tag in selected_tags:
        if tag in route_tag_set:
            score += 30
            _append_unique(matched_tags, tag)

    normalized_text = user_text.lower()
    for tag in route_tags:
        keywords = [tag, *TEXT_KEYWORDS.get(tag, [])]
        if _text_matches_any_keyword(normalized_text, keywords):
            score += 20
            _append_unique(matched_tags, tag)

    route_text = _route_search_text(route)
    for token in _tokenize_user_text(user_text):
        if token.lower() in route_text:
            score += 5

    return score, matched_tags


def _clean_selected_tags(selected_tags):
    if not isinstance(selected_tags, list):
        return []
    return [tag.strip() for tag in selected_tags if isinstance(tag, str) and tag.strip()]


def _text_matches_any_keyword(normalized_text, keywords):
    return any(keyword.lower() in normalized_text for keyword in keywords if keyword)


def _route_search_text(route):
    parts = [
        route.get("route_name", ""),
        route.get("reason", ""),
        " ".join(route.get("tags", [])),
    ]
    for spot in route.get("spots", []):
        parts.append(spot.get("name", ""))
        parts.append(spot.get("description", ""))
    return " ".join(parts).lower()


def _tokenize_user_text(user_text):
    if not isinstance(user_text, str):
        return []
    return [token for token in re.split(r"[\s,，。！？!?；;、]+", user_text) if len(token) >= 2]


def _append_unique(items, value):
    if value not in items:
        items.append(value)
