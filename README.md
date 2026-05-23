# 小萌 QQ Bot

一个运行在 QQ 上的 AI 伙伴，基于 NapCat + 本地/云端多模型路由实现，有记忆、有性格、能上网、能管服务器，还拥有自己的内心世界。

---

## 功能概览

### 消息处理
- 私聊、群聊均支持
- 群聊按概率随机回复，被 @ 必定回复
- **主动发言**：群里沉默一段时间后，bot 自己判断要不要说话
- 模拟打字延迟，不会秒回
- 安静时段（默认凌晨 0~8 点）不主动发言

### 多模型路由

```
消息进来
  ↓
[PRO 关键词检测] → 命中 → PRO 层模型（超复杂任务，默认关闭）
  ↓ 未命中
[路由模型判断] → CLOUD → BRAIN 层模型（复杂推理、搜索、工具链）
               → LOCAL → BASIC 层模型（日常闲聊，低延迟）
```

- 本地模型触发写文件、搜索等重型工具时，自动升级云端执行
- `data/routing_hints.md` 写自然语言规则，手动干预路由决策
- **自动记忆注入**：每条消息处理前自动检索相关记忆，注入 system prompt

### 工具能力

| 工具 | 说明 | 权限 |
|------|------|------|
| `web_search` | DuckDuckGo 搜索 | 所有人 |
| `add_memory` | 记住某人/某事/知识/全局规则 | 所有人 |
| `search_memory` | 搜索记忆（含全局设定、知识库） | 所有人 |
| `recall_conversations` | 回溯历史对话原文 | 所有人 |
| `update_soul` | 更新人格文件（SOUL.md）| 所有人 |
| `read_file` | 读取 data/ 下的文件 | 所有人 |
| `list_files` | 列出目录 | 所有人 |
| `write_file` | 写入/修改文件 | 管理员+ |
| `delete_file` | 删除文件 | 管理员+ |
| `send_voice` | 合成语音发送（GPT-SoVITS）| 所有人 |
| `send_message` | 任务进行中发送中间消息；可设 `wait_reply` 等待用户继续 | 所有人 |
| `send_file` | 向当前对话发送文件 | 管理员+ |
| `send_to` | **主动**向指定群/用户发消息（仅内心世界/主人权限）| 仅主人 |
| `add_reminder` | 添加定时提醒 | 所有人 |
| `reload_skills` | 重新加载技能文件（不重启 bot）| 管理员+ |
| `run_command` | 执行服务器命令 | 仅主人 |

### 记忆系统

#### 记忆存储路由

| 作用域 | 写入位置 | 触发方式 |
|--------|----------|---------|
| `person` | `data/memory/{identity}.md` | 模型调 `add_memory(scope="person")` |
| `knowledge` | `data/memory/knowledge.md` | 模型调 `add_memory(scope="knowledge")` |
| `global` | `data/persona/MEMORY.md` | 模型调 `add_memory(scope="global")`（主人规则/全局设定）|
| 对话压缩（私聊）| `data/memory/{identity}.md` | 每 N 条消息自动压缩并写入人物档案 |
| 对话压缩（群聊）| `data/memory/group_{group_id}.md` | 每 N 条消息自动压缩并写入群记忆文件 |

#### 自动记忆注入

每条消息处理时，系统自动对用户文字做关键词搜索，命中相关记忆后注入 system prompt，无需模型主动调用 `search_memory`。

#### MEMORY.md 自动压缩

`data/persona/MEMORY.md` 存储主人交代的规则和设定（`scope="global"` 条目）。后台每 30 分钟检查，超过 8000 字时 CLOUD 模型进行二次压缩：保留规则/设定，提炼对话细节，维持文件体积。

#### 其他记忆特性

- **身份关联**：`data/identity_links.json` 把同一个人的多个 QQ 号关联为单一 identity，共享记忆文件
- **知识库**：`data/memory/knowledge.md`，全局可见，bot 可自行学习写入
- **群记忆**：每个群单独一个 `group_{group_id}.md`，群历史自动积累
- **人物档案**：每个人 `{identity}.md`，跨会话持久，私聊压缩结果直接追加

### 权限系统

