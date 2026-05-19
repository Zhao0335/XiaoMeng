"""
账号管理模块
管理多个日历账号，支持账号切换和QQ号绑定

重要说明：
- 账号密码直接使用 calendar_backend 系统的账号密码
- 本地不保存密码，只保存账号别名和用户名的映射
- 每次登录/切换都需要用户输入密码，直接向 calendar_backend 验证
- 支持QQ号与calendar账号的绑定关系管理
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from binding_manager import BindingManager, BindingInfo
from calendar_client import CalendarClient
from config import CalendarMakerConfig

logger = logging.getLogger(__name__)


class AccountManagerError(Exception):
    """账号管理错误"""
    pass


class AccountManager:
    """
    账号管理器
    
    功能：
    - 管理多个日历账号的别名映射
    - 支持账号切换（需密码验证）
    - 直接使用 calendar_backend 的账号密码系统
    - 支持QQ号与calendar账号的绑定管理
    
    注意：
    - 本地不保存密码，只保存账号别名和用户名的映射
    - 每次操作都需要用户输入密码
    - 登录成功后保存 session_id 用于后续操作
    - QQ号绑定关系长期有效，直到用户主动解除或会话过期
    """

    def __init__(
        self,
        config: CalendarMakerConfig,
        data_dir: Path,
    ):
        self._config = config
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._client = CalendarClient(
            base_url=config.backend.backend_url,
            timeout=config.backend.timeout,
            retry_count=config.backend.retry_count,
            retry_delay=config.backend.retry_delay,
        )

        self._accounts_file = self._data_dir / "calendar_accounts.json"
        self._current_account: Optional[str] = config.default_account
        self._accounts: dict[str, dict] = {}

        self._binding_manager = BindingManager(
            data_dir=self._data_dir,
            session_ttl_days=config.security.session_ttl_days,
        )

        self._load_accounts()

    def _load_accounts(self) -> None:
        if self._accounts_file.exists():
            try:
                data = json.loads(self._accounts_file.read_text(encoding="utf-8"))
                self._accounts = data.get("accounts", {})
                self._current_account = data.get("current_account", self._current_account)
                
                if self._current_account and self._current_account in self._accounts:
                    acc = self._accounts[self._current_account]
                    session_id = acc.get("session_id")
                    username = acc.get("username")
                    if session_id and username:
                        self._client.set_session(session_id, username)
            except Exception as e:
                logger.error(f"加载账号数据失败: {e}")

    def _save_accounts(self) -> None:
        try:
            if self._current_account and self._current_account in self._accounts:
                self._accounts[self._current_account]["session_id"] = self._client.session_id
                self._accounts[self._current_account]["last_used"] = datetime.now(UTC).isoformat()
            
            data = {
                "accounts": self._accounts,
                "current_account": self._current_account,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._accounts_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"保存账号数据失败: {e}")

    @property
    def current_account(self) -> Optional[str]:
        return self._current_account

    @property
    def is_logged_in(self) -> bool:
        return self._client.is_authenticated

    @property
    def client(self) -> CalendarClient:
        return self._client

    @property
    def binding_manager(self) -> BindingManager:
        return self._binding_manager

    def list_accounts(self) -> list[dict]:
        result = []
        for name, acc in self._accounts.items():
            result.append({
                "name": name,
                "username": acc.get("username", name),
                "is_current": name == self._current_account,
                "last_used": acc.get("last_used"),
            })
        return result

    async def register_account(
        self,
        account_name: str,
        username: str,
        password: str,
    ) -> tuple[bool, str]:
        success, msg = await self._client.register(username, password)
        if not success:
            return False, f"注册失败: {msg}"

        success, msg = await self._client.login(username, password)
        if not success:
            return False, f"注册成功但登录失败: {msg}"

        self._accounts[account_name] = {
            "username": username,
            "created_at": datetime.now(UTC).isoformat(),
            "last_used": datetime.now(UTC).isoformat(),
            "session_id": self._client.session_id,
        }
        self._current_account = account_name
        self._save_accounts()

        return True, f"账号 {account_name}（用户名: {username}）注册并登录成功"

    async def login_account(
        self,
        username: str,
        password: str,
        account_name: Optional[str] = None,
    ) -> tuple[bool, str]:
        actual_username = username
        
        if username in self._accounts:
            actual_username = self._accounts[username].get("username", username)
            account_name = username
        
        success, msg = await self._client.login(actual_username, password)
        if not success:
            return False, f"登录失败: {msg}"

        if account_name is None:
            account_name = actual_username

        if account_name not in self._accounts:
            self._accounts[account_name] = {
                "username": actual_username,
                "created_at": datetime.now(UTC).isoformat(),
            }
        
        self._accounts[account_name]["last_used"] = datetime.now(UTC).isoformat()
        self._accounts[account_name]["session_id"] = self._client.session_id
        self._current_account = account_name
        self._save_accounts()

        return True, f"账号 {account_name}（用户名: {actual_username}）登录成功"

    async def switch_account(
        self,
        username: str,
        password: str,
    ) -> tuple[bool, str]:
        if username in self._accounts:
            account_name = username
            if account_name == self._current_account and self._client.is_authenticated:
                return True, f"已经是当前账号: {account_name}"
        else:
            account_name = username

        return await self.login_account(username, password, account_name)

    def logout(self) -> tuple[bool, str]:
        if not self._current_account:
            return False, "没有登录的账号"

        account_name = self._current_account
        if account_name in self._accounts:
            self._accounts[account_name]["session_id"] = None
        self._client.logout()
        self._current_account = None
        self._save_accounts()

        return True, f"账号 {account_name} 已登出"

    def delete_account(self, account_name: str) -> tuple[bool, str]:
        if account_name not in self._accounts:
            return False, "账号不存在"

        if account_name == self._current_account:
            self._client.logout()
            self._current_account = None

        del self._accounts[account_name]
        self._save_accounts()
        return True, f"账号映射 {account_name} 已删除"

    async def bind_qq(
        self,
        qq: int,
        username: str,
        password: str,
        account_name: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        绑定QQ号到calendar账号
        
        流程：
        1. 使用用户名密码登录 calendar_backend
        2. 登录成功后创建绑定关系
        3. 保存 session_id 用于后续操作
        """
        success, msg = await self.login_account(username, password, account_name)
        if not success:
            return False, msg

        actual_username = self._client._username or username
        session_id = self._client.session_id
        
        if not session_id:
            return False, "登录成功但未获取到会话ID"

        return self._binding_manager.bind(
            qq=qq,
            calendar_username=actual_username,
            session_id=session_id,
            account_name=account_name or actual_username,
        )

    def unbind_qq(self, qq: int) -> tuple[bool, str]:
        """解除QQ号的绑定"""
        return self._binding_manager.unbind(qq)

    def is_qq_bound(self, qq: int) -> bool:
        """检查QQ号是否已绑定"""
        return self._binding_manager.is_bound(qq)

    def get_qq_binding(self, qq: int) -> Optional[BindingInfo]:
        """获取QQ号的绑定信息"""
        return self._binding_manager.get_binding(qq)

    def get_qq_binding_status(self, qq: int) -> dict:
        """获取QQ号绑定状态详情"""
        return self._binding_manager.get_binding_status(qq)

    async def switch_qq_binding(
        self,
        qq: int,
        username: str,
        password: str,
        account_name: Optional[str] = None,
    ) -> tuple[bool, str]:
        """切换QQ号绑定的账号"""
        success, msg = await self.login_account(username, password, account_name)
        if not success:
            return False, msg

        actual_username = self._client._username or username
        session_id = self._client.session_id
        
        if not session_id:
            return False, "登录成功但未获取到会话ID"

        return self._binding_manager.switch_binding(
            qq=qq,
            calendar_username=actual_username,
            session_id=session_id,
            account_name=account_name or actual_username,
        )

    def set_context_from_binding(self, qq: int) -> tuple[bool, str]:
        """从绑定关系设置当前上下文"""
        binding = self._binding_manager.get_binding(qq)
        if not binding:
            return False, "该QQ号未绑定任何账号或绑定已过期"

        session_id = binding.session_id
        username = binding.calendar_username
        
        if not session_id:
            return False, "绑定信息中缺少会话ID"

        self._client.set_session(session_id, username)
        self._current_account = binding.account_name or username
        
        self._binding_manager.refresh_session(qq)
        
        return True, f"已切换到账号 {username}"

    async def add_event(
        self,
        title: str,
        qq: Optional[int] = None,
        date: Optional[str] = None,
        time: Optional[str] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> tuple[bool, str, Optional[dict]]:
        if qq and not self._client.is_authenticated:
            success, msg = self.set_context_from_binding(qq)
            if not success:
                return False, msg, None

        if not self._client.is_authenticated:
            return False, "未登录，请先登录或绑定账号", None

        from calendar_client import Event
        event = Event(title=title, date=date, time=time, location=location, notes=notes)

        try:
            result = await self._client.add_event(event)
            if qq:
                self._binding_manager.refresh_session(qq)
            return True, f"日程「{title}」添加成功", result
        except Exception as e:
            return False, f"添加日程失败: {e}", None

    async def add_todo(
        self,
        title: str,
        qq: Optional[int] = None,
        deadline: Optional[str] = None,
        priority: str = "medium",
        notes: Optional[str] = None,
    ) -> tuple[bool, str, Optional[dict]]:
        if qq and not self._client.is_authenticated:
            success, msg = self.set_context_from_binding(qq)
            if not success:
                return False, msg, None

        if not self._client.is_authenticated:
            return False, "未登录，请先登录或绑定账号", None

        from calendar_client import Todo
        todo = Todo(title=title, deadline=deadline, priority=priority, notes=notes)

        try:
            result = await self._client.add_todo(todo)
            if qq:
                self._binding_manager.refresh_session(qq)
            return True, f"待办「{title}」添加成功", result
        except Exception as e:
            return False, f"添加待办失败: {e}", None

    async def add_from_text(
        self,
        text: str,
        qq: Optional[int] = None,
    ) -> tuple[bool, str, Optional[dict]]:
        if qq and not self._client.is_authenticated:
            success, msg = self.set_context_from_binding(qq)
            if not success:
                return False, msg, None

        if not self._client.is_authenticated:
            return False, "未登录，请先登录或绑定账号", None

        try:
            result = await self._client.add_from_text(text)
            events = result.get("events", [])
            todos = result.get("todos", [])
            msg = result.get("message", "添加成功")
            if qq:
                self._binding_manager.refresh_session(qq)
            return True, msg, {"events": events, "todos": todos}
        except Exception as e:
            return False, f"添加失败: {e}", None

    async def get_events(self, qq: Optional[int] = None) -> list[dict]:
        if qq and not self._client.is_authenticated:
            success, msg = self.set_context_from_binding(qq)
            if not success:
                return []

        if not self._client.is_authenticated:
            return []
        return await self._client.get_events()

    async def get_todos(self, qq: Optional[int] = None) -> list[dict]:
        if qq and not self._client.is_authenticated:
            success, msg = self.set_context_from_binding(qq)
            if not success:
                return []

        if not self._client.is_authenticated:
            return []
        return await self._client.get_todos()

    async def health_check(self) -> bool:
        return await self._client.health_check()

    def list_bindings(self) -> list[BindingInfo]:
        """列出所有有效的绑定"""
        return self._binding_manager.list_bindings()
