# 小萌 QQ Bot

一个运行在 QQ 上的 AI 伙伴，基于 NapCat + 本地/云端多模型路由实现，有记忆、有性格、能上网、能管服务器。

---

## 功能概览

### 消息处理
- 私聊、群聊均支持
- 群聊按概率随机回复，被 @ 必定回复
- 主动发言：群里沉默一段时间后，bot 自己判断要不要说话
- 模拟打字延迟，不会秒回
- 安静时段（默认凌晨 1~8 点）不主动发言

### 多模型路由

```
消息进来
  ↓
[PRO 关键词检测] → 命中 → deepseek-v4-pro（超复杂任务，默认关闭）
  ↓ 未命中
[路由模型判断] → CLOUD → deepseek-v4-flash（复杂推理、搜索）
               → LOCAL → qwen2.5:14b（日常闲聊）
```

本地模型触发写文件/搜索等重型工具时，自动升级云端执行。

可在 `data/routing_hints.md` 中写自然语言规则，手动干预路由决策。

### 工具能力

| 工具 | 说明 | 权限 |
|------|------|------|
| `web_search` | DuckDuckGo 搜索 | 所有人 |
| `add_memory` | 记住某人/某事 | 所有人 |
| `search_memory` | 搜索记忆 | 所有人 |
| `recall_conversations` | 回溯历史对话 | 所有人 |
| `update_soul` | 更新自己的人格文件 | 所有人 |
| `read_file` | 读取 data/ 下的文件 | 所有人 |
| `list_files` | 列出目录 | 所有人 |
| `write_file` | 写入/修改文件 | 管理员+ |
| `delete_file` | 删除文件 | 管理员+ |
| `run_command` | 执行服务器命令 | 仅主人 |

### 记忆系统

- **对话压缩**：每 N 条消息自动压缩为摘要，存入 SQLite
- **人物记忆**：每个人单独一个 `.md` 文件，跨会话持久
- **知识库**：`data/memory/knowledge.md`，全局可见，bot 可自行学习写入
- **向量检索**：ChromaDB 支持语义搜索记忆
- **身份关联**：把同一个人的多个 QQ 号关联起来，共享记忆

### 权限系统

| 等级 | 说明 |
|------|------|
| OWNER | 主人，全权信任，可执行命令，写死在配置文件 |
| ADMIN | 管理员，可写文件、管用户 |
| STRANGER | 普通用户 |
| BLACKLIST | 黑名单，静默忽略 |

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

### 技能系统

在 `data/skills/` 下放 `.md` 文件，bot 启动时自动加载作为 system prompt 的一部分。bot 也可以在运行时自己写新 skill。

---

## 快速开始

**前置要求**：NapCat 已安装并运行，Python 3.9+

