# Moodscape Shanghai

Moodscape Shanghai 是一个基于情绪、偏好画像和真实城市点位的上海个性化旅行推荐原型。

系统采用混合推荐架构：

1. 本地 Excel 数据与规则算法完成路线候选、排序和动态点位组合。
2. 优先使用千问理解用户文本为结构化意图，并为三条候选路线生成分幕旅行剧本。
3. 如果千问首次漏掉部分路线，服务端会对缺失路线补生成一次；仍缺失时明确标注为可重试，不再使用本地模板冒充模型内容。
4. 高德地图 JavaScript API 2.0 把 WGS84 点位转换为高德坐标，并逐段规划真实步行路线。

用户手选标签和心情描述都会参与推荐：千问只负责把即时文本理解成结构化意图，本地代码再基于 Excel 里的真实路线和点位打分。模型只能使用 Excel 里的真实路线和点位，不能新增景点、改变点位顺序或覆盖开放时间与票务信息。

## 当前功能

- Flask 首页：`GET /`
- 标签接口：`GET /api/tags`
- 路线与剧本接口：`POST /api/generate-script`
- 兼容的本地路线接口：`POST /api/recommend-routes`
- Excel 路线、点位、标签和匹配表作为事实数据源
- 千问优先生成三条路线剧本，漏掉路线时自动补生成一次
- 剧本来源会在页面标注为“来自千问”或“未生成”
- 高德地图编号标记、WGS84 坐标转换和逐段步行规划

## 安装

必需依赖都写在 `requirements.txt` 里：

- `Flask`：提供网页和接口服务。
- `openpyxl`：读取 `上海路线数据.xlsx`。
- `openai`：用 OpenAI 兼容接口调用阿里云百炼千问。
- `python-dotenv`：启动时读取 `.env` 配置。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

如果旧虚拟环境因为项目路径变化或中文路径编码无法启动，删除旧的 `venv` / `.venv` 后按上面的步骤重建。

## 配置百炼千问与高德地图

复制配置模板：

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写：

```dotenv
QWEN_API_KEY=你的百炼APIKey
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.5-plus
LLM_TIMEOUT_SECONDS=20

AMAP_JS_KEY=你的高德Web端JSKey
AMAP_SECURITY_JS_CODE=你的高德安全密钥
```

申请入口：

- [阿里云百炼千问 API](https://help.aliyun.com/zh/model-studio/use-qwen-by-calling-api)
- [高德地图 JavaScript API 2.0](https://lbs.amap.com/api/javascript-api-v2/summary/)
- [高德安全密钥配置](https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode)

高德应用应创建 Web 端 JavaScript API Key。本机演示时，把本地开发地址加入相应安全配置；公网部署时必须改为正式域名限制。

`.env` 已被 `.gitignore` 忽略，不要把真实密钥提交到仓库。

## 运行

```powershell
.\.venv\Scripts\activate
python app.py
```

打开：

```text
http://127.0.0.1:5000/
```

选择标签、输入心情，或两者同时提供后生成路线。展开任意候选路线时，页面会显示“必要信息”和“分幕剧本”，并加载高德地图步行规划。

## 接口响应

`POST /api/generate-script` 请求格式：

```json
{
  "selected_tags": ["想一个人静静"],
  "mood_text": "今天有点累，想慢慢走",
  "user_text": "今天有点累，想慢慢走",
  "profile_answers": {
    "pace": "slow_stop"
  }
}
```

兼容字段：

- 标签：`selected_tags` 或 `tags`
- 心情描述：`mood_text`、`mood`、`description` 或 `user_text`

响应里会包含：

- `routes`：三条候选路线。
- `intent`：千问解析出的结构化意图，包含 `normalized_intent`、`inferred_tags`、`preferred_scene_types`、`avoid_scene_types`、`must_have`、`route_keywords` 等字段。
- `routes[].script_source`：`qwen` 或 `qwen_missing`。
- `routes[].script_source_message`：剧本来源说明。
- `script_source` / `script_source_message`：第一条路线的来源，兼容旧展示。
- `script_sections`：只按真实点位分幕，不包含开场白、角色设定、感官描写或结尾收束。

来源含义：

- `qwen`：剧本来自千问，页面显示“来自千问”。
- `qwen_missing`：千问未返回该路线剧本，请重试。页面显示“未生成”和失败原因。

## 千问失败与重试

- 未配置 `QWEN_API_KEY`：接口返回 502，并提示“千问未配置，请在 .env 中填写 QWEN_API_KEY 后重试”。
- 千问网络异常、超时、Key 无效或模型调用失败：接口返回 502，并提示“千问调用失败，请稍后重试”。
- 千问首次只返回部分路线剧本：服务端会对缺失路线再调用一次千问补生成。
- 补生成后仍缺少某条路线：该路线的 `script_source` 为 `qwen_missing`，页面提示“千问未返回该路线剧本，请重试”。
- 千问完全没有返回任何可用剧本：接口返回 502，并保留三条推荐路线和结构化意图用于排查。
- 没有配置 `AMAP_JS_KEY`：路线、点位和剧本正常展示，地图区域显示配置提示。
- 某一段步行规划失败：该段使用虚线连接，其余成功路段继续展示。

## 测试

测试不会请求真实千问或高德服务，外部调用均使用测试替身：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

真实密钥的端到端验收建议检查：

1. 返回三条候选路线。
2. 千问成功时，三条路线的 `script_source` 都是 `qwen`，页面显示“来自千问”。
3. 千问只漏掉部分路线时，缺失路线会补生成；仍缺失的路线显示 `qwen_missing` 和“千问未返回该路线剧本，请重试”。
4. 千问完全失败时，接口返回 502，页面显示失败原因，不出现本地模板剧本。
5. 展开路线后出现必要信息、分幕剧本、编号点位、道路级步行折线、距离和预计时间。
6. 切换或关闭路线详情后旧地图被销毁。

## 主要文件

- `app.py`：Flask 接口、配置注入、千问优先、缺失路线补生成与错误提示。
- `services/qwen_service.py`：千问 OpenAI 兼容调用与 JSON 校验。
- `services/recommender.py`：Excel 规则推荐及模型推断标签的低权重融合。
- `services/excel_data.py`：读取 `上海路线数据.xlsx`。
- `static/js/main.js`：推荐交互、来源标注与高德地图步行路线展示。
- `tests/`：推荐、API、千问服务、地图前端和配置测试。
