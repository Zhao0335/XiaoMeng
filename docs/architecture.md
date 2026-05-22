# 小萌 扩展架构文档

> 最后更新：2026-05-22（新增 Docker 部署章节）

---

## 一、三层扩展模型

```
┌─────────────────────────────────────────────────────────┐
│  Skills（data/skills/）                                  │
│  ── LLM 上下文文档，描述"可以做什么/怎么做"               │
│  ── SKILL.md 格式，注入 system prompt                    │
│  ── 无可执行代码，纯文本                                  │
├─────────────────────────────────────────────────────────┤
│  Tools（core/qq/tools.py + 插件注册）                    │
│  ── LLM function-calling 原子操作                        │
│  ── 内置工具：hardcoded 在 tools.py（稳定、通用）         │
│  ── 插件工具：由 Plugins 动态注册                         │
├─────────────────────────────────────────────────────────┤
│  Plugins（data/plugins/）                                │
│  ── Python 包，扩展工具集 + 可选后台服务                  │
│  ── 每个插件 = plugin.py + 可选 SKILL.md + config.json   │
│  ── 热加载，不需改核心代码                                │
└─────────────────────────────────────────────────────────┘
```

**对应关系：**

| 要做的事 | 放在哪里 |
|---------|---------|
| 告诉 LLM"你可以用 scheduler 发题目" | `data/skills/scheduler.md`（SKILL.md）|
| 提供 `scheduler_add` 工具让 LLM 调用 | `data/plugins/scheduler/plugin.py` |
| 实现 `read_file`/`web_search` 等通用能力 | `core/qq/tools.py`（内置） |
| 启动/管理 scheduler 守护进程 | `data/skills/scheduler/main.py` |

---

## 二、Skills（技能文档）

位置：`data/skills/`

### 格式（SKILL.md）

```markdown
---
name: my-skill
description: 一句话描述
version: 1.0.0
emoji: 🔧
always: false          # true = 总是注入 system prompt
risk: read_only        # read_only / sensitive / dangerous
min_user_level: stranger  # stranger / admin / owner
min_model_tier: cloud     # local / cloud / pro
tags:
  - tag1
---

# 技能名

LLM 看到的说明文档，告诉它这个技能有什么能力、有哪些工具可用、操作流程是什么。
```

### 权限过滤

- `min_model_tier: cloud` → LOCAL 14b 模型看不到这个技能（避免占 context）
- `min_user_level: admin` → 只有管理员和主人才能触发

### 目录结构

```
data/skills/
├── scheduler.md           # 定时任务技能文档
├── daily-quiz/
│   └── SKILL.md           # 每日题目技能文档
├── self-improving/
│   └── SKILL.md
├── scheduler/
│   └── main.py            # scheduler 守护进程（不是 skill，是独立程序）
└── ...
```

---

## 三、Tools（内置工具）

位置：`core/qq/tools.py`

内置工具是稳定的、通用的原子操作，hardcoded 在核心代码中。

### 当前内置工具列表

| 工具名 | 功能 | 权限 |
|--------|------|------|
| `web_search` | DuckDuckGo 搜索 | 全部 |
| `add_memory` | 写入记忆 | 全部 |
| `search_memory` | 搜索记忆 | 全部 |
| `update_soul` | 更新 SOUL.md | 全部 |
| `recall_conversations` | 查看历史对话 | admin+ |
| `read_file` | 读取 data/ 下的文件 | 全部 |
| `write_file` | 写入 data/ 下的文件 | admin+ |
| `list_files` | 列出目录 | 全部 |
| `delete_file` | 删除文件 | admin+ |
| `send_file` | 发送文件到当前聊天 | 全部 |
| `send_voice` | TTS 合成并发语音 | 全部 |
| `send_message` | 发消息/等待回复 | 全部 |
| `run_command` | 执行 shell 命令 | owner |
| `reload_skills` | 重新加载技能文件 | admin+ |

### 按模型层级过滤

```python
LOCAL_OK_TOOLS = {"search_memory", "recall_conversations"}
# LOCAL 模型只能用这两个工具（轻量，不占 context）
# CLOUD/PRO 模型可以用全部工具
```

---

## 四、Plugins（插件）

位置：`data/plugins/`

每个插件是一个目录，包含：