```bash
# 1. 克隆仓库
git clone <repo_url>
cd XiaoMeng

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化配置和目录（自动创建 data/ 下的所有必要文件）
python setup.py

# 4. 编辑配置（填写 QQ 号、API Key、NapCat token）
vi data/qq_config.json

# 5. 启动 QQ Bot
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

  "napcat_ws_url": "ws://127.0.0.1:3001",
  "napcat_token": "你在NapCat里设置的token",

  "quiet_hours": { "start": 1, "end": 8 },

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
      "layer": "brain", "role": "reasoning",
      "model_name": "deepseek-v4-flash",
      "endpoint": "https://api.deepseek.com/v1",
      "api_key": "sk-...",
      "max_tokens": 32768, "temperature": 0.7,
      "enabled": true
    },
    {
      "model_id": "deepseek-pro",
      "layer": "pro", "role": "reasoning",
      "model_name": "deepseek-v4-pro",
      "endpoint": "https://api.deepseek.com/v1",
      "api_key": "sk-...",
      "max_tokens": 65536, "temperature": 0.6,
      "enabled": false
    }
  ],

  "live2d": {
    "tts_voice": "zh-CN-XiaoxiaoNeural",
    "port": 8765
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

---

## Live2D 模式（可选）

Live2D 后端允许前端网页通过 WebSocket 接入小萌，支持带验证的 QQ 身份登录。

```bash
# 启动 Live2D 后端（需要安装 llm-live2d 库）
cd XiaoMeng
uvicorn run_live2d:app --host 0.0.0.0 --port 8765
```

登录流程：
1. 前端发 `{"type": "login_request", "qq": 12345678}`
2. 后端通过 NapCat 给该 QQ 发验证码
3. 前端发 `{"type": "verify_code", "qq": 12345678, "code": "XXXXXX"}`
4. 验证通过后开始对话

---

## 项目结构

```
XiaoMeng/
├── run_qq.py              # QQ Bot 启动入口
├── run_live2d.py          # Live2D 后端启动入口（uvicorn）
├── setup.py               # 初始化脚本（首次运行）
├── requirements.txt
│
├── core/
│   ├── qq/
│   │   ├── gateway.py     # 核心协调器（消息路由、LLM调用、记忆管理）
│   │   ├── napcat.py      # NapCat WebSocket 客户端
│   │   ├── onebot_events.py # OneBot v11 事件解析
│   │   ├── tools.py       # 工具执行器
│   │   ├── commands.py    # 管理命令解析
│   │   ├── permissions.py # 权限管理
│   │   └── proactive.py   # 主动发言
│   ├── model_layer.py     # 多模型路由（Basic/Brain/Pro 层）
│   └── live2d_provider.py # Live2D LLM 适配器
│
├── models/
│   └── core.py            # 核心数据模型（用户、消息、情感等）
│
└── data/                  # 运行时数据（git ignored，用 setup.py 初始化）
    ├── qq_config.json      # 配置（含API Key，不上传）
    ├── qq_config.example.json
    ├── qq_bot.db           # 聊天数据库
    ├── qq_admins.json      # 管理员列表
    ├── qq_blacklist.json   # 黑名单
    ├── users.json          # 用户注册表
    ├── whitelist.json      # 白名单
    ├── identity_links.json # QQ 号关联（同一人的多个账号）
    ├── routing_hints.md    # 手动路由规则（自然语言）
    ├── persona/SOUL.md     # bot 人格定义
    ├── memory/             # 每个人的记忆文件（.md）
    ├── skills/             # 技能文件（.md，启动时加载）
    ├── notes/              # bot 的笔记
    ├── audit/              # 操作审计日志
    └── chroma/             # ChromaDB 向量库（语义记忆检索）
```

---

## 依赖

```
openai>=1.0.0
aiohttp>=3.9.0
httpx>=0.25.0
websockets>=12.0
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.0.0
pyyaml>=6.0
chromadb>=0.4.0
aiofiles>=23.0.0
requests>=2.31.0
python-multipart>=0.0.6
```

本地模型需要 [Ollama](https://ollama.com)，云端使用 DeepSeek API（或任何兼容 OpenAI 格式的接口）。

Live2D 模式额外需要 `llm-live2d` 库（单独安装）。

---

## 运维手册

> 本节面向日常维护，不需要懂代码，只需要能 SSH 进服务器。

### 整体架构

小萌由三个独立进程组成，互相之间通过本地端口通信：

```
[QQ 客户端 + NapCat]  ←─ Docker Compose  ─→  ws://127.0.0.1:3002
         ↓
  [小萌 Bot 进程]      ←─ systemd 服务    ─→  xiaomeng-bot.service
         ↓
    [Ollama 本地模型]  ←─ systemd 服务    ─→  ollama.service
