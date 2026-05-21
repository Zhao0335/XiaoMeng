"""
AsyncTask 数据结构与 TaskStatus
===============================
独立的异步任务实体，与 TaskPool 解耦。
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


class TaskStatus:
    PENDING = "pending"
    QUEUED = "queued"  # 排队等待中（任务池满）
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class AsyncTask:
    task_id: str
    session_key: str
    sender_qq: int
    group_id: int = 0
    user_event_timeout: int = 600
    status: str = TaskStatus.PENDING
    queue_position: int = 0
    progress: List[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    loop_messages: List[Dict] = field(default_factory=list)
    react_steps: List[Dict] = field(default_factory=list)
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _user_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _user_response: Optional[str] = field(default=None, repr=False)
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_progress(self, msg: str) -> None:
        self.progress.append(msg)
        self.updated_at = datetime.now().isoformat()

    async def wait_for_user(self, prompt: str) -> Optional[str]:
        self._user_event.clear()
        self._user_response = None
        self.status = TaskStatus.WAITING_USER
        self.add_progress(f"[等待用户] {prompt}")
        try:
            await asyncio.wait_for(
                self._user_event.wait(), timeout=self.user_event_timeout
            )
            self.status = TaskStatus.RUNNING
            return self._user_response
        except asyncio.TimeoutError:
            self.status = TaskStatus.ERROR
            self.error = "等待用户反馈超时"
            return None

    def submit_user_input(self, text: str) -> None:
        self._user_response = text
        self._user_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._user_event.set()
