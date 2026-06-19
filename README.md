# Moodscape Shanghai

Moodscape Shanghai 是一个基于情绪标签的上海个性化旅游推荐网站原型。

当前版本是最小可运行 Flask MVP：用户可以选择体验标签/心境标签、输入心情描述，系统会从本地 Excel 数据库 `上海路线数据.xlsx` 中推荐 2-3 条上海路线。此版本不接真实大模型 API，不接地图 API，也不引入复杂前端框架。

## 当前功能

- Flask 首页：`GET /`
- 标签接口：`GET /api/tags`
- 剧本和候选路线接口：`POST /api/generate-script`
- 路线推荐接口：`POST /api/recommend-routes`
- 原生 HTML/CSS/JavaScript 前端交互
- 本地规则推荐函数，运行时读取 Excel
- 本地数据源：`上海路线数据.xlsx`
- 地图展示区域预留，占位但不加载地图服务

## 项目结构

```text
Moodscape-Shanghai/
├─ app.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ 上海路线数据.xlsx
├─ templates/
│  └─ index.html
├─ static/
│  ├─ css/
│  │  └─ style.css
│  ├─ js/
│  │  └─ main.js
│  └─ data/
│     └─ routes.json
├─ services/
│  ├─ __init__.py
│  ├─ excel_data.py
│  └─ recommender.py
└─ tests/
   ├─ test_app.py
   └─ test_recommender.py
```

## 文件作用

- `app.py`：Flask 应用入口，提供首页、标签接口、路线推荐接口和 mock 剧本接口。
- `services/excel_data.py`：读取 `上海路线数据.xlsx`，组装路线、点位、体验标签、心境分值和匹配表。
- `services/recommender.py`：本地规则推荐逻辑，根据 Excel 字段、用户选择和用户文本给路线打分。
- `static/data/routes.json` / `static/data/tags.json`：历史静态备份，运行时推荐不依赖它们。
- `templates/index.html`：首页页面结构。
- `static/css/style.css`：页面样式。
- `static/js/main.js`：标签选择、接口请求和推荐结果渲染。
- `requirements.txt`：Python 依赖，包含 Flask 和 openpyxl。
- `tests/`：基础单元测试，覆盖推荐函数和推荐接口。

## 安装依赖

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 运行项目

```bash
python app.py
```

启动后打开：

```text
http://127.0.0.1:5000/
```

## 测试首页

1. 打开 `http://127.0.0.1:5000/`。
2. 点击一个或多个体验标签或心境标签，例如“一个人静静”“疗愈”。
3. 在输入框中填写心情描述，例如“今天想一个人慢慢走，不赶路”。
4. 点击“生成推荐”。
5. 页面应展示 2-3 条候选路线；点击候选路线可展开推荐理由、点位列表和 mock 剧本。

## 测试接口

PowerShell:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:5000/api/recommend-routes" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"selected_tags":["想一个人静静"],"user_text":"今天想一个人慢慢走"}'
```

curl:

```bash
curl -X POST http://127.0.0.1:5000/api/recommend-routes \
  -H "Content-Type: application/json" \
  -d '{"selected_tags":["想一个人静静"],"user_text":"今天想一个人慢慢走"}'
```

预期返回 JSON 中包含 `routes` 字段，并且“武康路书香独处线”会排在前列。

## 运行测试

```bash
python -m unittest discover -s tests
```

## 后续计划

- 扩展更多上海路线和真实点位数据。
- 优化情绪标签与文本关键词匹配策略。
- 接入真实大模型 API，用于生成更有氛围的旅行文案。
- 接入地图服务，展示路线点位和连线。
