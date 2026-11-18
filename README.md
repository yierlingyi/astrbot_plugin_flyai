# 飞猪旅行助手 · AstrBot 插件

在 QQ / Telegram / 微信等聊天里直接查机票、火车票、酒店和景点，价格与库存实时来自飞猪供应链，结果自带飞猪下单短链。

底层调用飞猪官方开源的 **flyai**（阿里飞猪 2026-03 发布，MIT 协议），不是爬虫，也不是第三方聚合。

## 能力覆盖

| 能力 | 指令 | 对应 flyai 子命令 |
|---|---|---|
| 一句话语义搜索（全品类） | `/飞猪` | `ai-search` |
| 机票 | `/机票` | `search-flight`（18 个过滤项） |
| 火车票 | `/火车` | `search-train` |
| 酒店 | `/酒店` | `search-hotel` |
| 景点玩乐 | `/景点` | `search-poi`（34 个分类，1–5A 等级） |
| 关键词搜索（兜底） | LLM 工具内部使用 | `keyword-search` |
| 万豪系酒店 / 套餐 | 暂未开指令 | `search-marriott-hotel` / `search-marriott-package` |

## 安装

### 1. 装插件

把整个 `astrbot_plugin_flyai/` 目录放到 `AstrBot/data/plugins/` 下，然后在 WebUI 插件页点刷新。

### 2. 装 flyai CLI（必须）

插件本身没有 Python 第三方依赖，但**需要宿主机有 Node.js 18+**：

```bash
npm i -g @fly-ai/flyai-cli
flyai keyword-search --query "三亚怎么玩"
```

Docker 部署的话，需要在容器内也能执行 `node`。如果装在别处，把绝对路径填到插件配置的 `cli_path` 里。

没装也能跑——插件会退回 `npx -y @fly-ai/flyai-cli` 临时拉取，代价是首次调用多花十几秒。

### 3. 检查环境

```
/飞猪诊断
```

会打印 node / npx / flyai 的探测结果和实际调用命令。

## 用法

```
/飞猪 五一杭州三天 人均2000 想住西湖附近
/机票 北京 成都 2026-11-25
/机票 上海 东京 2026-12-01 1500
/火车 上海 杭州 明天
/酒店 杭州 2026-11-25 2026-11-27 西湖
/景点 西安 历史古迹
/景点 三亚 亲子
```

日期支持 `2026-11-25`、`11-25`、`今天`、`明天`、`后天`。机票/火车不写日期时默认查 7 天 / 1 天后；酒店不写离店默认住两晚。

## LLM 工具

插件注册了 3 个 function tool，开启 Agent 后模型会自己判断什么时候该查飞猪：

- `flyai_travel_search(query)` — 开放型问题（哪好玩、怎么安排）
- `flyai_flight_search(origin, destination, dep_date, max_price?)` — 明确提到机票航班
- `flyai_hotel_search(dest_name, check_in_date?, check_out_date?, poi_name?)` — 提到酒店住哪

## 配置项

| 键 | 默认 | 说明 |
|---|---|---|
| `cli_mode` | `auto` | `auto` / `flyai` / `npx` |
| `cli_path` | 空 | flyai 可执行文件绝对路径，留空自动探测 |
| `api_key` | 空 | `FLYAI_API_KEY`，填了才有精确价格 |
| `timeout` | 90 | 单次查询超时（秒） |
| `max_items` | 5 | 每条消息展示几条 |
| `enable_llm_tool` | true | 是否注册 LLM 工具 |
| `show_price_note` | true | 打码价时追加提示 |

## 三个必须知道的限制

**1. 价格默认是打码的。**
不配 API Key 时飞猪返回的是 `¥8xx`、`2x`、`1xxx` 这种区间价，不是 bug，是上游行为。填 `api_key` 才能拿到精确数字。

**2. 只能查，不能订。**
`flyai` 没有下单接口，所有结果只带 `jumpUrl` 短链，用户点开跳飞猪 App 支付。别指望插件帮你自动抢票。

**3. `ai-search` 很慢。**
实测单次 15–40 秒。所以 `/飞猪` 会先回一句「查一下，稍等…」再出结果，`timeout` 别调低于 60。结构化指令（机票/酒店/景点）通常 2–5 秒就回。

## 目录结构

```
astrbot_plugin_flyai/
├── main.py              # 指令、配置读取、生命周期
├── metadata.yaml
├── _conf_schema.json
├── core/
│   ├── cli.py           # flyai 子进程封装：Windows .cmd 兼容、超时、JSON 兜底解析
│   ├── render.py        # 三种异构返回体统一渲染成聊天可读文本
│   └── util.py          # 日期归一、景点分类白名单、价格解析
├── tools/
│   ├── base.py          # FlyAITool 基类（plugin_ref 注入）
│   ├── travel.py        # 3 个 LLM 工具
│   └── __init__.py      # build_tools(plugin)
└── requirements.txt
```

## 二次开发

- 想加万豪那两条能力：在 `main.py` 里照 `/酒店` 写一个 handler 调 `search-marriott-hotel` 或 `search-marriott-package` 即可，`core/render.py` 已经兼容它们返回的结构，不用改渲染层。
- 想调排序策略：机票/火车默认 `sort_type=3`（价格升序），酒店默认 `sort=rate_desc`（评分优先），都在 `main.py` 的 params 里。
- 加新的 LLM 工具：在 `tools/travel.py` 里继承 `FlyAITool`，把类加进文件末尾的 `ALL_TOOLS`，再补一下 `tools/__init__.py` 的 `EXPECTED_TOOL_NAMES`。
- 发布到插件市场前记得改 `metadata.yaml` 里的 `author` 和 `repo`。

## 许可

MIT。flyai 本身也是 MIT，版权归阿里巴巴飞猪所有。