```
data/plugins/<plugin-name>/
├── plugin.py     # 必须：继承 PluginBase，注册工具
├── SKILL.md      # 可选：LLM 技能文档（自动注入 system prompt）
└── config.json   # 可选：插件配置
```

### plugin.py 格式

```python
from core.plugins.base import PluginBase, PluginMetadata, ToolDefinition

class MyPlugin(PluginBase):

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="插件描述",
        )

    async def on_initialize(self) -> bool:
        self.register_tool(ToolDefinition(
            name="my_tool",
            description="工具描述",
            parameters={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "参数说明"}
                },
                "required": ["arg1"],
            },
            min_user_level=1,      # 0=陌生人, 1=管理员, 2=主人
            progress_msg="执行中~", # LLM 调用期间显示的提示（可选）
        ))
        return True

    async def on_tool_call(self, tool_name: str, arguments: dict, context: dict) -> str:
        if tool_name == "my_tool":
            return f"执行结果: {arguments['arg1']}"
        return f"未知工具: {tool_name}"

    async def on_shutdown(self) -> None:
        pass
```

### ToolDefinition 字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | — | 工具名（全局唯一） |
| `description` | str | — | LLM 看到的工具描述 |
| `parameters` | dict | — | OpenAI function-calling 格式的参数 schema |
| `min_user_level` | int | `0` | 最低权限（0=陌生人, 1=管理员, 2=主人）|
| `progress_msg` | str | `None` | 工具执行期间展示给用户的提示语 |

**权限双重保障：**
- **Schema 过滤**：`PluginManager.get_all_tool_schemas(user_level)` 只向 LLM 返回 `user_level >= min_user_level` 的工具，LLM 根本看不到无权限的工具。
- **执行时校验**：`dispatch_tool_call()` 再次检查权限，防止绕过 schema 过滤的攻击。

### context 字段

`on_tool_call` 的 `context` 参数包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_key` | str | 会话标识（`group:xxx` 或 `private:xxx`） |
| `sender_qq` | int | 发送者 QQ 号 |
| `level` | PermLevel | 权限级别（0=stranger, 1=admin, 2=owner） |
| `identity` | str | canonical 身份名 |
| `napcat` | NapCatClient | QQ API 客户端 |
| `data_dir` | Path | data/ 目录路径 |
| `is_private` | bool | 是否私聊 |
| `target_id` | int | 发送目标（group_id 或 user_id） |
| `task` | AsyncTask | 当前异步任务对象 |

### 当前插件列表

| 插件 | 提供的工具 |
|------|-----------|
| `scheduler` | `scheduler_list/add/remove/start/stop/status` |

### 生命周期

1. **发现**：启动时扫描 `data/plugins/`，找到含 `plugin.py` 的目录
2. **加载**：动态 import `plugin.py`，实例化插件类
3. **初始化**：调用 `on_initialize()`，注册工具
4. **SKILL.md 注册**：`gateway._register_plugin_skills()` 扫描每个已初始化插件的目录，若有 `SKILL.md` 则加载进 `SkillRegistry`，与 `data/skills/` 下的技能统一管理
5. **运行**：每次 LLM 调用工具时，`dispatch_tool_call` 路由到对应插件
6. **关闭**：调用 `on_shutdown()`

> **注意**：`reload_skills` 工具（`_reload_skills()`）也会重新扫描插件目录中的 SKILL.md，确保热重载后插件技能文档同步更新。

### 热重载

修改插件后，可以通过 `run_command` 重启 bot，或（未来）通过 `reload_plugin` 热重载。

---

## 五、进程间消息发送（Bot HTTP 中继）

scheduler 守护进程是独立的 Python 进程，没有 NapCat WebSocket 连接。它通过 bot 暴露的本地 HTTP 中继发送消息或触发 AI 指令：

```
scheduler daemon
    │
    ├─ POST /send_msg  {"message": "...", "group_id": 123456}
    │      ↓
    │  self._napcat.send_group_msg(...)
    │      ↓
    │  NapCat WebSocket → QQ 消息
    │
    └─ POST /instruct  {"prompt": "...", "target": {"group_id": 123456}}
           ↓
       QQGateway._task_manager.create_and_run(forced_level=ADMIN)
           ↓
       LLM 推理（含工具调用，全量能力）
           ↓
       self._napcat.send_group_msg(...)  →  QQ 消息