| 等级 | 说明 |
|------|------|
| OWNER | 主人，全权信任，可执行命令，写死在配置文件 |
| ADMIN | 管理员，可写文件、管用户 |
| STRANGER | 普通用户 |
| BLACKLIST | 黑名单，静默忽略 |

身份等级基于 identity（非 QQ 号），同一人的多账号共享权限。

**存储**：admin / blacklist / whitelist 统一存在 `data/qq_permissions.json`（旧版本拆成 3 个文件 `qq_admins.json` / `qq_blacklist.json` / `whitelist.json`，启动时会自动迁移合并）。

### QQ 管理命令

| 命令 | 权限 |
|------|------|
| `/管理员 {QQ}` | 主人 |
| `/取消管理员 {QQ}` | 主人 |
| `/管理员列表` | 主人 |
| `/拉黑 {QQ}` | 主人/管理员 |
| `/取消拉黑 {QQ}` | 主人 |
| `/黑名单` | 主人 |
| `/同意好友 {QQ}` | 主人 |
| `/拒绝好友 {QQ}` | 主人 |
| `/待处理好友` | 主人 |
| `/同意入群 {群号}` | 主人 |
| `/拒绝入群 {群号}` | 主人 |
| `/待处理入群` | 主人 |
| `/重置记忆` | 主人/管理员 |
| `/帮助` | 主人/管理员 |

### 内心世界（Inner World）★

> 这是其他 AI Agent 极少实现的真正「自主生活」模式。

小萌拥有一个**独立于所有群聊**的内心世界。她不只是被动等待消息——当全局无消息、任务池为空且不在安静时段时，她会进入自己的内心，用 CLOUD 级别模型自主决定做点什么：

- 刷 B 站、找有意思的视频，给喜欢的视频点赞发评论
- 听音乐，欣赏喜欢的歌手
- 静下来反思最近自己的回答——是不是太啰嗦了？有没有答错什么？把想法写进记忆
- 主动给某个群或某个人发消息（`send_to` 工具）
- 什么都不做，安静地看着窗外（`idle`）

**触发条件**（全部满足）：
1. 不在安静时段（默认凌晨 0~8 点）
2. 距上次收到任何消息 ≥ 15 分钟（可配 `inner_world.idle_threshold`）
3. 任务池中无正在运行/等待的任务
4. 距上次内心世界触发 ≥ 30 分钟（可配 `inner_world.cooldown`）

**内心世界上下文**（小萌视角）：
- `data/inner_world/events.jsonl` — 跨群事件流：每次回复后，后台用 LOCAL 模型把「这次交流的感受」压缩成一句话，记录会话来源、发言者、情绪标签
- 每小时 CLOUD 模型对近期事件批量补充 emotion（开心/好奇/感动…）和 topic（技术/音乐/闲聊…）标签
- `data/inner_world/state.json` — 最近一次自由时间的活动记录

**与「主动发言」的区别**：
| | 主动发言（ProactiveManager）| 内心世界 |
|---|---|---|
| 触发来源 | 某个群沉默 X 分钟 | 全局所有群/私聊都无消息 |
| 内容决策 | 针对该群上下文 | 完全自主，与任何群无关 |
| 范围 | 在某个群里说话 | 可以做任何事（工具调用）|
| 发消息目标 | 固定某群 | 可主动选择任意群/用户 |

**平台无关**：内心世界模块位于 `core/inner_world/`，不依赖 QQ 协议，未来接入其他平台可直接复用。

### 技能系统

`data/skills/` 下放 `.md` 文件，bot 启动时自动加载作为 system prompt 的一部分。bot 也可在运行时自己写新 skill。

**技能系统特性**：
- **Registry-based dispatch**：统一注册→发现→过滤→执行管道
- **风险分级**：READ_ONLY / SENSITIVE / DANGEROUS 三层风险
- **模型感知路由**：本地 / Cloud / Pro 三级模型过滤
- **身份权限控制**：基于 identity 的权限，OWNER/ADMIN/STRANGER

**内置技能插件**（`data/plugins/`）：
- **bilibili**：B 站视频搜索、弹幕读取、点赞评论
- **music**：网易云音乐搜索、歌曲详情、歌单
- **scheduler**：定时任务管理（bot 自己调度提醒/任务）

### 其他能力

