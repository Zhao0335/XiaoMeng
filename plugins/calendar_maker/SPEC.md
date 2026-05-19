# Calendar Maker Plugin 技术规范文档

## 1. 插件规范合规性检查

### 1.1 OpenAI Function Calling 规范

**合规状态：✅ 完全合规**

当前实现完全遵循 OpenAI Function Calling 规范：

```python
# 工具定义格式（完全符合 OpenAI 规范）
{
    "type": "function",
    "function": {
        "name": "calendar_add_event",           # 工具名称
        "description": "添加日程到日历系统...",  # 工具描述
        "parameters": {                          # JSON Schema 参数定义
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "日程标题"
                },
                # ...
            },
            "required": ["title"]
        }
    }
}
```

**规范对照表：**

| 规范要求 | 当前实现 | 状态 |
|---------|---------|------|
| 工具定义使用 `type: "function"` | ✅ 已实现 | 合规 |
| 参数使用 JSON Schema | ✅ 已实现 | 合规 |
| 支持 `required` 字段 | ✅ 已实现 | 合规 |
| 支持 `enum` 约束 | ✅ 已实现（priority字段） | 合规 |
| 异步执行接口 | ✅ `async def execute()` | 合规 |
| 返回字符串结果 | ✅ 返回 `str` | 合规 |

### 1.2 LangChain Tool 规范

**合规状态：✅ 可适配**

当前实现可通过适配器转换为 LangChain Tool：

```python
# LangChain 适配示例
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

class CalendarAddEventInput(BaseModel):
    title: str = Field(description="日程标题")
    date: str = Field(default=None, description="日期")
    time: str = Field(default=None, description="时间")

class CalendarAddEventTool(BaseTool):
    name = "calendar_add_event"
    description = "添加日程到日历系统"
    args_schema = CalendarAddEventInput
    
    async def _arun(self, title: str, date: str = None, time: str = None):
        # 调用 CalendarToolExecutor
        return await executor.execute("calendar_add_event", {
            "title": title, "date": date, "time": time
        })
```

### 1.3 XiaoMeng 插件规范

**合规状态：✅ 完全合规**

| 接口要求 | 当前实现 | 状态 |
|---------|---------|------|
| `get_tool_schemas()` | ✅ 返回工具定义列表 | 合规 |
| `get_tool_executor()` | ✅ 返回执行器 | 合规 |
| `get_command_parser()` | ✅ 返回命令解析器 | 合规 |
| `initialize()` / `start()` / `stop()` | ✅ 生命周期管理 | 合规 |
| `handle_tool_call()` | ✅ 工具调用入口 | 合规 |
| `handle_command()` | ✅ 命令处理入口 | 合规 |

---

## 2. Agent 兼容性验证

### 2.1 第三方 Agent 接入流程

**支持状态：✅ 完全支持**

第三方 Agent 可通过以下方式接入：

#### 方式一：直接调用（推荐）

```python
from plugins.calendar_maker import CalendarMakerPlugin

# 1. 创建插件实例
plugin = CalendarMakerPlugin()
await plugin.initialize()

# 2. 获取工具定义（用于 LLM function calling）
tools = plugin.get_tool_schemas()

# 3. 执行工具调用
result = await plugin.handle_tool_call(
    tool_name="calendar_add_event",
    arguments={"title": "会议", "date": "2024-01-15", "time": "14:00"}
)

# 4. 获取插件状态
status = plugin.get_status()
```

#### 方式二：使用工具执行器

```python
from plugins.calendar_maker import CalendarToolExecutor, AccountManager

# 1. 创建账号管理器
account_manager = AccountManager(config, data_dir)

# 2. 创建执行器
executor = CalendarToolExecutor(account_manager)

# 3. 执行工具
result = await executor.execute("calendar_add_event", {
    "title": "会议",
    "date": "2024-01-15"
})
```

#### 方式三：LangChain 集成

```python
from langchain.agents import AgentExecutor
from plugins.calendar_maker.adapters import get_langchain_tools

# 获取 LangChain 兼容的工具列表
tools = get_langchain_tools(plugin)

# 创建 Agent
agent = AgentExecutor.from_agent_and_tools(
    agent=some_agent,
    tools=tools
)
```

### 2.2 权限控制

**支持状态：✅ 支持**

| 权限级别 | 说明 | 实现方式 |
|---------|------|---------|
| 插件级 | 启用/禁用插件 | `config.enabled` |
| 账号级 | 登录验证 | `calendar_login` 工具 |
| 操作级 | 需登录才能操作 | 执行前检查 `is_logged_in` |

### 2.3 调用方式

