# Moodscape Shanghai

Moodscape Shanghai 是一个基于情绪、偏好画像和真实城市点位的上海个性化旅行推荐原型。

系统采用混合推荐架构：

1. 百炼千问把用户的自由文本解析成受控体验标签和心境标签。
2. 本地 Excel 数据与规则算法完成路线候选、排序和动态点位组合。
3. 千问根据真实路线数据一次生成三条旅行剧本。
4. 高德地图 JavaScript API 2.0 把 WGS84 点位转换为高德坐标，并逐段规划真实步行路线。

用户手选标签的权重高于模型推断标签。模型只负责理解和表达，不能新增景点、改变点位顺序或覆盖 Excel 中的开放时间与票务信息。

## 当前功能

- Flask 首页：`GET /`
- 标签接口：`GET /api/tags`
- 路线与 AI 剧本接口：`POST /api/generate-script`
- 兼容的本地路线接口：`POST /api/recommend-routes`
- Excel 路线、点位、标签和匹配表作为事实数据源
- 千问意图解析与三条路线批量文案生成
- 高德地图编号标记、WGS84 坐标转换和逐段步行规划
- API 不可用时自动本地回退，路线推荐仍可使用

## 安装

Windows PowerShell：

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

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
python app.py
```

打开：

```text
http://127.0.0.1:5000/
```

选择标签或输入心情后生成路线。展开任意候选路线时，页面才会加载高德地图并请求该路线的步行规划。

## 接口响应

`POST /api/generate-script` 保持原请求格式：

```json
{
  "selected_tags": ["想一个人静静"],
  "user_text": "今天有点累，想慢慢走",
  "profile_answers": {
    "pace": "slow_stop"
  }
}
```

响应新增：

- `intent`：心情摘要、模型推断的体验/心境标签和处理来源。
- `routes[].script_source`：`qwen` 或 `fallback`。

原有的 `routes`、`route`、`script`、`spots` 等字段继续保留。

## 本地回退与故障排查

- 没有配置 `QWEN_API_KEY`：继续使用本地规则推荐和 Excel 拼接文案，`script_source` 为 `fallback`。
- 千问超时、返回非法 JSON 或漏掉部分路线：仅对应文案使用本地回退，不影响路线数据。
- 没有配置 `AMAP_JS_KEY`：路线与点位列表正常展示，地图区域显示配置提示。
- 某一段步行规划失败：该段使用虚线连接，其余成功路段继续展示。
- 地图脚本或坐标转换失败：点位列表和 AI 文案仍然保留。
- 若旧虚拟环境因项目路径变化无法启动，请删除后重新执行“安装”步骤创建环境。

## 测试

测试不会请求真实千问或高德服务，外部调用均使用测试替身：

```powershell
python -m unittest discover -s tests
```

真实密钥的端到端验收建议检查：

1. 返回三条候选路线，且 `intent.source` 为 `qwen`。
2. 至少一条路线的 `script_source` 为 `qwen`。
3. 展开路线后出现编号点位、道路级步行折线、距离和预计时间。
4. 切换或关闭路线详情后旧地图被销毁。

## 主要文件

- `app.py`：Flask 接口、配置注入和服务编排。
- `services/qwen_service.py`：千问 OpenAI 兼容调用、JSON 校验和回退。
- `services/recommender.py`：Excel 规则推荐及模型推断标签的低权重融合。
- `services/excel_data.py`：读取 `上海路线数据.xlsx`。
- `static/js/main.js`：推荐交互与高德地图步行路线展示。
- `tests/`：推荐、API、千问服务、地图前端和配置测试。