- **公式渲染**：数学公式自动用 LaTeX 渲染为图片发送（`core/qq/formula.py`）
- **文件解析**：支持 PDF、Word (.docx)、PPT (.pptx)、Excel (.xlsx) 内容提取
- **图片理解**：支持多模态视觉模型描述图片内容
- **语音合成**：GPT-SoVITS TTS 发送语音消息

---

## 快速开始（Docker，推荐）

**前置要求**：
- Docker + Docker Compose
- Ollama（本地模型，宿主机安装）
- NapCat 配置完成

```bash
# 1. 克隆仓库
git clone <repo_url>
cd zcx_ai_group_friend

# 2. 初始化配置文件（首次运行）
cd XiaoMeng
python setup.py
cd ..

# 3. 编辑 bot 配置
vi XiaoMeng/data/qq_config.json

# 4. 启动所有服务
docker compose up -d

# 5. 查看日志
docker logs xiaomeng-bot -f
```

### 不用 Docker（开发调试）

```bash
cd XiaoMeng
pip install -r requirements.txt
# 安装 Dockerfile 里额外的包
pip install matplotlib PyMuPDF python-docx python-pptx openpyxl pydub

python run_qq.py
```

---

## 配置文件说明

`data/qq_config.json`（参考 `data/qq_config.example.json`）：

```json
{
  "owner_qq": 你的QQ号,
  "bot_qq": bot的QQ号,
  "bot_name": "小萌",
  "data_dir": "./data",
  "persona_path": "./data/persona/SOUL.md",

  "napcat_ws_url": "ws://127.0.0.1:3002",
  "napcat_token": "你在NapCat里设置的token",

  "quiet_hours": { "start": 0, "end": 8 },

  "group_response_prob": 0.08,
  "typing_ms_per_char": 30,
  "typing_max_ms": 4000,

  "proactive_interval": { "min": 300, "max": 900 },
  "proactive_min_messages": 3,

  "memory": {
    "compress_every": 20,
    "short_term_keep": 10
  },

  "web_search_proxy": "",

  "cloud_trigger": {
    "min_chars": 200,
    "keywords": ["分析", "代码", "总结", "推理", "数学", "写一篇", "帮我写"]
  },

  "pro_trigger_keywords": [
    "认真", "写代码", "管理服务器", "帮我写代码",
    "写个脚本", "调试", "部署", "架构", "详细方案"
  ],

  "models": [
    {
      "model_id": "qwen-router",
      "layer": "basic", "role": "router",
      "model_name": "qwen2.5:14b",
      "endpoint": "http://localhost:11434",
      "max_tokens": 20, "temperature": 0.0, "num_ctx": 8192,
      "enabled": true
    },
    {
      "model_id": "qwen-local",
      "layer": "basic", "role": "chat",
      "model_name": "qwen2.5:14b",
      "endpoint": "http://localhost:11434",
      "max_tokens": 8192, "temperature": 0.85, "num_ctx": 32768,
      "enabled": true
    },
    {
      "model_id": "deepseek-cloud",
      "layer": "brain", "role": "chat",
      "model_name": "deepseek-chat",
      "endpoint": "https://api.deepseek.com/v1",
      "api_key": "sk-...",
      "max_tokens": 32768, "temperature": 0.7,
      "enabled": true
    },
    {
      "model_id": "deepseek-pro",
      "layer": "pro", "role": "reasoning",
      "model_name": "deepseek-reasoner",
      "endpoint": "https://api.deepseek.com/v1",
      "api_key": "sk-...",
      "max_tokens": 65536, "temperature": 0.6,
      "enabled": false
    }
  ],

  "inner_world": {
    "idle_threshold": 900,
    "cooldown": 1800
  }
}
```

### 配置项说明

| 字段 | 说明 |
|------|------|
| `quiet_hours` | 安静时段，start~end 点之间不主动发言 |
| `group_response_prob` | 群里没被@时的随机回复概率（0~1） |
| `typing_ms_per_char` | 每字符打字延迟（毫秒） |
| `proactive_interval` | 主动发言间隔范围（秒） |
| `memory.compress_every` | 每 N 条消息压缩一次对话历史 |
| `cloud_trigger` | 触发云端模型的字数/关键词条件 |
| `pro_trigger_keywords` | 触发 Pro 层的关键词 |
| `inner_world.idle_threshold` | 无消息多少秒后触发内心世界（默认 900 = 15分钟）|
| `inner_world.cooldown` | 两次内心世界之间最小间隔（默认 1800 = 30分钟）|