```python
# 同步调用（阻塞）
result = await plugin.handle_tool_call("calendar_list_events", {})

# 异步调用（非阻塞）
import asyncio
task = asyncio.create_task(plugin.handle_tool_call("calendar_add_event", args))

# 批量调用
results = await asyncio.gather(*[
    plugin.handle_tool_call("calendar_add_event", event)
    for event in events
])
```

---

## 3. 账号绑定机制

### 3.1 设计概述

**QQ号与calendar账号绑定关系：**

```
QQ号 (sender_qq) <--绑定--> calendar账号 (username)
```

### 3.2 绑定状态生命周期

```
┌─────────────────────────────────────────────────────────────┐
│                    绑定状态生命周期                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [未绑定]                                                   │
│      │                                                      │
│      ├── 用户登录成功 ──→ [已绑定]                          │
│      │                         │                            │
│      │                         ├── 会话有效期内可操作        │
│      │                         │                            │
│      │                         ├── 会话过期 ──→ [需重新登录] │
│      │                         │                            │
│      │                         └── 用户主动解绑 ──→ [未绑定] │
│      │                                                      │
│      └── 用户主动解绑 ──→ [未绑定]                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 绑定关系存储

```json
{
  "bindings": {
    "123456789": {
      "calendar_username": "user1",
      "account_name": "我的账号",
      "session_id": "sess_xxx",
      "bound_at": "2024-01-15T10:00:00Z",
      "expires_at": "2024-02-14T10:00:00Z",
      "last_active": "2024-01-15T15:30:00Z"
    }
  }
}
```

### 3.4 绑定状态管理接口

| 接口 | 说明 | 参数 |
|------|------|------|
| `bind_account(qq, username, password)` | 绑定账号 | qq, username, password |
| `unbind_account(qq)` | 解除绑定 | qq |
| `get_binding(qq)` | 查询绑定状态 | qq |
| `is_bound(qq)` | 检查是否已绑定 | qq |
| `refresh_binding(qq)` | 刷新绑定状态 | qq |
| `list_bindings()` | 列出所有绑定 | - |

### 3.5 绑定规则

1. **一对一绑定**：一个QQ号只能绑定一个calendar账号
2. **长期有效**：绑定关系长期有效，直到用户主动解除或会话过期
3. **会话刷新**：每次操作自动刷新会话有效期
4. **安全验证**：绑定和解绑都需要密码验证

---

## 4. 接口规范

### 4.1 工具接口

| 工具名称 | 功能 | 认证要求 |
|---------|------|---------|
| `calendar_bind` | 绑定QQ号到calendar账号 | 需密码 |
| `calendar_unbind` | 解除绑定 | 需已绑定 |
| `calendar_binding_status` | 查询绑定状态 | 无 |
| `calendar_login` | 登录（兼容旧接口） | 需密码 |
| `calendar_add_event` | 添加日程 | 需已绑定 |
| `calendar_add_todo` | 添加待办 | 需已绑定 |
| `calendar_list_events` | 查看日程 | 需已绑定 |
| `calendar_list_todos` | 查看待办 | 需已绑定 |

### 4.2 命令接口

```
/日历 绑定 {用户名} {密码}      # 绑定QQ号到calendar账号
/日历 解绑                     # 解除当前QQ号的绑定
/日历 绑定状态                 # 查看绑定状态
/日历 切换账号 {用户名} {密码}  # 切换到其他账号
```

### 4.3 响应格式

```python
# 成功响应
{
    "success": True,
    "message": "操作成功",
    "data": {...}
}

# 失败响应
{
    "success": False,
    "message": "错误原因",
    "error_code": "ERROR_CODE"
}
```

---

## 5. 安全规范

### 5.1 密码处理

- ❌ 不在本地存储密码
- ✅ 每次操作直接向 calendar_backend 验证
- ✅ 密码通过 HTTPS 传输

### 5.2 会话管理

- ✅ 会话有有效期限制（默认30天）
- ✅ 会话过期需重新验证密码
- ✅ 每次操作自动刷新会话

### 5.3 绑定安全

- ✅ 绑定需要密码验证
- ✅ 解绑需要用户主动操作
- ✅ 绑定关系加密存储

---

## 6. 兼容性矩阵

| Agent 框架 | 兼容性 | 接入方式 |
|-----------|--------|---------|
| OpenAI GPT | ✅ 原生支持 | Function Calling |
| LangChain | ✅ 适配器支持 | `get_langchain_tools()` |
| AutoGPT | ✅ 可适配 | Tool 接口 |
| BabyAGI | ✅ 可适配 | Tool 接口 |
| XiaoMeng | ✅ 原生支持 | Plugin 接口 |
| 自定义 Agent | ✅ 支持 | 直接调用 |