```

三个组件任意一个挂了，bot 都会停止响应。排查问题时按上面从下往上检查。

---

### 查看状态

**一眼确认三个组件是否正常：**

```bash
systemctl status xiaomeng-bot --no-pager
systemctl status ollama --no-pager
docker ps --format "table {{.Names}}\t{{.Status}}" | grep xiao
```

正常状态应该看到：
- `xiaomeng-bot`：`active (running)`
- `ollama`：`active (running)`
- `xiaomeng-qq` 和 `xiaomeng-napcat` 两个容器：`Up X hours`

---

### 查看日志

**实时跟踪日志（最常用）：**

```bash
journalctl -u xiaomeng-bot -f
```

按 `Ctrl+C` 退出。

**查看最近 100 条：**

```bash
journalctl -u xiaomeng-bot -n 100 --no-pager
```

**只看报错：**

```bash
journalctl -u xiaomeng-bot -p err -n 50 --no-pager
```

**查看某个时间段的日志：**

```bash
journalctl -u xiaomeng-bot --since "2026-05-17 18:00" --until "2026-05-17 19:00" --no-pager
```

**查看 NapCat 容器日志：**

```bash
cd /home/qwq/napcat_xiaomeng
docker compose logs -f xiaomeng-napcat
```

**日志里常见内容解读：**

| 日志片段 | 含义 |
|----------|------|
| `路由决策: 'LOCAL' → 本地` | 当前消息用本地 Ollama 回复 |
| `路由决策: 'CLOUD' → 云端` | 当前消息走 DeepSeek 云端 |
| `工具调用 web_search` | bot 正在联网搜索 |
| `群消息 {群号} from {QQ} at_bot=True` | 有人 @ 了 bot |
| `[Ollama] done=length` | 本地模型因 token 限制截断（上下文太长） |
| `ConnectionRefusedError` | 连不上 NapCat，检查 Docker 容器 |
| `Restart=on-failure` 后 bot 重启 | bot 崩溃了，查前面日志找原因 |

---

### 重启与停止

**重启 bot（最常用，改了配置/代码后用这个）：**

```bash
sudo systemctl restart xiaomeng-bot
```

**重启后验证是否起来：**

```bash
systemctl status xiaomeng-bot --no-pager
journalctl -u xiaomeng-bot -n 20 --no-pager
```

**停止 / 启动：**

```bash
sudo systemctl stop xiaomeng-bot
sudo systemctl start xiaomeng-bot
```

**重启 NapCat（QQ 掉线或 WebSocket 连不上时）：**

```bash
cd /home/qwq/napcat_xiaomeng
docker compose restart
```

**重启 Ollama（本地模型卡死时）：**

```bash
sudo systemctl restart ollama
```

---

### 修改配置后生效

修改 `data/qq_config.json` 后需要重启 bot：

```bash
# 先检查 JSON 格式是否正确
python3 -c "import json; json.load(open('data/qq_config.json'))" && echo "格式正确"

# 再重启
sudo systemctl restart xiaomeng-bot
```

---

### 常见问题排查

#### bot 完全不响应

1. 检查 bot 进程：`systemctl status xiaomeng-bot`
2. 检查 NapCat 容器：`docker ps | grep xiao`
3. 检查 bot 和 NapCat 的连接端口是否一致：  
   配置文件 `napcat_ws_url` 应为 `ws://127.0.0.1:3002`（注意是 3002 不是 3001）

#### 只响应一半，或者回复很慢

- 云端 DeepSeek API 限速或网络问题：`journalctl -u xiaomeng-bot -f` 看有没有 API 报错
- 本地 Ollama 被撑爆：`journalctl -u ollama -f` 看有没有内存 OOM

#### 出现 `done=length`（回复被截断）

本地模型的 `num_ctx`（上下文长度）满了。解决方法：
1. 发 `/重置记忆` 清除当前会话的上下文
2. 或在 `qq_config.json` 里调大 `qwen-local` 的 `num_ctx`（会占更多显存）

#### QQ 掉线 / 扫码重登

```bash
# 打开 NapCat WebUI（需要本地访问或 SSH 端口转发）
# 浏览器打开 http://127.0.0.1:3081
```

如果是远程服务器，先在本地做 SSH 端口转发：

```bash
ssh -L 3081:127.0.0.1:3081 用户名@服务器IP
# 然后浏览器打开 http://127.0.0.1:3081
```

#### bot 崩溃循环重启

systemd 配置了 `Restart=on-failure`，崩溃后会自动重启。查崩溃原因：

```bash
journalctl -u xiaomeng-bot -n 200 --no-pager | grep -E "ERROR|Traceback|Exception"
```

---

### 查看记忆文件

每个用户的记忆存在 `data/memory/` 下，文件名是 QQ 号：

```bash
ls data/memory/
cat data/memory/user_123456.md   # 查看某人的记忆
```

手动编辑记忆文件后不需要重启 bot，下次 bot 访问该记忆时自动生效。

---

### 操作审计日志

bot 的文件读写操作会记录在 `data/audit/audit.jsonl`，每行一条 JSON：

```bash
# 查看最近操作
tail -20 data/audit/audit.jsonl | python3 -m json.tool

# 用 jq 过滤（如果装了 jq）
tail -50 data/audit/audit.jsonl | jq '{time: .timestamp, file: .file_path, by: .user_id}'
```

---

### 升级代码

```bash
cd /home/qwq/zcx_ai_group_friend
git pull
sudo systemctl restart xiaomeng-bot
journalctl -u xiaomeng-bot -f  # 确认重启成功
```