```

**为什么不直连 NapCat HTTP？**
NapCat 仅暴露 WebSocket 端口（3002），没有独立的 HTTP API 端口。Bot 本地中继（3003）由 bot 自己管理，只监听 127.0.0.1，外部无法访问。

**配置项**：`qq_config.json` 中 `bot_relay_port`（默认 3003）

---

## 六、日程系统设计原则

> **哪里定的时，哪里提醒。**

| 场景 | 在哪里设置 | 提醒发到哪里 |
|------|-----------|-------------|
| QQ 群/私聊日程 | 在 QQ 聊天中对小萌说 | QQ 群/私聊 |
| 未来外部应用日程 | 在对应 App（如日历）里设置 | 对应 App |

**QQ 内日程**（当前实现）：
- 任何 admin+ 用户均可通过对话要求小萌创建定时任务
- scheduler plugin（`data/plugins/scheduler/`）提供工具给 LLM 调用
- scheduler daemon（`data/skills/scheduler/main.py`）在后台按时发送
- 提醒回到设置该任务的 QQ 群/私聊

**任务类型**：
| 类型 | 说明 |
|------|------|
| `cron` | 定时发固定文本消息 |
| `instruct` | 定时触发 AI 指令，小萌全量推理后发结果（支持所有工具） |
| `interval` | 按间隔分钟数循环发固定消息 |
| `once` | 一次性定时任务 |

**跨应用日程**（未来扩展）：
- 需要单独的插件（如 `data/plugins/google-calendar/`）
- 各应用维护各自的发送通道，不经过 Bot 中继

---

## 七、工具分发链路

```
LLM 输出 tool_call
    │
    ▼
QQToolExecutor.execute(tool_name, arguments)
    │
    ├── 内置工具（tools.py 中 hardcoded）→ 直接执行
    │
    └── 未知工具 → PluginManager.dispatch_tool_call()
                        │
                        └── 找到注册该工具的插件 → plugin.on_tool_call()
```

工具 schema 构建链路：

```
base_tools（按模型层级过滤的内置工具）
    +
PluginManager.get_all_tool_schemas(user_level)  ← 仅 CLOUD/PRO 模型，且按权限过滤
    │
    ▼
active_tools → 传给 LLM 作为 function-calling tools
```

权限校验链路（双重保障）：

```
1. Schema 构建时：user_level < tool.min_user_level → 工具从 schema 中剔除
   （LLM 不知道这个工具存在，从源头屏蔽）

2. 执行时：dispatch_tool_call() 再次检查 user_level
   （防御深度，即使 schema 被绕过也拦截）
```

---

## 八、文件收发

### 收 QQ 文件（用户发给 bot）

| 类型 | 处理方式 |
|------|---------|
| 图片 | 提取 file_id → `get_file` API → base64 → 视觉模型描述 |
| 其他文件（.txt/.pdf/.docx 等） | 提取 file_id → `get_file` API（base64）→ 写到 `data/uploads/` → 告诉 LLM 路径 |

**NapCat 配置要求**：llbot 的 `config_<botqq>.json` 中必须设置 `"enableLocalFile2Url": true`，否则 `get_file` 只返回容器内路径（无法直接读取）。已在 `xiaomeng-napcat` 容器中开启。

非图片文件下载后，LLM 收到的消息里会附带：
```
[文件已保存到 uploads/report.txt，可用 read_file 读取]
```
LLM 调用 `read_file("uploads/report.txt")` 读取内容，支持格式：

| 格式 | 库 | 说明 |
|------|----|------|
| `.pdf` | pymupdf | 按页提取文本 |
| `.docx` | python-docx | 提取所有段落文本 |
| `.pptx` | python-pptx | 提取所有幻灯片文本框 |
| `.xlsx/.xls` | openpyxl | 逐 sheet 逐行提取单元格 |
| 其他 | 内置 | 当 UTF-8 纯文本读取 |

### 发文件给 QQ（bot 发给用户）

用 `send_file` 工具，路径相对 `data/` workspace：
```
send_file(path="uploads/result.csv", caption="处理结果")
```

---

## 九、添加新能力的决策树

```
要给小萌加新能力？
    │
    ├── 只需要告诉 LLM 怎么用现有工具？
    │   └── 写 SKILL.md，放到 data/skills/
    │
    ├── 需要让 LLM 调用新的原子操作？
    │   ├── 通用能力（记忆/文件/搜索等）→ 加到 core/qq/tools.py
    │   └── 领域能力（bilibili/live2d/scheduler等）→ 建 data/plugins/<name>/plugin.py
    │
    └── 需要后台常驻服务（定时/监听）？
        └── 在插件的 on_initialize() 里启动 asyncio.Task
            或写独立守护进程（参考 scheduler/main.py）
