"""
Scheduler Plugin — 定时任务管理

提供 LLM 可调用的工具来管理 data/skills/scheduler/tasks.json：
  scheduler_list    — 列出所有任务
  scheduler_add     — 添加/更新一个任务
  scheduler_remove  — 删除一个任务
  scheduler_start   — 启动 scheduler 守护进程
  scheduler_stop    — 停止 scheduler 守护进程
  scheduler_status  — 查看 scheduler 运行状态

守护进程本体：data/skills/scheduler/main.py
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

# XiaoMeng 根目录（plugin.py 在 data/plugins/scheduler/ 下，往上三级）
_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from core.plugins.base import PluginBase, PluginMetadata, ToolDefinition

_SCHEDULER_DIR = Path(__file__).parent.parent.parent / "skills" / "scheduler"
_TASKS_FILE = _SCHEDULER_DIR / "tasks.json"
_PID_FILE = _SCHEDULER_DIR / "scheduler.pid"
_MAIN_PY = _SCHEDULER_DIR / "main.py"


def _load_tasks() -> dict:
    if not _TASKS_FILE.exists():
        return {"tasks": []}
    try:
        return json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"tasks": []}


def _save_tasks(data: dict) -> None:
    _TASKS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_pid() -> int | None:
    if not _PID_FILE.exists():
        return None
    try:
        return int(_PID_FILE.read_text().strip())
    except Exception:
        return None


def _is_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


class SchedulerPlugin(PluginBase):
    """定时任务管理插件"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="scheduler",
            version="1.1.0",
            description="定时任务管理：查看、添加、删除、启停定时任务",
            author="XiaoMeng",
            tags=["scheduler", "automation"],
        )

    async def on_initialize(self) -> bool:
        self.register_tool(ToolDefinition(
            name="scheduler_list",
            description="列出 tasks.json 中所有定时任务（含 cron/quiz/interval/once 类型）。",
            parameters={"type": "object", "properties": {}, "required": []},
            min_user_level=1,  # admin+
        ))
        self.register_tool(ToolDefinition(
            name="scheduler_add",
            description=(
                "添加或更新一个定时任务。id 相同则覆盖。\n"
                "task 字段为完整任务对象（JSON），必须包含 id、type、target。\n"
                "cron 类型还需 cron（'HH:MM'）和 msg；quiz 类型还需 cron、subject、difficulty、grade。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "object",
                        "description": "完整任务对象，参见技能文档中的格式",
                    }
                },
                "required": ["task"],
            },
            min_user_level=1,  # admin+
            progress_msg="（小萌添加定时任务~）",
        ))
        self.register_tool(ToolDefinition(
            name="scheduler_remove",
            description="按 id 删除一个定时任务。",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "要删除的任务 id"}
                },
                "required": ["task_id"],
            },
            min_user_level=1,  # admin+
            progress_msg="（小萌删除定时任务~）",
        ))
        self.register_tool(ToolDefinition(
            name="scheduler_start",
            description="启动 scheduler 守护进程（后台运行，5秒内自动加载 tasks.json）。",
            parameters={"type": "object", "properties": {}, "required": []},
            min_user_level=2,  # owner only
            progress_msg="（小萌启动定时服务~）",
        ))
        self.register_tool(ToolDefinition(
            name="scheduler_stop",
            description="停止 scheduler 守护进程。",
            parameters={"type": "object", "properties": {}, "required": []},
            min_user_level=2,  # owner only
            progress_msg="（小萌停止定时服务~）",
        ))
        self.register_tool(ToolDefinition(
            name="scheduler_status",
            description="查看 scheduler 守护进程当前运行状态。",
            parameters={"type": "object", "properties": {}, "required": []},
            min_user_level=1,  # admin+
        ))
        return True

    async def on_shutdown(self) -> None:
        pass

    async def on_tool_call(
        self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        if tool_name == "scheduler_list":
            return self._list_tasks()
        elif tool_name == "scheduler_add":
            return self._add_task(arguments.get("task", {}))
        elif tool_name == "scheduler_remove":
            return self._remove_task(arguments.get("task_id", ""))
        elif tool_name == "scheduler_start":
            return self._start_scheduler()
        elif tool_name == "scheduler_stop":
            return self._stop_scheduler()
        elif tool_name == "scheduler_status":
            return self._get_status()
        return f"未知工具: {tool_name}"

    # ── 工具实现 ────────────────────────────────────────────────

    def _list_tasks(self) -> str:
        data = _load_tasks()
        tasks = data.get("tasks", [])
        if not tasks:
            return "当前没有任何定时任务。"
        lines = [f"共 {len(tasks)} 个任务：\n"]
        for t in tasks:
            tid = t.get("id", "?")
            typ = t.get("type", "?")
            cron = t.get("cron", t.get("run_at", ""))
            target = t.get("target", {})
            if isinstance(target, str):
                target = {"user_id": target}
            target_str = f"群{target['group_id']}" if "group_id" in target else f"私聊{target.get('user_id','?')}"
            extra = ""
            if typ == "quiz":
                extra = f" [{t.get('subject','?')} {t.get('difficulty','?')}]"
            elif typ == "cron":
                extra = f" 消息={t.get('msg','')[:20]}"
            lines.append(f"• [{tid}] {typ} {cron} → {target_str}{extra}")
        return "\n".join(lines)

    def _add_task(self, task: dict) -> str:
        if not task or not task.get("id"):
            return "task 参数不能为空，且必须包含 id 字段。"
        # 兼容 LLM 把 target 传成字符串（应为 {"user_id":...} 或 {"group_id":...}）
        target = task.get("target")
        if isinstance(target, str):
            task["target"] = {"user_id": int(target)} if target.isdigit() else {"user_id": target}
        data = _load_tasks()
        tasks: List[dict] = data.get("tasks", [])
        existing_ids = [t.get("id") for t in tasks]
        if task["id"] in existing_ids:
            tasks = [task if t.get("id") == task["id"] else t for t in tasks]
            action = "已更新"
        else:
            tasks.append(task)
            action = "已添加"
        data["tasks"] = tasks
        _save_tasks(data)
        return f"{action}任务 [{task['id']}]（类型: {task.get('type','?')}，共 {len(tasks)} 个任务）"

    def _remove_task(self, task_id: str) -> str:
        if not task_id:
            return "task_id 不能为空。"
        data = _load_tasks()
        tasks = data.get("tasks", [])
        before = len(tasks)
        tasks = [t for t in tasks if t.get("id") != task_id]
        if len(tasks) == before:
            return f"未找到任务 [{task_id}]。"
        data["tasks"] = tasks
        _save_tasks(data)
        return f"已删除任务 [{task_id}]，剩余 {len(tasks)} 个任务。"

    def _start_scheduler(self) -> str:
        if _is_running():
            return f"Scheduler 已在运行中（PID: {_read_pid()}）。"
        if not _MAIN_PY.exists():
            return f"找不到 scheduler 主程序: {_MAIN_PY}"
        try:
            proc = subprocess.Popen(
                [sys.executable, str(_MAIN_PY)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return f"Scheduler 已启动（PID: {proc.pid}）。"
        except Exception as e:
            return f"启动失败: {e}"

    def _stop_scheduler(self) -> str:
        pid = _read_pid()
        if pid is None or not _is_running():
            return "Scheduler 未在运行。"
        try:
            os.kill(pid, signal.SIGTERM)
            _PID_FILE.unlink(missing_ok=True)
            return f"已发送停止信号给 PID {pid}。"
        except Exception as e:
            return f"停止失败: {e}"

    def _get_status(self) -> str:
        if _is_running():
            pid = _read_pid()
            data = _load_tasks()
            n = len(data.get("tasks", []))
            return f"✅ Scheduler 运行中（PID: {pid}），共 {n} 个任务。"
        else:
            return "❌ Scheduler 未运行。"
