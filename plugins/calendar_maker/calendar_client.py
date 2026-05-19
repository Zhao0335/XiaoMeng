"""
Calendar Backend API 客户端
与 calendar_backend 系统通信
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Event:
    title: str
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        result = {"title": self.title}
        if self.date:
            result["date"] = self.date
        if self.time:
            result["time"] = self.time
        if self.location:
            result["location"] = self.location
        if self.notes:
            result["notes"] = self.notes
        return result


@dataclass
class Todo:
    title: str
    deadline: Optional[str] = None
    priority: str = "medium"
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        result = {"title": self.title, "priority": self.priority}
        if self.deadline:
            result["deadline"] = self.deadline
        if self.notes:
            result["notes"] = self.notes
        return result


class CalendarClientError(Exception):
    """日历客户端错误基类"""
    pass


class AuthenticationError(CalendarClientError):
    """认证错误"""
    pass


class ConnectionError(CalendarClientError):
    """连接错误"""
    pass


class CalendarClient:
    """
    Calendar Backend API 客户端
    
    支持的操作：
    - 用户认证（登录/注册）
    - 日程管理（添加/查询/更新/删除）
    - 待办管理（添加/查询/更新/删除）
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:5522",
        timeout: float = 30.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retry_count = retry_count
        self._retry_delay = retry_delay
        self._session_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._username: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return self._session_id is not None

    @property
    def current_user(self) -> Optional[str]:
        return self._username

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._session_id:
            headers["Authorization"] = f"Bearer {self._session_id}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
    ) -> dict:
        url = f"{self._base_url}{endpoint}"
        headers = self._get_headers()

        for attempt in range(self._retry_count):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    if method == "GET":
                        response = await client.get(url, headers=headers)
                    elif method == "POST":
                        response = await client.post(url, headers=headers, json=data)
                    elif method == "PUT":
                        response = await client.put(url, headers=headers, json=data)
                    elif method == "DELETE":
                        response = await client.delete(url, headers=headers)
                    else:
                        raise ValueError(f"不支持的HTTP方法: {method}")

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 401:
                        raise AuthenticationError("认证失败，请重新登录")
                    elif response.status_code == 409:
                        raise CalendarClientError(f"资源冲突: {response.text}")
                    else:
                        raise CalendarClientError(
                            f"请求失败: {response.status_code} - {response.text}"
                        )

            except httpx.TimeoutException:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self._retry_count}): {url}")
                if attempt < self._retry_count - 1:
                    await asyncio.sleep(self._retry_delay)
                else:
                    raise ConnectionError("连接超时")

            except httpx.ConnectError:
                logger.warning(f"连接失败 (尝试 {attempt + 1}/{self._retry_count}): {url}")
                if attempt < self._retry_count - 1:
                    await asyncio.sleep(self._retry_delay)
                else:
                    raise ConnectionError("无法连接到服务器")

        raise ConnectionError("请求失败")

    async def health_check(self) -> bool:
        try:
            result = await self._request("GET", "/health")
            return result.get("status") == "ok"
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False

    async def register(self, username: str, password: str) -> tuple[bool, str]:
        try:
            await self._request("POST", "/auth/register", {
                "username": username,
                "password": password,
            })
            return True, "注册成功"
        except CalendarClientError as e:
            if "409" in str(e) or "已存在" in str(e):
                return False, "用户名已存在"
            return False, str(e)

    async def login(self, username: str, password: str) -> tuple[bool, str]:
        try:
            result = await self._request("POST", "/auth/login", {
                "username": username,
                "password": password,
            })
            self._session_id = result.get("session_id")
            self._username = result.get("username")
            return True, "登录成功"
        except CalendarClientError as e:
            return False, str(e)

    def logout(self) -> None:
        self._session_id = None
        self._user_id = None
        self._username = None

    def set_session(self, session_id: str, username: str) -> None:
        self._session_id = session_id
        self._username = username

    async def get_me(self) -> Optional[dict]:
        try:
            return await self._request("GET", "/auth/me")
        except Exception:
            return None

    async def add_event(self, event: Event) -> dict:
        if not self.is_authenticated:
            raise AuthenticationError("未登录，请先登录")

        try:
            result = await self._request("POST", "/extract", {
                "text": self._format_event_text(event),
                "current_date": datetime.now().strftime("%Y-%m-%d"),
            })
            events = result.get("events", [])
            if events:
                return events[0]
            return {"title": event.title, "status": "created"}
        except Exception as e:
            logger.error(f"添加日程失败: {e}")
            raise

    async def add_events(self, events: list[Event]) -> list[dict]:
        if not self.is_authenticated:
            raise AuthenticationError("未登录，请先登录")

        try:
            texts = [self._format_event_text(e) for e in events]
            result = await self._request("POST", "/extract", {
                "text": "\n".join(texts),
                "current_date": datetime.now().strftime("%Y-%m-%d"),
            })
            return result.get("events", [])
        except Exception as e:
            logger.error(f"批量添加日程失败: {e}")
            raise

    async def add_todo(self, todo: Todo) -> dict:
        if not self.is_authenticated:
            raise AuthenticationError("未登录，请先登录")

        try:
            result = await self._request("POST", "/extract", {
                "text": self._format_todo_text(todo),
                "current_date": datetime.now().strftime("%Y-%m-%d"),
            })
            todos = result.get("todos", [])
            if todos:
                return todos[0]
            return {"title": todo.title, "status": "created"}
        except Exception as e:
            logger.error(f"添加待办失败: {e}")
            raise

    async def add_todos(self, todos: list[Todo]) -> list[dict]:
        if not self.is_authenticated:
            raise AuthenticationError("未登录，请先登录")

        try:
            texts = [self._format_todo_text(t) for t in todos]
            result = await self._request("POST", "/extract", {
                "text": "\n".join(texts),
                "current_date": datetime.now().strftime("%Y-%m-%d"),
            })
            return result.get("todos", [])
        except Exception as e:
            logger.error(f"批量添加待办失败: {e}")
            raise

    async def add_from_text(self, text: str) -> dict:
        if not self.is_authenticated:
            raise AuthenticationError("未登录，请先登录")

        try:
            result = await self._request("POST", "/extract", {
                "text": text,
                "current_date": datetime.now().strftime("%Y-%m-%d"),
            })
            return result
        except Exception as e:
            logger.error(f"从文本添加日程失败: {e}")
            raise

    async def get_events(self) -> list[dict]:
        if not self.is_authenticated:
            raise AuthenticationError("未登录，请先登录")

        try:
            result = await self._request("GET", "/items/events")
            return result
        except Exception as e:
            logger.error(f"获取日程列表失败: {e}")
            return []

    async def get_todos(self) -> list[dict]:
        if not self.is_authenticated:
            raise AuthenticationError("未登录，请先登录")

        try:
            result = await self._request("GET", "/items/todos")
            return result
        except Exception as e:
            logger.error(f"获取待办列表失败: {e}")
            return []

    @staticmethod
    def _format_event_text(event: Event) -> str:
        parts = [event.title]
        if event.date:
            parts.append(event.date)
        if event.time:
            parts.append(event.time)
        if event.location:
            parts.append(f"地点：{event.location}")
        if event.notes:
            parts.append(f"备注：{event.notes}")
        return " ".join(parts)

    @staticmethod
    def _format_todo_text(todo: Todo) -> str:
        parts = [f"待办：{todo.title}"]
        if todo.deadline:
            parts.append(f"截止日期：{todo.deadline}")
        if todo.priority != "medium":
            parts.append(f"优先级：{todo.priority}")
        if todo.notes:
            parts.append(f"备注：{todo.notes}")
        return " ".join(parts)
