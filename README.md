# XiaoMengCore

> 一个支持跨平台身份统一的 AI Agent 框架
> 
> 兼容 OpenClaw 人设系统 | 多模型路由 | 三层协同调度 | 自主学习

---

## ✨ 核心特性

### 🌐 跨平台身份统一（v2 核心特性）

```
用户 Alice:
├── QQ: 12345
├── 微信: wxid_alice
└── Telegram: 456789
        ↓
    统一映射到 identity:alice
        ↓
    共享同一个会话历史
```

**效果**：无论用户从 QQ、微信还是 Telegram 发消息，Agent 都能识别是同一个人，保持对话连续性。

### 🧠 Agent 自主学习

- **错误学习**：记录错误和修正方案，避免重复犯错
- **最佳实践**：积累成功经验，优化处理流程
- **功能请求**：记录用户需求，指导功能迭代

### 📚 OpenClaw 技能兼容

- 完全兼容 OpenClaw 的 SKILL.md 格式
- AI 通过阅读 Markdown 文件学习新技能
- 支持技能热加载

### 🎯 多模型智能路由

| 层级 | 用途 | 推荐模型 |
|------|------|----------|
| Basic | 快速响应、简单任务 | Qwen-7B, Llama-8B |
| Brain | 复杂推理、分析 | DeepSeek-V3, GPT-4 |
| Special | 专业任务（代码、数学） | DeepSeek-Coder |

### 🧩 可插拔多模态系统

```
┌─────────────────────────────────────────────────────────────┐
│                    ModalityPluginSystem                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ TextMod │ │VoiceMod │ │ FaceMod │ │ImageMod │  ← 插件   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
│       │           │           │           │                │
│       └───────────┴─────┬─────┴───────────┘                │
│                         ↓                                   │
│              asyncio.gather() 并行执行                      │
│                         ↓                                   │
│              FusionStrategy 融合策略                        │
└─────────────────────────────────────────────────────────────┘
```

- **可插拔**：随时添加/移除模态插件
- **并行处理**：低延迟，总延迟 = max(各模态延迟)
- **多种融合策略**：weighted / attention / voting / priority

### 📖 高级记忆系统

- **语义分析**：意图识别 + 情感分析 + 实体提取
- **知识图谱**：Graphiti 时序记忆，支持关系演化
- **混合检索**：向量 70% + BM25 30%
- **记忆衰减**：旧记忆权重自动降低

---

## 🚀 快速开始

### 方式一：一键启动（推荐新手）

1. **安装 Python 3.9+**
   - 下载：https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. **双击 `install.bat`** 安装依赖

3. **双击 `start.bat`** 选择启动方式：
   ```
   [1] 启动管理面板 - 可视化管理界面
   [2] 启动统一网关 (v1) - 基础消息入口
   [3] 启动 v2 网关 - 跨平台身份统一
   [4] 启动命令行对话 - 调试测试
   ```

### 方式二：命令行启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动管理面板
python run_panel.py

# 启动 v2 网关
python run_gateway_v2.py

# 命令行对话
python cli_chat.py
```

---

## 📁 项目结构

```
XiaoMengCore/
├── start.bat              # 一键启动器
├── install.bat            # 依赖安装
├── run_panel.py           # 管理面板入口
├── run_gateway_v2.py      # v2 网关入口
├── cli_chat.py            # 命令行对话
│
├── core/                  # 核心模块
│   ├── v2/               # v2 架构
│   │   ├── identity.py   # 跨平台身份系统
│   │   ├── gateway.py    # 统一网关
│   │   ├── queue.py      # 消息队列
│   │   ├── hooks.py      # 钩子系统
│   │   ├── session.py    # 会话存储
│   │   ├── adapters.py   # 渠道适配器
│   │   └── tools.py      # 会话工具
│   ├── processor.py      # 消息处理器
│   ├── llm_client.py     # LLM 客户端
│   ├── model_layer.py    # 三层模型路由
│   ├── skills.py         # 技能系统
│   ├── tools.py          # 工具系统
│   ├── plugins.py        # 插件系统
│   ├── self_improving.py # 自主学习
│   ├── admin_panel.py    # 管理面板
│   └── memory/           # 记忆系统
│       ├── memory_manager.py  # 记忆管理器
│       ├── semantic.py        # 语义分析
│       ├── graphiti.py        # 知识图谱
│       ├── multimodal.py      # 多模态融合
│       ├── modality_plugin.py # 模态插件系统
│       └── builtin_plugins.py # 内置模态插件
│
├── gateway/              # 网关模块
│   ├── unified.py        # v1 统一网关
│   └── paper_reader.py   # 论文阅读器 API
│
├── data/                 # 数据目录
│   ├── config.json       # 主配置文件
│   ├── identity_links.json # 身份映射配置
│   ├── persona/          # 人设文件
│   │   ├── SOUL.md       # 人格定义
│   │   ├── AGENTS.md     # 行为规范
│   │   ├── MEMORY.md     # 长期记忆
│   │   └── USER.md       # 用户信息
│   ├── skills/           # 技能文件
│   └── plugins/          # 插件目录
│
└── web/                  # 前端文件
    └── paper_reader.html # 论文阅读器