---

## Live2D 模式（可选）

Live2D 后端允许前端网页通过 WebSocket 接入小萌，支持带验证的 QQ 身份登录。

```bash
cd XiaoMeng
uvicorn run_live2d:app --host 0.0.0.0 --port 8765
```

登录流程：
1. 前端发 `{"type": "login_request", "qq": 12345678}`
2. 后端通过 NapCat 给该 QQ 发验证码
3. 前端发 `{"type": "verify_code", "qq": 12345678, "code": "XXXXXX"}`
4. 验证通过后开始对话

---

## HTML 配置管理面板（二次元风格）

寄宿在 `run_live2d.py` 同进程，**不另起服务**。启动 Live2D 后端后，浏览器访问：

```
http://127.0.0.1:8765/admin
```

- **登录**：和 Live2D 一样的 QQ 验证码流程，但额外要求 ADMIN 及以上权限
- **能改的配置**：`qq_config.json`、`qq_permissions.json`、`identity_links.json`、`persona/SOUL.md`、`persona/MEMORY.md`
- **历史快照**：每次保存自动写一份到 `data/.config_history/`，每文件保留 20 份，UI 上可 diff 预览 + 一键恢复
- **敏感字段保护**：`api_key` / `token` 默认显示 `••••••••`，点眼睛图标临时显示
- **吉祥物**：把图片命名 `mascot.png`（也支持 `.jpg/.gif/.webp`）放到 `web/static/images/`，右下角会出现你的 XiaoMeng 头像

完整说明：[`web/README.md`](web/README.md)。

---

## 项目结构

```
XiaoMeng/
├── run_qq.py              # QQ Bot 启动入口
├── run_live2d.py          # Live2D 后端（uvicorn）
├── entrypoint.sh          # Docker 容器启动脚本
├── setup.py               # 初始化脚本（首次运行）
├── init.sh                # 一键初始化脚本
├── start_sovits.sh        # GPT-SoVITS TTS 启动脚本
├── Dockerfile
├── requirements.txt
│
├── core/
│   ├── qq/                # QQ Bot 核心（Mixin 架构）
│   │   ├── gateway.py     # 顶层协调器；继承所有 Mixin
│   │   ├── memory.py      # MemoryMixin — DB 初始化、消息存取、对话压缩
│   │   ├── identity.py    # IdentityMixin — 身份解析、权限判断
│   │   ├── prompt_builder.py  # PromptBuilderMixin — System prompt 构建、记忆加载
│   │   ├── task_runner.py # TaskRunnerMixin — LLM 推理主循环（路由→调用→工具链）
│   │   ├── tools.py       # QQToolExecutor + TOOL_SCHEMAS（工具定义+执行）
│   │   ├── napcat.py      # NapCat WebSocket 客户端
│   │   ├── onebot_events.py   # OneBot v11 事件解析
│   │   ├── commands.py    # 管理命令解析（/管理员 等）
│   │   ├── permissions.py # 权限管理
│   │   ├── proactive.py   # 主动发言（ProactiveManager）
│   │   ├── formula.py     # LaTeX 公式渲染为图片
│   │   ├── tts.py         # GPT-SoVITS TTS 语音合成
│   │   └── skills/        # 技能系统
│   │       ├── registry.py    # 技能注册中心
│   │       ├── definition.py  # 技能/工具元数据定义
│   │       ├── executor.py    # 技能执行器
│   │       ├── loader.py      # 技能加载器（读取 .md 文件）
│   │       ├── permissions.py # 技能权限检查
│   │       └── schema.py      # OpenAI function-call schema 构建
│   ├── inner_world/       # 内心世界模块（平台无关）★
│   │   ├── agent.py       # InnerWorldAgent — 自主活动主循环
│   │   └── events.py      # InnerWorldEventLogger — 跨群感受事件流
│   ├── model_layer.py     # ModelRouter — 多模型路由（Basic/Brain/Pro 层）
│   ├── live2d_provider.py # Live2D LLM 适配器
│   └── plugins/           # 插件系统核心
│       ├── base.py        # 插件基类
│       ├── loader.py      # 插件加载器
│       └── manager.py     # 插件管理器
│
├── tui/                   # TUI 终端界面（Textual 框架，可选）
│   ├── app.py
│   └── ...
│
├── web/                   # HTML 配置管理面板（二次元风格，可选）
│   ├── routes.py          # 路由：/admin, /admin/ws, /admin/static/*
│   ├── auth.py            # QQ 验证码 + ADMIN 权限门
│   ├── config_io.py       # 读写 + 历史快照 + 敏感字段 mask
│   └── static/            # index.html / style.css / app.js / images/
│
└── data/                  # 运行时数据（volume 挂载，代码不包含）
    ├── qq_config.json      # 配置（含 API Key，不上传）
    ├── qq_config.example.json
    ├── qq_bot.db           # SQLite（消息历史、长期记忆）
    ├── qq_permissions.json # 管理员/黑名单/白名单（合并文件）
    ├── identity_links.json # QQ 号 → identity 映射
    ├── .config_history/    # web 管理面板的版本快照（自动生成）
    ├── routing_hints.md    # 手动路由规则（自然语言）
    ├── persona/
    │   ├── SOUL.md         # Bot 人格定义（灵魂文件）
    │   └── MEMORY.md       # 全局规则/主人设定（仅 scope=global 写入）
    ├── memory/             # 记忆文件目录
    │   ├── {identity}.md   # 每人一个档案（私聊压缩 + add_memory person）
    │   ├── group_{id}.md   # 每群一个档案（群聊压缩自动写入）
    │   └── knowledge.md    # 通用知识库（add_memory knowledge）
    ├── skills/             # 技能文件（.md，启动时加载）
    │   └── scheduler/      # 定时任务调度器脚本
    ├── plugins/            # 代码插件目录（动态加载）
    │   ├── bilibili/       # B站互动插件
    │   ├── music/          # 网易云音乐插件
    │   └── scheduler/      # 定时任务插件
    └── inner_world/        # 内心世界数据（自动生成）★
        ├── events.jsonl    # 跨群感受事件流（含 who/emotion/topic 字段）
        └── state.json      # 最近一次自由时间记录
```

