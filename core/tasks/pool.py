"""
TaskPool - 基于 Semaphore 的并发任务池
======================================
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .task import AsyncTask, TaskStatus

logger = logging.getLogger(__name__)


class TaskPool:
    """
    任务池：基于 Semaphore 的并发任务管理器。

    特性：
    - max_concurrent 控制同时执行的任务数
    - 超出的任务自动排队，返回队列位置
    - 同一 session 允许有多个并发任务（独立上下文）
    """

    def __init__(
        self,
        db_path: str,
        send_message: Callable[..., Any],
        user_event_timeout: int = 600,
        max_concurrent: int = 3,
    ):
        self._db_path = db_path
        self._send_message = send_message
        self._user_event_timeout = user_event_timeout
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: Dict[str, AsyncTask] = {}
        self._lock = asyncio.Lock()
        self._init_db()

    # ── DB ──────────────────────────────────────────────────────

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
        conn = sqlite3.connect(self._db_path)
        try:
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
        except Exception as e:
            logger.warning(f"持久化任务失败: {e}")
        finally:
            conn.close()

    # ── 查询 ────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[AsyncTask]:
        return self._tasks.get(task_id)

    def get_active_tasks_for_session(self, session_key: str) -> List[AsyncTask]:
        result = []
        for task in self._tasks.values():
            if task.session_key == session_key and task.status in (
                TaskStatus.QUEUED,
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
                TaskStatus.WAITING_USER,
            ):
                result.append(task)
        return result

    def get_active_task_for_session(self, session_key: str) -> Optional[AsyncTask]:
        tasks = self.get_active_tasks_for_session(session_key)
        return tasks[0] if tasks else None

    def get_queue_position(self, task_id: str) -> int:
        task = self._tasks.get(task_id)
        if task is None or task.status != TaskStatus.QUEUED:
            return 0
        pos = 0
        for t in self._tasks.values():
            if t.status == TaskStatus.QUEUED and t.created_at < task.created_at:
                pos += 1
        return pos + 1

    # ── 提交与执行 ─────────────────────────────────────────────

    async def submit(
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
        )
        async with self._lock:
            self._tasks[task_id] = task

        if self._semaphore.locked():
            task.status = TaskStatus.QUEUED
            task.queue_position = self.get_queue_position(task_id)
            self._save(task)
            logger.info(
                f"任务 {task_id} 排队中 (session={session_key}), "
                f"前方 {task.queue_position} 个任务"
            )
        else:
            task.status = TaskStatus.PENDING
            task.queue_position = 0
            self._save(task)

        task._asyncio_task = asyncio.create_task(
            self._run_task(task, coro_factory), name=f"task-{task_id}"
        )
        return task

    async def _run_task(
        self, task: AsyncTask, coro_factory: Callable[["AsyncTask"], Any]
    ) -> None:
        async with self._semaphore:
            if task.status == TaskStatus.QUEUED:
                task.status = TaskStatus.RUNNING
                task.queue_position = 0
                self._save(task)
                logger.info(f"任务 {task.task_id} 从队列进入执行")
            else:
                task.status = TaskStatus.RUNNING
                self._save(task)

            try:
                logger.info(
                    f"任务 {task.task_id} 开始执行 (session={task.session_key})"
                )
                result = await coro_factory(task)
                if task.is_cancelled():
                    task.status = TaskStatus.CANCELLED
                else:
                    task.status = TaskStatus.DONE
                    task.result = result
            except Exception as e:
                logger.exception(f"任务 {task.task_id} 执行失败")
                task.status = TaskStatus.ERROR
                task.error = str(e)
            finally:
                task.updated_at = datetime.now().isoformat()
                self._save(task)
                logger.info(f"任务 {task.task_id} 结束: {task.status}")

    # ── 兼容接口 ───────────────────────────────────────────────

    async def create_and_run(
        self,
        session_key: str,
        sender_qq: int,
        group_id: int,
        coro_factory: Callable[["AsyncTask"], Any],
    ) -> AsyncTask:
        return await self.submit(
            session_key=session_key,
            sender_qq=sender_qq,
            group_id=group_id,
            coro_factory=coro_factory,
        )

    async def submit_to_task(self, task_id: str, text: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None or task.status != TaskStatus.WAITING_USER:
            return False
        task.submit_user_input(text)
        self._save(task)
        return True

    async def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.status not in (
            TaskStatus.QUEUED,
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_USER,
        ):
            return False
        task.cancel()
        if task._asyncio_task and not task._asyncio_task.done():
            task._asyncio_task.cancel()
        self._save(task)
        return True

    async def send_progress(self, task: AsyncTask, text: str) -> None:
        task.add_progress(text)
        self._save(task)
        for attempt in range(3):
            try:
                await self._send_message(task, text)
                return
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(1)
                    logger.warning(f"发送进度消息失败(重试 {attempt + 1}/3): {e}")
                else:
                    logger.error(f"发送进度消息失败(已重试3次): {e}")
                    raise

    # ── 状态展示 ───────────────────────────────────────────────

    def get_status_summary(self, task: AsyncTask) -> str:
        status_emoji = {
            TaskStatus.QUEUED: "\U0001f550",
            TaskStatus.PENDING: "\u23f3",
            TaskStatus.RUNNING: "\U0001f504",
            TaskStatus.WAITING_USER: "\u23f8\ufe0f",
            TaskStatus.DONE: "\u2705",
            TaskStatus.ERROR: "\u274c",
            TaskStatus.CANCELLED: "\U0001f6ab",
        }
        lines = [
            f"{status_emoji.get(task.status, '\u2753')} 任务 {task.task_id} [{task.status}]",
        ]
        if task.queue_position > 0:
            lines.append(f"  排队位置: 第 {task.queue_position} 位")
        if task.progress:
            for p in task.progress[-5:]:
                lines.append(f"  \u2022 {p}")
        if task.result:
            lines.append(f"\n{task.result[:500]}")
        if task.error:
            lines.append(f"\n错误: {task.error}")
        return "\n".join(lines)

    def load_running_tasks_from_db(self, coro_factory: Callable) -> List[str]:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM async_tasks WHERE status IN "
                "('pending','running','waiting_user','queued')"
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
                    "UPDATE async_tasks SET status='error', "
                    "error='Bot 重启导致任务中断', updated_at=? WHERE task_id=?",
                    (now, r["task_id"]),
                )
                conn2.commit()
                conn2.close()
            except Exception:
                pass
        return []