```

---

## 十、Docker 部署

所有服务统一用 `docker-compose.yml`（位于 `/home/qwq/zcx_ai_group_friend/docker-compose.yml`）管理。

### 服务一览

| 容器 | 镜像 | 作用 |
|------|------|------|
| `xiaomeng-qq` | `linyuchen/pmhq:7.3.0` | QQ 登录进程（QQNT headless） |
| `xiaomeng-napcat` | `linyuchen/llbot:7.11.0` | OneBot v11 WebSocket 服务 |
| `xiaomeng-bot` | 本地构建 | 小萌 bot 主进程 + scheduler 守护进程 |

### 网络设计

- `xiaomeng-qq` 和 `xiaomeng-napcat` 使用 bridge 网络 `xiaomeng_net`，互相通过容器名访问。
- `xiaomeng-bot` 使用 **`network_mode: host`**，直接共享宿主机网络栈，原因：
  - NapCat WebSocket 绑定在 `127.0.0.1:3002`（只对宿主机可见）
  - TTS 服务绑定在 `127.0.0.1:9882`
  - 代理服务绑定在 `127.0.0.1:20171`
  - Bot 中继本身监听在 `127.0.0.1:3003`（scheduler 调用）

### 目录挂载

```
宿主机                                     容器内
/home/qwq/napcat_xiaomeng/qq_volume   → /root/.config/QQ   (napcat 容器)
/home/qwq/zcx_ai_group_friend/XiaoMeng/data → /app/data   (bot 容器)
```

代码（`core/`、`*.py`）在镜像构建时 `COPY` 进去；`data/` 目录 bind-mount，保持持久化且不需重建镜像即可修改配置/技能。

### Dockerfile 分层策略

```
FROM python:3.13-slim
  → apt 系统包（LaTeX、ffmpeg、libgl…）      # 变化频率极低
  → pip install requirements.txt             # 仅在 requirements 变更时重建
  → pip install 额外包（matplotlib、PyMuPDF 等）
  → COPY 源代码                              # 代码变更仅重建最后一层
```

### 容器内进程

`entrypoint.sh` 在同一容器内启动两个进程：
1. `python data/skills/scheduler/main.py` — 后台守护（`&`）
2. `python run_qq.py` — bot 主进程（`exec`，前台，决定容器生命周期）

容器重启时 `entrypoint.sh` 会先清理 `scheduler.pid`，避免残留 PID 文件导致 scheduler 拒绝启动。

### 常用操作

```bash
# 启动/重启所有服务
cd /home/qwq/zcx_ai_group_friend
docker compose up -d

# 重建 bot 镜像（代码有更新时）
docker compose build xiaomeng-bot
docker compose up -d xiaomeng-bot

# 查看 bot 日志
docker compose logs -f xiaomeng-bot

# 停止所有服务
docker compose down
```

### 首次迁移步骤

```bash
# 1. 停止旧 systemd 服务
sudo systemctl stop xiaomeng-bot
sudo systemctl disable xiaomeng-bot

# 2. 停止旧 napcat compose（如果在 /home/qwq/napcat_xiaomeng/ 下运行）
cd /home/qwq/napcat_xiaomeng && docker compose down

# 3. 构建并启动新 compose
cd /home/qwq/zcx_ai_group_friend
docker compose build xiaomeng-bot
docker compose up -d
```

---

## 十一、未来计划

| 能力 | 实现方式 |
|------|---------|
| Bilibili 弹幕互动 | `data/plugins/bilibili/plugin.py`，on_initialize 启动弹幕监听 |
| Live2D 表情控制 | `data/plugins/live2d/plugin.py`，注册 `set_expression` 工具 |
| Sub-agent 任务派发 | 在 gateway 加 `run_background_task` 工具，LLM 可以 dispatch 后台任务 |
| 图片生成 | `data/plugins/image-gen/plugin.py`，注册 `generate_image` 工具 |
