"""
Calendar Maker 工具定义
遵循 XiaoMeng 的 TOOL_SCHEMAS 格式（OpenAI function-calling）
"""

from typing import Any, Dict

CALENDAR_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calendar_bind",
            "description": (
                "将当前QQ号绑定到calendar账号。绑定后，该QQ号可以直接使用日历功能，"
                "无需每次登录。绑定关系长期有效，直到主动解除或会话过期。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "calendar_backend 的用户名"
                    },
                    "password": {
                        "type": "string",
                        "description": "calendar_backend 的密码"
                    },
                    "account_name": {
                        "type": "string",
                        "description": "可选的本地别名，方便记忆"
                    }
                },
                "required": ["username", "password"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_unbind",
            "description": "解除当前QQ号与calendar账号的绑定关系。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_binding_status",
            "description": "查询当前QQ号的绑定状态。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_switch_binding",
            "description": "切换当前QQ号绑定的calendar账号。需要验证新账号的密码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "新的 calendar_backend 用户名"
                    },
                    "password": {
                        "type": "string",
                        "description": "新账号的密码"
                    },
                    "account_name": {
                        "type": "string",
                        "description": "可选的本地别名"
                    }
                },
                "required": ["username", "password"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_add_event",
            "description": (
                "添加日程到日历系统。可以添加会议、约会、提醒等日程安排。"
                "如果QQ号已绑定账号，可直接使用；否则需要先登录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "日程标题，如「项目会议」、「牙医预约」"
                    },
                    "date": {
                        "type": "string",
                        "description": "日期，格式 YYYY-MM-DD 或「明天」、「下周一」等自然语言"
                    },
                    "time": {
                        "type": "string",
                        "description": "时间，如「14:00」或「下午2点」"
                    },
                    "location": {
                        "type": "string",
                        "description": "地点，如「会议室A」、「市中心医院」"
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注信息"
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_add_todo",
            "description": (
                "添加待办事项到日历系统。可以添加任务、作业、购物清单等。"
                "如果QQ号已绑定账号，可直接使用；否则需要先登录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "待办事项标题"
                    },
                    "deadline": {
                        "type": "string",
                        "description": "截止日期，格式 YYYY-MM-DD"
                    },
                    "priority": {
                        "type": "string",
                        "description": "优先级：high(高)、medium(中)、low(低)",
                        "enum": ["high", "medium", "low"]
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注信息"
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_add_from_text",
            "description": (
                "从自然语言文本中提取并添加日程/待办。"
                "适合用户用口语描述多个安排的情况，如「明天下午3点开会，周五前交报告」。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "包含日程/待办信息的自然语言文本"
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "查看当前账号的所有日程安排。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_todos",
            "description": "查看当前账号的所有待办事项。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_login",
            "description": (
                "登录日历账号（不绑定QQ号）。使用 calendar_backend 系统的用户名和密码。"
                "如果需要长期免登录，请使用 calendar_bind 绑定账号。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "calendar_backend 的用户名（或本地保存的账号别名）"
                    },
                    "password": {
                        "type": "string",
                        "description": "calendar_backend 的密码"
                    },
                    "account_name": {
                        "type": "string",
                        "description": "可选的本地别名，方便以后快速登录"
                    }
                },
                "required": ["username", "password"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_logout",
            "description": "登出当前日历账号。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_accounts",
            "description": "列出所有已保存的日历账号别名。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_register",
            "description": "在 calendar_backend 注册新的日历账号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_name": {
                        "type": "string",
                        "description": "本地账号别名（方便记忆）"
                    },
                    "username": {
                        "type": "string",
                        "description": "calendar_backend 的用户名"
                    },
                    "password": {
                        "type": "string",
                        "description": "calendar_backend 的密码（至少6位）"
                    }
                },
                "required": ["account_name", "username", "password"]
            }
        }
    },
]

