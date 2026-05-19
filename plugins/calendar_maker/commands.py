"""
Calendar Maker 命令解析器
处理 QQ 渠道的日历管理命令
"""

import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from account_manager import AccountManager

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    success: bool
    reply: str
    action: Optional[str] = None


class CalendarCommandParser:
    """
    解析并执行日历管理命令。
    
    命令格式：
    /日历 绑定 {用户名} {密码} [别名]   - 绑定QQ号到calendar账号
    /日历 解绑                        - 解除当前QQ号的绑定
    /日历 绑定状态                    - 查看绑定状态
    /日历 切换账号 {用户名} {密码}     - 切换到其他账号
    /日历 登录 {用户名} {密码} [别名]  - 登录（不绑定）
    /日历 登出                        - 登出
    /日历 账号列表                    - 查看已保存账号
    /日历 注册 {别名} {用户名} {密码}  - 注册新账号
    /日历 添加日程 {标题} [日期] [时间] [地点]
    /日历 添加待办 {标题} [截止日期] [优先级]
    /日历 查看日程                    - 查看所有日程
    /日历 查看待办                    - 查看所有待办
    
    注意：用户名和密码是 calendar_backend 系统的账号密码
    """

    COMMANDS = {
        "/日历 绑定": ("bind", "用法: /日历 绑定 {用户名} {密码} [别名]"),
        "/日历 解绑": ("unbind", ""),
        "/日历 绑定状态": ("binding_status", ""),
        "/日历 切换账号": ("switch_binding", "用法: /日历 切换账号 {用户名} {密码}"),
        "/日历 登录": ("login", "用法: /日历 登录 {用户名} {密码} [别名]"),
        "/日历 登出": ("logout", ""),
        "/日历 账号列表": ("list_accounts", ""),
        "/日历 注册": ("register", "用法: /日历 注册 {别名} {用户名} {密码}"),
        "/日历 添加日程": ("add_event", "用法: /日历 添加日程 {标题} [日期] [时间] [地点]"),
        "/日历 添加待办": ("add_todo", "用法: /日历 添加待办 {标题} [截止日期] [优先级]"),
        "/日历 查看日程": ("list_events", ""),
        "/日历 查看待办": ("list_todos", ""),
        "/日历 帮助": ("help", ""),
    }

    def __init__(self, account_manager: "AccountManager"):
        self._account_manager = account_manager

    async def handle(
        self,
        text: str,
        sender_qq: int,
        session_key: str,
    ) -> Optional[CommandResult]:
        text = text.strip()

        matched_cmd = None
        matched_args = ""
        for cmd in sorted(self.COMMANDS.keys(), key=len, reverse=True):
            if text == cmd or text.startswith(cmd + " "):
                matched_cmd = cmd
                matched_args = text[len(cmd):].strip()
                break

        if not matched_cmd:
            return None

        action, usage = self.COMMANDS[matched_cmd]
        return await self._dispatch(action, matched_args, sender_qq, session_key, usage)

    async def _dispatch(
        self,
        action: str,
        args: str,
        sender_qq: int,
        session_key: str,
        usage: str,
    ) -> CommandResult:
        if action == "bind":
            return await self._bind(args, sender_qq)
        elif action == "unbind":
            return await self._unbind(sender_qq)
        elif action == "binding_status":
            return await self._binding_status(sender_qq)
        elif action == "switch_binding":
            return await self._switch_binding(args, sender_qq)
        elif action == "login":
            return await self._login(args)
        elif action == "logout":
            return await self._logout()
        elif action == "list_accounts":
            return await self._list_accounts()
        elif action == "register":
            return await self._register(args)
        elif action == "add_event":
            return await self._add_event(args, sender_qq)
        elif action == "add_todo":
            return await self._add_todo(args, sender_qq)
        elif action == "list_events":
            return await self._list_events(sender_qq)
        elif action == "list_todos":
            return await self._list_todos(sender_qq)
        elif action == "help":
            return self._help()
        return CommandResult(False, "未知操作")

    async def _bind(self, args: str, qq: int) -> CommandResult:
        parts = args.split(maxsplit=2)
        if len(parts) < 2:
            return CommandResult(False, "请提供用户名和密码\n用法: /日历 绑定 {用户名} {密码} [别名]")

        username, password = parts[0], parts[1]
        account_name = parts[2] if len(parts) > 2 else None
        
        success, msg = await self._account_manager.bind_qq(
            qq=qq,
            username=username,
            password=password,
            account_name=account_name,
        )

        if success:
            return CommandResult(
                True, 
                f"✅ {msg}\n绑定后可直接使用日历功能，无需每次登录。", 
                action="calendar_bind"
            )
        return CommandResult(False, f"❌ {msg}")

    async def _unbind(self, qq: int) -> CommandResult:
        success, msg = self._account_manager.unbind_qq(qq)
        if success:
            return CommandResult(True, f"✅ {msg}", action="calendar_unbind")
        return CommandResult(False, f"❌ {msg}")

    async def _binding_status(self, qq: int) -> CommandResult:
        status = self._account_manager.get_qq_binding_status(qq)
        if not status.get("is_bound"):
            return CommandResult(True, f"📋 绑定状态：{status.get('message', '未绑定')}")
        
        lines = [
            "📋 绑定状态：已绑定",
            f"  账号：{status.get('calendar_username', '')}",
            f"  别名：{status.get('account_name', '')}",
            f"  绑定时间：{status.get('bound_at', '')[:10]}",
            f"  过期时间：{status.get('expires_at', '')[:10]}",
        ]
        return CommandResult(True, "\n".join(lines))

    async def _switch_binding(self, args: str, qq: int) -> CommandResult:
        parts = args.split(maxsplit=2)
        if len(parts) < 2:
            return CommandResult(False, "请提供用户名和密码\n用法: /日历 切换账号 {用户名} {密码}")

        username, password = parts[0], parts[1]
        account_name = parts[2] if len(parts) > 2 else None
        
        success, msg = await self._account_manager.switch_qq_binding(
            qq=qq,
            username=username,
            password=password,
            account_name=account_name,
        )

        if success:
            return CommandResult(True, f"✅ {msg}", action="calendar_switch_binding")
        return CommandResult(False, f"❌ {msg}")

    async def _login(self, args: str) -> CommandResult:
        parts = args.split(maxsplit=2)
        if len(parts) < 2:
            return CommandResult(False, "请提供用户名和密码\n用法: /日历 登录 {用户名} {密码} [别名]")

        username, password = parts[0], parts[1]
        account_name = parts[2] if len(parts) > 2 else None
        
        success, msg = await self._account_manager.login_account(
            username=username,
            password=password,
            account_name=account_name,
        )

        if success:
            return CommandResult(
                True, 
                f"✅ {msg}\n提示：使用 /日历 绑定 可以长期免登录。", 
                action="calendar_login"
            )
        return CommandResult(False, f"❌ {msg}")

    async def _logout(self) -> CommandResult:
        success, msg = self._account_manager.logout()
        if success:
            return CommandResult(True, f"✅ {msg}", action="calendar_logout")
        return CommandResult(False, f"❌ {msg}")

    async def _list_accounts(self) -> CommandResult:
        accounts = self._account_manager.list_accounts()
        if not accounts:
            return CommandResult(True, "📋 没有保存的账号别名\n提示：使用 /日历 登录 {用户名} {密码} {别名} 可以保存别名")

        lines = ["📋 已保存的账号别名："]
        for acc in accounts:
            current = "（当前登录）" if acc["is_current"] else ""
            lines.append(f"  • {acc['name']}（用户名: {acc['username']}）{current}")
        return CommandResult(True, "\n".join(lines))

    async def _register(self, args: str) -> CommandResult:
        parts = args.split(maxsplit=2)
        if len(parts) < 3:
            return CommandResult(
                False,
                "请提供账号别名、用户名和密码\n用法: /日历 注册 {别名} {用户名} {密码}"
            )

        account_name, username, password = parts
        if len(password) < 6:
            return CommandResult(False, "密码至少需要6位")

        success, msg = await self._account_manager.register_account(
            account_name, username, password
        )

        if success:
            return CommandResult(True, f"✅ {msg}", action="calendar_register")
        return CommandResult(False, f"❌ {msg}")

    async def _add_event(self, args: str, qq: int) -> CommandResult:
        parts = args.split(maxsplit=3)
        if not parts or not parts[0]:
            return CommandResult(False, "请提供日程标题")

        title = parts[0]
        date = parts[1] if len(parts) > 1 else None
        time = parts[2] if len(parts) > 2 else None
        location = parts[3] if len(parts) > 3 else None

        success, msg, result = await self._account_manager.add_event(
            title=title, date=date, time=time, location=location, qq=qq
        )

        if success:
            return CommandResult(True, f"✅ {msg}", action="calendar_add_event")
        return CommandResult(False, f"❌ {msg}")

    async def _add_todo(self, args: str, qq: int) -> CommandResult:
        parts = args.split(maxsplit=2)
        if not parts or not parts[0]:
            return CommandResult(False, "请提供待办标题")

        title = parts[0]
        deadline = parts[1] if len(parts) > 1 else None
        priority = parts[2] if len(parts) > 2 else "medium"

        if priority not in ("high", "medium", "low"):
            priority = "medium"

        success, msg, result = await self._account_manager.add_todo(
            title=title, deadline=deadline, priority=priority, qq=qq
        )

        if success:
            return CommandResult(True, f"✅ {msg}", action="calendar_add_todo")
        return CommandResult(False, f"❌ {msg}")

    async def _list_events(self, qq: int) -> CommandResult:
        events = await self._account_manager.get_events(qq=qq)
        if not events:
            return CommandResult(True, "📅 当前没有日程安排")

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
        return CommandResult(True, "\n".join(lines))

    async def _list_todos(self, qq: int) -> CommandResult:
        todos = await self._account_manager.get_todos(qq=qq)
        if not todos:
            return CommandResult(True, "📋 当前没有待办事项")

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
        return CommandResult(True, "\n".join(lines))

    def _help(self) -> CommandResult:
        lines = [
            "📖 日历管理命令：",
            "",
            "  绑定与账号：",
            "  /日历 绑定 {用户名} {密码} [别名]  - 绑定QQ号到calendar账号（推荐）",
            "  /日历 解绑                     - 解除当前QQ号的绑定",
            "  /日历 绑定状态                  - 查看绑定状态",
            "  /日历 切换账号 {用户名} {密码}    - 切换到其他账号",
            "  /日历 登录 {用户名} {密码} [别名] - 登录（不绑定QQ号）",
            "  /日历 登出                     - 登出当前账号",
            "  /日历 账号列表                  - 查看已保存的账号别名",
            "  /日历 注册 {别名} {用户名} {密码}  - 注册新账号",
            "",
            "  日程与待办：",
            "  /日历 添加日程 {标题} [日期] [时间] [地点]  - 添加日程",
            "  /日历 添加待办 {标题} [截止日期] [优先级]  - 添加待办",
            "  /日历 查看日程                  - 查看所有日程",
            "  /日历 查看待办                  - 查看所有待办",
            "",
            "💡 提示：绑定后可直接使用日历功能，无需每次登录",
            "📌 注意：用户名和密码是 calendar_backend 系统的账号密码",
        ]
        return CommandResult(True, "\n".join(lines))