```

---

## 🏗️ 架构

### v2 统一网关架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    XiaoMengCore v2 架构                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    渠道适配器层                               │  │
│   │  QQ │ 微信 │ Telegram │ Discord │ HTTP │ WebSocket │ CLI   │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                      │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    GatewayV2 统一网关                         │  │
│   │  ┌───────────┐  ┌───────────┐  ┌───────────┐               │  │
│   │  │ Identity  │  │   Queue   │  │   Hooks   │               │  │
│   │  │ 身份系统   │  │  消息队列  │  │  钩子系统  │               │  │
│   │  └───────────┘  └───────────┘  └───────────┘               │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                      │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    会话存储层                                 │  │
│   │  sessions.json (元数据)  +  .jsonl (完整记录)                │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                              ↓                                      │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    Agent 处理器                               │  │
│   │         LLM 调用 │ 技能执行 │ 工具调用 │ 记忆检索            │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 三层模型调度

```
┌─────────────────────────────────────────────────────────────┐
│                    三层模型调度系统                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Basic 层 - 快速响应                                  │   │
│  │  • 简单问答、日常对话                                 │   │
│  │  • 延迟 < 500ms                                      │   │
│  │  • 推荐: Qwen-7B, Llama-8B                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Brain 层 - 复杂推理                                  │   │
│  │  • 论文分析、代码生成、复杂推理                       │   │
│  │  • 延迟 < 3s                                        │   │
│  │  • 推荐: DeepSeek-V3, GPT-4                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Special 层 - 专业任务                                │   │
│  │  • 代码审查、数学计算、专业分析                       │   │
│  │  • 按需调用                                          │   │
│  │  • 推荐: DeepSeek-Coder, Qwen-Math                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ 配置

### 主配置文件 (data/config.json)

```json
{
    "llm": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_key": "your_api_key",
        "base_url": "https://api.deepseek.com/v1"
    },
    "model_layers": {
        "basic": {
            "model": "qwen2.5:7b",
            "base_url": "http://localhost:11434/v1"
        },
        "brain": {
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1"
        },
        "special": {
            "model": "deepseek-coder",
            "base_url": "https://api.deepseek.com/v1"
        }
    },
    "user_groups": {
        "owner": ["your_user_id"],
        "admin": [],
        "whitelist": [],
        "blacklist": []
    }
}
```

### 身份映射配置 (data/identity_links.json)

```json
{
    "identity_links": {
        "alice": [
            "qq:12345678",
            "wechat:wxid_alice",
            "telegram:123456789"
        ],
        "bob": [
            "qq:87654321",
            "discord:987654321"
        ]
    },
    "identity_profiles": {
        "alice": {
            "display_name": "Alice Wang",
            "level": "normal",
            "group_id": "friends"
        }
    },
    "dm_scope": "per-identity"
}
```

**dm_scope 说明**：
- `per-identity`: 同一身份共享会话（跨平台统一）
- `per-platform`: 各平台独立会话

---

## 🔌 API 接口

### v2 网关 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/message` | POST | 统一消息入口 |
| `/api/identity/link` | POST | 关联平台身份 |
| `/api/identity/{id}` | GET | 获取身份信息 |
| `/api/sessions` | GET | 列出活跃会话 |
| `/api/session/{key}/history` | GET | 获取会话历史 |
| `/ws/{user_id}` | WS | WebSocket 连接 |
| `/dashboard` | GET | 管理面板 |

### 发送消息示例

```bash
curl -X POST http://localhost:8080/api/message \
  -H "Content-Type: application/json" \
  -d '{
    "content": "你好",
    "user_id": "12345",
    "platform": "qq"
  }'
```

### 关联身份示例

```bash
curl -X POST http://localhost:8080/api/identity/link \
  -H "Content-Type: application/json" \
  -d '{
    "identity_id": "alice",
    "platform": "qq",
    "platform_user_id": "12345678",
    "display_name": "Alice"
  }'
```

---

## 📚 技能系统

### 技能文件格式 (SKILL.md)

```markdown
---
name: paper-reading
description: 论文阅读和分析技能
version: 1.0.0
emoji: 📚
---

# 论文阅读技能

## 使用说明

当用户需要分析论文时，使用此技能。

## 步骤

1. 提取论文标题和摘要
2. 分析论文结构和主要贡献
3. 总结关键发现
4. 提供批判性评价

## 示例

用户请求: 帮我分析这篇论文
响应: 我来帮你分析这篇论文...
```

### 添加新技能

1. 在 `data/skills/` 下创建文件夹
2. 添加 `SKILL.md` 文件
3. 重启服务或通过管理面板热加载

---

## 🧩 插件系统