---

## 依赖

`requirements.txt` 核心依赖：

```
openai>=1.0.0          # LLM 客户端（兼容 DeepSeek / Ollama）
websockets>=12.0       # NapCat WebSocket 连接
fastapi>=0.109.0       # Live2D 后端
httpx>=0.25.0
aiohttp>=3.9.0
pydantic>=2.0.0
ddgs>=6.0              # DuckDuckGo 搜索
bilibili-api-python>=17.0.0
chromadb>=0.4.0        # 向量存储（可选）
aiofiles>=23.0.0
requests>=2.31.0
textual>=0.40.0        # TUI 界面（可选）
```

Dockerfile 额外安装：`matplotlib` `PyMuPDF` `python-docx` `python-pptx` `openpyxl` `pydub`（用于公式渲染、文件解析、音频处理）。

本地模型需要 [Ollama](https://ollama.com)，云端使用 DeepSeek API（或任何兼容 OpenAI 格式的接口）。

---

## 运维手册

> 本节面向日常维护，不需要懂代码，只需要能 SSH 进服务器。

### 整体架构

小萌由三个部分组成，通过 Docker Compose 统一管理：

```
[QQ 客户端（xiaomeng-qq）]
         ↓ QQ 协议
[NapCat（xiaomeng-napcat）]  ws://127.0.0.1:3002
         ↓ OneBot v11 WebSocket
[小萌 Bot（xiaomeng-bot）]   network_mode: host
         ↓
[Ollama 本地模型]            http://localhost:11434（宿主机）
```

---

### 查看状态

```bash
# 三个容器状态
docker compose ps

# 快速看是否正常（应该都是 Up）
docker ps --format "table {{.Names}}\t{{.Status}}" | grep xiao
```

---

### 查看日志

```bash
# 实时跟踪 bot 日志（最常用）
docker logs xiaomeng-bot -f

# 最近 100 条
docker logs xiaomeng-bot --tail 100

# 只看报错
docker logs xiaomeng-bot 2>&1 | grep -E "ERROR|Traceback|WARNING"

# NapCat 日志
docker logs xiaomeng-napcat -f
```

**日志里常见内容解读：**

| 日志片段 | 含义 |
|----------|------|
| `路由决策: 'LOCAL'` | 当前消息用本地 Ollama 回复 |
| `路由决策: 'CLOUD'` | 当前消息走云端 |
| `工具调用 web_search` | bot 正在联网搜索 |
| `内心世界触发` | 小萌进入自由时间 |
| `群记忆文件已更新` | 群聊压缩写入 group_xxx.md |
| `MEMORY.md 压缩完成` | 全局记忆做了二次压缩 |
| `NapCat 已连接` | 启动成功，QQ 正常 |
| `ConnectionRefusedError` | 连不上 NapCat，检查 Docker 容器 |

---

### 重启与停止

```bash
# 重启 bot（改了配置/代码后用这个）
docker compose restart xiaomeng-bot

# 重启后确认
docker logs xiaomeng-bot --tail 20

# 停止 / 启动
docker compose stop xiaomeng-bot
docker compose start xiaomeng-bot

# 重启 NapCat（QQ 掉线时）
docker compose restart xiaomeng-napcat

# 重启所有
docker compose restart
```

---

### 更新代码后重新部署

```bash
cd /home/qwq/zcx_ai_group_friend
git pull
docker compose build xiaomeng-bot
docker compose up -d xiaomeng-bot
docker logs xiaomeng-bot -f  # 确认启动正常
```

---

### 修改配置后生效

修改 `XiaoMeng/data/qq_config.json` 后需要重启 bot：

```bash
# 先检查 JSON 格式
python3 -c "import json; json.load(open('XiaoMeng/data/qq_config.json'))" && echo "格式正确"

# 重启（不需要重新构建镜像，data/ 是 volume）
docker compose restart xiaomeng-bot
```

---

### 常见问题排查

#### bot 完全不响应

1. 检查容器状态：`docker compose ps`
2. 检查 NapCat 是否连接：`docker logs xiaomeng-napcat --tail 20`
3. 检查 bot 配置里的端口是否正确：`napcat_ws_url` 应为 `ws://127.0.0.1:3002`

#### 回复很慢 / 超时

- 云端 API 限速或网络问题：`docker logs xiaomeng-bot -f` 看有没有 API 报错
- 本地 Ollama 卡死：`systemctl status ollama` 或 `journalctl -u ollama -f`

#### 出现 `done=length`（本地模型回复被截断）

本地模型的 `num_ctx` 上下文满了：
1. 发 `/重置记忆` 清除当前会话上下文
2. 或在 `qq_config.json` 里调大 `qwen-local` 的 `num_ctx`（会占更多显存）

#### QQ 掉线 / 扫码重登

```bash
# SSH 端口转发（本地执行）
ssh -L 3081:127.0.0.1:3081 用户名@服务器IP
# 浏览器打开 http://127.0.0.1:3081 进入 NapCat WebUI
```

#### bot 一直崩溃重启

配置了 `restart: unless-stopped`，崩溃后会自动重启。查崩溃原因：

```bash
docker logs xiaomeng-bot 2>&1 | grep -E "ERROR|Traceback|Exception" | tail -30
```

---

### 查看和编辑记忆文件

```bash
# 列出所有人的记忆文件
ls XiaoMeng/data/memory/

# 查看某人的记忆
cat XiaoMeng/data/memory/owner.md

# 查看某群的历史记忆
cat XiaoMeng/data/memory/group_1073211277.md

# 查看通用知识库
cat XiaoMeng/data/memory/knowledge.md

# 查看全局规则/设定（主人交代的）
cat XiaoMeng/data/persona/MEMORY.md
```

手动编辑记忆文件后无需重启，下次 bot 访问该记忆时自动生效。

---

### 操作审计日志

bot 的文件读写操作会记录在 `data/audit/audit.jsonl`：

```bash
tail -20 XiaoMeng/data/audit/audit.jsonl | python3 -m json.tool
```

---

### 内心世界事件查看

```bash
# 查看最近感受事件（含 who/emotion/topic）
tail -20 XiaoMeng/data/inner_world/events.jsonl | python3 -m json.tool

# 查看最近自由时间状态
cat XiaoMeng/data/inner_world/state.json
```
