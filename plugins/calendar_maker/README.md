# Calendar Maker Plugin

日历管理插件 - 支持通过 QQ 管理 calendar_backend 系统的日程安排。

## 重要说明

**本插件直接使用 calendar_backend 系统的账号密码：**

- 用户名和密码是 calendar_backend 系统的账号，不是本地创建的
- 本地不保存密码，只保存账号别名和用户名的映射
- 每次登录/切换都需要输入密码，直接向 calendar_backend 验证
- 登录成功后保存 session_id 用于后续操作

## 目录结构

```
plugins/calendar_maker/
├── __init__.py           # 插件入口
├── plugin.py             # 插件主类
├── config.py             # 配置管理
├── auth.py               # 身份验证（本地会话管理）
├── calendar_client.py    # 日历后端API客户端
├── account_manager.py    # 账号管理
├── tools.py              # 工具定义（遵循XiaoMeng TOOL_SCHEMAS格式）
├── commands.py           # QQ命令处理
├── SKILL.md              # 技能文档
├── config.example.json   # 配置示例
├── README.md             # 本文档
└── tests/                # 单元测试
    ├── __init__.py
    ├── test_auth.py
    ├── test_calendar_client.py
    └── test_account_manager.py
```

## 安装

1. 将插件放置在 XiaoMeng 项目的 `plugins/calendar_maker/` 目录下

2. 安装依赖：
```bash
pip install httpx bcrypt pytest pytest-asyncio
```

3. 复制配置文件：
```bash
cp config.example.json config.json
```

4. 根据需要修改 `config.json`

## 配置说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | true | 是否启用插件 |
| `backend.url` | string | http://127.0.0.1:5522 | calendar_backend 服务地址 |
| `backend.timeout` | float | 30.0 | 请求超时时间（秒） |
| `backend.retry_count` | int | 3 | 请求重试次数 |
| `backend.retry_delay` | float | 1.0 | 重试间隔（秒） |

## 使用方法

### QQ 命令

```
# 登录 calendar_backend 已有的账号
/日历 登录 {用户名} {密码}
/日历 登录 {用户名} {密码} {别名}   # 登录并保存别名

# 切换账号（需要重新输入密码）
/日历 切换 {用户名} {密码}

# 注册新账号（在 calendar_backend 注册）
/日历 注册 {别名} {用户名} {密码}

# 其他命令
/日历 登出
/日历 账号列表
/日历 添加日程 {标题} [日期] [时间] [地点]
/日历 添加待办 {标题} [截止日期] [优先级]
/日历 查看日程
/日历 查看待办
/日历 帮助
```

### 示例

```
用户: /日历 登录 myuser mypassword123
小萌: ✅ 账号 myuser（用户名: myuser）登录成功

用户: /日历 登录 myuser mypassword123 我的账号
小萌: ✅ 账号 我的账号（用户名: myuser）登录成功

用户: 明天下午2点有个项目会议
小萌: ✅ 日程「项目会议」添加成功

用户: /日历 查看日程
小萌: 
📅 日程列表（共 1 个）：
  1. 2024-01-16 14:00 项目会议
```

## 接口文档

### 插件主类 (CalendarMakerPlugin)

```python
from plugins.calendar_maker import CalendarMakerPlugin

plugin = CalendarMakerPlugin(
    config_path=Path("config.json"),
    data_dir=Path("data")
)

await plugin.initialize()
await plugin.start()

# 处理工具调用
result = await plugin.handle_tool_call("calendar_add_event", {
    "title": "会议",
    "date": "2024-01-15",
    "time": "14:00"
})

# 处理命令
reply = await plugin.handle_command("/日历 查看日程", sender_qq, session_key)

await plugin.stop()
```

### 账号管理器 (AccountManager)

```python
from plugins.calendar_maker.account_manager import AccountManager

manager = AccountManager(config, data_dir)

# 登录 calendar_backend 已有的账号
success, msg = await manager.login_account(
    username="calendar_user",  # calendar_backend 的用户名
    password="password",       # calendar_backend 的密码
    account_name="我的账号",   # 可选的本地别名
)

# 切换账号（需要密码）
success, msg = await manager.switch_account(
    username="another_user",
    password="password",
)

# 注册新账号（在 calendar_backend 注册）
success, msg = await manager.register_account(
    account_name="新账号",     # 本地别名
    username="new_user",       # calendar_backend 用户名
    password="password",       # calendar_backend 密码
)

# 添加日程
success, msg, result = await manager.add_event(
    title="会议",
    date="2024-01-15",
    time="14:00",
    location="会议室A"
)
```

### 日历客户端 (CalendarClient)

```python
from plugins.calendar_maker.calendar_client import CalendarClient, Event, Todo

client = CalendarClient(base_url="http://127.0.0.1:5522")

# 登录 calendar_backend
success, msg = await client.login("username", "password")

# 添加日程
event = Event(title="会议", date="2024-01-15", time="14:00")
result = await client.add_event(event)

# 从文本添加
result = await client.add_from_text("明天下午开会")

# 获取日程
events = await client.get_events()
```

## 工具定义

| 工具名称 | 描述 | 参数 |
|----------|------|------|
| `calendar_login` | 登录账号 | username, password, account_name(可选) |
| `calendar_switch_account` | 切换账号 | username, password |
| `calendar_register` | 注册账号 | account_name, username, password |
| `calendar_logout` | 登出 | - |
| `calendar_list_accounts` | 账号列表 | - |
| `calendar_add_event` | 添加日程 | title, date, time, location, notes |
| `calendar_add_todo` | 添加待办 | title, deadline, priority, notes |
| `calendar_add_from_text` | 从文本添加 | text |
| `calendar_list_events` | 查看日程 | - |
| `calendar_list_todos` | 查看待办 | - |

## 安全说明

1. **不保存密码**：本地只保存账号别名和用户名的映射，不保存密码

2. **直接验证**：每次登录/切换都直接向 calendar_backend 验证密码

3. **会话管理**：登录成功后保存 session_id，用于后续操作

4. **传输安全**：建议在生产环境使用 HTTPS

## 测试

```bash
cd /home/qwq/zcx_ai_group_friend/XiaoMeng
pytest plugins/calendar_maker/tests/ -v
```

## 版本历史

- v1.0.0 (2024-01-15)
  - 初始版本
  - 直接使用 calendar_backend 的账号密码系统
  - 支持日程和待办管理
  - 支持多账号切换

## 许可证

MIT License