### 插件结构

```
data/plugins/
└── my_plugin/
    ├── plugin.json       # 插件元数据
    ├── main.py          # 插件主文件
    └── config.json      # 插件配置
```

### 插件元数据 (plugin.json)

```json
{
    "name": "weather",
    "version": "1.0.0",
    "description": "天气查询插件",
    "author": "developer",
    "tools": ["get_weather"],
    "hooks": ["before_agent_start"]
}
```

---

## 🔐 权限系统

| 等级 | 权限 |
|------|------|
| owner | 所有操作、系统控制、硬件控制 |
| admin | 用户管理、配置修改 |
| whitelist | 日常聊天、技能使用 |
| normal | 基础对话 |
| blacklist | 拒绝服务 |

---

## 🛠️ 开发指南

### 添加渠道适配器

```python
from core.v2 import ChannelAdapter, Platform, IncomingMessage

class MyAdapter(ChannelAdapter):
    def __init__(self, gateway):
        super().__init__(gateway, Platform.HTTP)
    
    async def receive(self, content, user_id, **kwargs):
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id
        )
        return await self._gateway.receive(message)
```

### 添加钩子

```python
from core.v2 import HookPoint, HookContext

async def my_hook(context: HookContext):
    print(f"钩子触发: {context.hook_point}")
    return context

gateway.register_hook("my_hook", HookPoint.BEFORE_AGENT_START, my_hook)
```

### 添加工具

```python
from core.v2 import SessionTools

async def my_tool(session_key: str, message: str):
    return {"success": True, "result": "处理完成"}

session_tools = SessionTools(gateway)
```

---

## 🧠 记忆系统

XiaoMengCore 支持多层记忆系统，完全兼容 OpenClaw 人设格式：

### 记忆类型

| 类型 | 存储 | 用途 |
|------|------|------|
| 人设记忆 | `data/persona/*.md` | 人格、行为规范、身份信息 |
| 短期记忆 | 会话上下文 | 当前对话 |
| 长期记忆 | `data/memory/YYYY-MM-DD.md` | 每日记忆日记 |
| 向量记忆 | ChromaDB | RAG 语义检索 |
| 图谱记忆 | Neo4j | 时序知识图谱 |

### 人设文件

```
data/persona/
├── SOUL.md      # 人格定义（性格、说话风格）
├── AGENTS.md    # 行为规范（如何与不同用户交互）
├── IDENTITY.md  # 身份信息（名字、背景、能力）
├── USER.md      # 用户信息（主人的信息）
├── TOOLS.md     # 工具说明（可用工具）
├── MEMORY.md    # 长期记忆（重要事实）
└── HEARTBEAT.md # 心跳任务（定时行为）
```

### 使用记忆系统

```python
from core.memory import MemoryManager

memory = MemoryManager.get_instance()

# 添加记忆
memory.add_memory(user, "主人今天心情很好", tags=["mood"])

# 搜索记忆
results = memory.search_memories(user, "心情", limit=5)

# 获取 LLM 上下文
context = memory.get_context_for_llm(user, current_message)
```

---

## 🗜️ 会话压缩

当会话上下文过长时，自动压缩历史对话：

### 压缩机制

```
原始对话 (8000 tokens)
    ↓
[摘要] 之前讨论了项目架构...
    ↓
压缩后 (2000 tokens)
```

### 配置压缩

```python
from core.v2 import Compactor, CompactionConfig, AutoCompactor

config = CompactionConfig(
    max_tokens=4000,      # 触发压缩的阈值
    target_tokens=2000,   # 压缩目标
    keep_recent_messages=5  # 保留最近消息数
)

compactor = Compactor(llm_client=llm, config=config)

# 手动压缩
result = await compactor.compact(entries)
print(f"压缩: {result.original_tokens} -> {result.compressed_tokens} tokens")

# 自动压缩
auto_compactor = AutoCompactor(session_store, compactor, config)
result = await auto_compactor.check_and_compact(session_key)
```

### 压缩钩子

```python
from core.v2 import HookPoint, HookContext

async def before_compaction_hook(ctx: HookContext):
    print(f"即将压缩会话: {ctx.session_key}")
    return ctx

gateway.register_hook("compaction", HookPoint.BEFORE_COMPACTION, before_compaction_hook)
```

---

## 📦 依赖

```
Python >= 3.9
openai >= 1.0.0
fastapi >= 0.100.0
uvicorn >= 0.23.0
pyyaml >= 6.0
aiohttp >= 3.8.0
chromadb >= 0.4.0 (可选)
```

---

## 📄 许可证

MIT License

---

## 🙏 致谢

- [OpenClaw](https://github.com/openclaw/openclaw) - 人设文件格式和技能系统参考
- [PyGPT](https://github.com/szczyglis-dev/py-gpt) - 桌面助手架构参考
- [GLM-5 / Trae AI Assistant](https://www.trae.ai) - 核心架构设计、代码实现、文档撰写