CALENDAR_TOOL_PROGRESS_MSG = {
    "calendar_bind": lambda args: f"正在绑定账号「{args.get('username', '')}」...",
    "calendar_unbind": lambda args: "正在解除绑定...",
    "calendar_binding_status": lambda args: "正在查询绑定状态...",
    "calendar_switch_binding": lambda args: f"正在切换到账号「{args.get('username', '')}」...",
    "calendar_add_event": lambda args: f"正在添加日程「{args.get('title', '')}」...",
    "calendar_add_todo": lambda args: f"正在添加待办「{args.get('title', '')}」...",
    "calendar_add_from_text": lambda args: "正在解析并添加日程...",
    "calendar_login": lambda args: f"正在登录账号「{args.get('username', '')}」...",
    "calendar_register": lambda args: f"正在注册账号「{args.get('account_name', '')}」...",
}


class CalendarToolExecutor:
    """
    日历工具执行器
    遵循 XiaoMeng 的 QQToolExecutor 接口规范
    """

    def __init__(self, account_manager):
        self._account_manager = account_manager
        self._current_qq: int = 0

    def set_context(self, qq: int) -> None:
        """设置当前操作的QQ号上下文"""
        self._current_qq = qq

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        if tool_name == "calendar_bind":
            return await self._bind(arguments)
        elif tool_name == "calendar_unbind":
            return await self._unbind()
        elif tool_name == "calendar_binding_status":
            return await self._binding_status()
        elif tool_name == "calendar_switch_binding":
            return await self._switch_binding(arguments)
        elif tool_name == "calendar_add_event":
            return await self._add_event(arguments)
        elif tool_name == "calendar_add_todo":
            return await self._add_todo(arguments)
        elif tool_name == "calendar_add_from_text":
            return await self._add_from_text(arguments)
        elif tool_name == "calendar_list_events":
            return await self._list_events()
        elif tool_name == "calendar_list_todos":
            return await self._list_todos()
        elif tool_name == "calendar_login":
            return await self._login(arguments)
        elif tool_name == "calendar_logout":
            return await self._logout()
        elif tool_name == "calendar_list_accounts":
            return await self._list_accounts()
        elif tool_name == "calendar_register":
            return await self._register(arguments)
        else:
            return f"未知工具: {tool_name}"

    async def _bind(self, args: dict) -> str:
        username = args.get("username", "")
        password = args.get("password", "")
        if not username or not password:
            return "用户名和密码不能为空"

        success, msg = await self._account_manager.bind_qq(
            qq=self._current_qq,
            username=username,
            password=password,
            account_name=args.get("account_name"),
        )
        if success:
            return f"✅ {msg}\n绑定后可直接使用日历功能，无需每次登录。"
        return f"❌ {msg}"

    async def _unbind(self) -> str:
        success, msg = self._account_manager.unbind_qq(self._current_qq)
        if success:
            return f"✅ {msg}"
        return f"❌ {msg}"

    async def _binding_status(self) -> str:
        status = self._account_manager.get_qq_binding_status(self._current_qq)
        if not status.get("is_bound"):
            return f"📋 绑定状态：{status.get('message', '未绑定')}"
        
        lines = [
            "📋 绑定状态：已绑定",
            f"  账号：{status.get('calendar_username', '')}",
            f"  别名：{status.get('account_name', '')}",
            f"  绑定时间：{status.get('bound_at', '')[:10]}",
            f"  过期时间：{status.get('expires_at', '')[:10]}",
        ]
        return "\n".join(lines)

    async def _switch_binding(self, args: dict) -> str:
        username = args.get("username", "")
        password = args.get("password", "")
        if not username or not password:
            return "用户名和密码不能为空"

        success, msg = await self._account_manager.switch_qq_binding(
            qq=self._current_qq,
            username=username,
            password=password,
            account_name=args.get("account_name"),
        )
        if success:
            return f"✅ {msg}"
        return f"❌ {msg}"

    async def _add_event(self, args: dict) -> str:
        title = args.get("title", "")
        if not title:
            return "日程标题不能为空"

        success, msg, result = await self._account_manager.add_event(
            title=title,
            qq=self._current_qq,
            date=args.get("date"),
            time=args.get("time"),
            location=args.get("location"),
            notes=args.get("notes"),
        )
        if success:
            return f"✅ {msg}"
        return f"❌ {msg}"

    async def _add_todo(self, args: dict) -> str:
        title = args.get("title", "")
        if not title:
            return "待办标题不能为空"

        success, msg, result = await self._account_manager.add_todo(
            title=title,
            qq=self._current_qq,
            deadline=args.get("deadline"),
            priority=args.get("priority", "medium"),
            notes=args.get("notes"),
        )
        if success:
            return f"✅ {msg}"
        return f"❌ {msg}"

    async def _add_from_text(self, args: dict) -> str:
        text = args.get("text", "")
        if not text:
            return "文本内容不能为空"

        success, msg, result = await self._account_manager.add_from_text(
            text=text,
            qq=self._current_qq,
        )
        if success:
            return f"✅ {msg}"
        return f"❌ {msg}"

    async def _list_events(self) -> str:
        events = await self._account_manager.get_events(qq=self._current_qq)
        if not events:
            return "📅 当前没有日程安排"

        lines = [f"📅 日程列表（共 {len(events)} 个）："]
        for i, e in enumerate(events[:10], 1):
            date = e.get("date", "")
            time = e.get("time", "")
            title = e.get("title", "")
            location = e.get("location", "")
            line = f"  {i}. {date} {time} {title}"
            if location:
                line += f"（{location}）"
            lines.append(line)
        if len(events) > 10:
            lines.append(f"  ... 还有 {len(events) - 10} 个")
        return "\n".join(lines)

    async def _list_todos(self) -> str:
        todos = await self._account_manager.get_todos(qq=self._current_qq)
        if not todos:
            return "📋 当前没有待办事项"

        lines = [f"📋 待办列表（共 {len(todos)} 个）："]
        for i, t in enumerate(todos[:10], 1):
            title = t.get("title", "")
            deadline = t.get("deadline", "")
            priority = t.get("priority", "medium")
            done = t.get("is_done", False)
            status = "✓" if done else "○"
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "🟡")
            line = f"  {i}. {status} {priority_icon} {title}"
            if deadline:
                line += f"（截止：{deadline}）"
            lines.append(line)
        if len(todos) > 10:
            lines.append(f"  ... 还有 {len(todos) - 10} 个")
        return "\n".join(lines)

    async def _login(self, args: dict) -> str:
        username = args.get("username", "")
        password = args.get("password", "")
        if not username or not password:
            return "用户名和密码不能为空"

        success, msg = await self._account_manager.login_account(
            username=username,
            password=password,
            account_name=args.get("account_name"),
        )
        if success:
            return f"✅ {msg}\n提示：使用 /日历 绑定 可以长期免登录。"
        return f"❌ {msg}"

    async def _logout(self) -> str:
        success, msg = self._account_manager.logout()
        if success:
            return f"✅ {msg}"
        return f"❌ {msg}"

    async def _list_accounts(self) -> str:
        accounts = self._account_manager.list_accounts()
        if not accounts:
            return "📋 没有保存的账号别名"

        lines = ["📋 已保存的账号别名："]
        for acc in accounts:
            current = "（当前）" if acc["is_current"] else ""
            last_used = acc.get("last_used", "")
            if last_used:
                last_used = f" - 最后使用: {last_used[:10]}"
            lines.append(f"  • {acc['name']}（用户名: {acc['username']}）{current}{last_used}")
        return "\n".join(lines)

    async def _register(self, args: dict) -> str:
        account_name = args.get("account_name", "")
        username = args.get("username", "")
        password = args.get("password", "")

        if not account_name or not username or not password:
            return "账号别名、用户名和密码不能为空"
        if len(password) < 6:
            return "密码至少需要6位"

        success, msg = await self._account_manager.register_account(
            account_name, username, password
        )
        if success:
            return f"✅ {msg}"
        return f"❌ {msg}"
