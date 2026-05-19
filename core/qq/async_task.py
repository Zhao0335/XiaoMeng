"""
异步任务执行系统
解决 QQ Bot 任务处理中断问题：先发确认消息，后台继续执行，支持暂停等待用户反馈

任务状态机:
  PENDING → RUNNING → (WAITING_USER)* → DONE
                    ↘ ERROR
                    ↘ CANCELLED

使用方式:
  gateway 收到消息 → task_manager.create_and_run(task_id, context) → 立即返回确认消息
  后台 asyncio.Task 执行完整工具调用循环
  需要用户输入时 → await task.wait_for_user() → 用户回复后 resume
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskStatus:
    PENDING = "pending"
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
    progress: List[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    loop_messages: List[Dict] = field(default_factory=list)
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
            await asyncio.wait_for(self._user_event.wait(), timeout=self.user_event_timeout)
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


class AsyncTaskManager:
    def __init__(
        self,
        db_path: str,
        send_message: Callable[..., Any],
        user_event_timeout: int = 600,
    ):
        self._db_path = db_path
        self._send_message = send_message
        self._user_event_timeout = user_event_timeout
        self._tasks: Dict[str, AsyncTask] = {}
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS async_tasks (
                task_id      TEXT PRIMARY KEY,
                session_key  TEXT NOT NULL,
                sender_qq    INTEGER NOT NULL,
                group_id     INTEGER DEFAULT 0,
                status       TEXT NOT NULL DEFAULT 'pending',
                progress     TEXT NOT NULL DEFAULT '[]',
                loop_messages TEXT NOT NULL DEFAULT '[]',
                result       TEXT,
                error        TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_at_session ON async_tasks(session_key);
            CREATE INDEX IF NOT EXISTS idx_at_status ON async_tasks(status);
        """)
        conn.commit()
        conn.close()

    def _save(self, task: AsyncTask) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT OR REPLACE INTO async_tasks
                   (task_id, session_key, sender_qq, group_id, status,
                    progress, loop_messages, result, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id,
                    task.session_key,
                    task.sender_qq,
                    task.group_id,
                    task.status,
                    json.dumps(task.progress, ensure_ascii=False),
                    json.dumps(task.loop_messages, ensure_ascii=False),
                    task.result,
                    task.error,
                    task.created_at,
                    task.updated_at,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"持久化任务失败: {e}")

    def get_task(self, task_id: str) -> Optional[AsyncTask]:
        return self._tasks.get(task_id)

    def get_active_task_for_session(self, session_key: str) -> Optional[AsyncTask]:
        for task in self._tasks.values():
            if task.session_key == session_key and task.status in (
                TaskStatus.RUNNING, TaskStatus.WAITING_USER, TaskStatus.PENDING,
            ):
                return task
        return None

    async def create_and_run(
        self,
        session_key: str,
        sender_qq: int,
        group_id: int,
        coro_factory: Callable[["AsyncTask"], Any],
    ) -> AsyncTask:
        task_id = str(uuid.uuid4())[:8]
        task = AsyncTask(
            task_id=task_id,
            session_key=session_key,
            sender_qq=sender_qq,
            group_id=group_id,
            user_event_timeout=self._user_event_timeout,
            status=TaskStatus.PENDING,
        )
        async with self._lock:
            self._tasks[task_id] = task
        self._save(task)

        async def _wrapper():
            try:
                task.status = TaskStatus.RUNNING
                self._save(task)
                logger.info(f"任务 {task_id} 开始执行 (session={session_key})")
                result = await coro_factory(task)
                if task.is_cancelled():
                    task.status = TaskStatus.CANCELLED
                else:
                    task.status = TaskStatus.DONE
                    task.result = result
            except Exception as e:
                logger.exception(f"任务 {task_id} 执行失败")
                task.status = TaskStatus.ERROR
                task.error = str(e)
            finally:
                task.updated_at = datetime.now().isoformat()
                self._save(task)
                logger.info(f"任务 {task_id} 结束: {task.status}")

        task._asyncio_task = asyncio.create_task(_wrapper(), name=f"task-{task_id}")
        return task

    async def submit_to_task(self, task_id: str, text: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.status != TaskStatus.WAITING_USER:
            return False
        task.submit_user_input(text)
        self._save(task)
        return True

    async def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.WAITING_USER):
            return False
        task.cancel()
        if task._asyncio_task and not task._asyncio_task.done():
            task._asyncio_task.cancel()
        self._save(task)
        return True

    async def send_progress(self, task: AsyncTask, text: str) -> None:
        task.add_progress(text)
        self._save(task)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._send_message(task, text)
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    logger.warning(f"发送进度消息失败(重试 {attempt + 1}/{max_retries}): {e}")
                else:
                    logger.error(f"发送进度消息失败(已重试{max_retries}次): {e}")
                    raise

    def get_status_summary(self, task: AsyncTask) -> str:
        status_emoji = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.WAITING_USER: "⏸️",
            TaskStatus.DONE: "✅",
            TaskStatus.ERROR: "❌",
            TaskStatus.CANCELLED: "🚫",
        }
        lines = [
            f"{status_emoji.get(task.status, '❓')} 任务 {task.task_id} [{task.status}]",
        ]
        if task.progress:
            recent = task.progress[-5:]
            for p in recent:
                lines.append(f"  • {p}")
        if task.result:
            lines.append(f"\n{task.result[:500]}")
        if task.error:
            lines.append(f"\n错误: {task.error}")
        return "\n".join(lines)

    def load_running_tasks_from_db(self, coro_factory: Callable) -> List[str]:
        """启动时恢复未完成任务。如果无法恢复（上下文丢失），标记为 ERROR。"""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM async_tasks WHERE status IN ('pending', 'running', 'waiting_user')"
            )
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
        except Exception:
            return []

        for r in rows:
            try:
                now = datetime.now().isoformat()
                conn2 = sqlite3.connect(self._db_path)
                conn2.execute(
                    "UPDATE async_tasks SET status='error', error='Bot 重启导致任务中断', updated_at=? WHERE task_id=?",
                    (now, r["task_id"]),
                )
                conn2.commit()
                conn2.close()
            except Exception:
                pass

        return []
