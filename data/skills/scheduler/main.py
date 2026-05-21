#!/usr/bin/env python3
"""
⏰ 小萌定时提醒服务 v1.0
独立守护进程，通过 tasks.json 配置任务，通过 napcat API 发送消息。

运行方式：
    python3 skills/scheduler/main.py          # 启动
    python3 skills/scheduler/main.py --stop   # 停止（通过 PID 文件）
    python3 skills/scheduler/main.py --status # 查看状态
"""

import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# ====== 配置 ======
TASKS_FILE = Path(__file__).parent / "tasks.json"
PID_FILE = Path(__file__).parent / "scheduler.pid"
LOG_FILE = Path(__file__).parent / "scheduler.log"
NAPCAT_API = "http://127.0.0.1:3002"
POLL_INTERVAL = 5  # 每5秒检查一次任务文件

# ====== 日志 ======
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")


# ====== Napcat API 发送消息 ======
async def send_msg(text: str, target: dict):
    """发送 QQ 消息"""
    async with httpx.AsyncClient(timeout=10) as client:
        payload = {"message": text}
        if "group_id" in target:
            payload["group_id"] = target["group_id"]
        elif "user_id" in target:
            payload["user_id"] = target["user_id"]
        try:
            resp = await client.post(f"{NAPCAT_API}/send_msg", json=payload)
            if resp.status_code == 200:
                log(f"✅ 消息发送成功 -> {target}")
            else:
                log(f"❌ 消息发送失败 [{resp.status_code}]: {resp.text}")
        except Exception as e:
            log(f"❌ 消息发送异常: {e}")


# ====== 任务解析和执行 ======
def parse_cron(cron_str: str):
    """解析 cron 表达式 '9:30' -> (hour=9, minute=30)"""
    try:
        parts = cron_str.strip().split(":")
        return {"hour": int(parts[0]), "minute": int(parts[1])}
    except:
        return None


def should_run_now(task: dict, last_run: dict) -> bool:
    """检查当前时间是否应该执行任务（防止重复触发）"""
    now = datetime.now()
    cron = parse_cron(task.get("cron", ""))
    if not cron:
        return False

    # 检查是否为指定时间
    if now.hour != cron["hour"] or now.minute != cron["minute"]:
        return False

    # 检查是否已在本分钟内执行过
    task_id = task.get("id", "")
    last = last_run.get(task_id)
    if last and last == f"{now.hour}:{now.minute}":
        return False

    # 检查星期匹配
    weekdays = task.get("weekdays", None)
    if weekdays is not None:
        weekday_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        if now.weekday() >= len(weekday_names):
            return False
        if weekday_names[now.weekday()] not in weekdays:
            return False

    return True


async def check_and_run_tasks(tasks: list, last_run: dict) -> dict:
    """检查并执行到时的任务"""
    now = datetime.now()
    for task in tasks:
        task_id = task.get("id", "")
        task_type = task.get("type", "cron")

        if task_type == "cron":
            if should_run_now(task, last_run):
                log(f"🔔 执行定时任务 [{task_id}]: {task.get('msg', '')}")
                await send_msg(task.get("msg", "⏰ 小萌提醒时间到！"), task.get("target", {}))
                last_run[task_id] = f"{now.hour}:{now.minute}"

        elif task_type == "interval":
            # 间隔任务：检查上一次执行时间
            interval_minutes = task.get("interval_minutes", 60)
            last = task.get("_last_run_time", 0)
            if time.time() - last >= interval_minutes * 60:
                log(f"🔔 执行间隔任务 [{task_id}]: {task.get('msg', '')}")
                await send_msg(task.get("msg", "⏰ 小萌提醒时间到！"), task.get("target", {}))
                task["_last_run_time"] = time.time()

        elif task_type == "once":
            # 一次性任务：检查是否到了执行时间
            run_at = task.get("run_at", "")
            target_time = parse_cron(run_at)
            if target_time:
                if now.hour == target_time["hour"] and now.minute == target_time["minute"]:
                    if not task.get("_done", False):
                        log(f"🔔 执行一次性任务 [{task_id}]: {task.get('msg', '')}")
                        await send_msg(task.get("msg", "⏰ 小萌提醒时间到！"), task.get("target", {}))
                        task["_done"] = True

    return last_run


def load_tasks() -> list:
    """从 tasks.json 加载任务"""
    if not TASKS_FILE.exists():
        return []
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("tasks", [])
    except Exception as e:
        log(f"⚠️ 读取任务文件失败: {e}")
        return []


# ====== 信号处理 ======
running = True

def handle_signal(sig, frame):
    global running
    log("🛑 收到停止信号，scheduler 即将退出...")
    running = False


# ====== 主循环 ======
async def main_loop():
    global running
    log("🚀 小萌定时提醒服务启动")
    
    last_run = {}
    last_mtime = 0
    tasks = []

    while running:
        # 检查任务文件是否有变化
        current_mtime = TASKS_FILE.stat().st_mtime if TASKS_FILE.exists() else 0
        if current_mtime != last_mtime:
            tasks = load_tasks()
            last_mtime = current_mtime
            log(f"📋 已加载 {len(tasks)} 个任务")

        # 执行到时的任务
        if tasks:
            last_run = await check_and_run_tasks(tasks, last_run)

        await asyncio.sleep(POLL_INTERVAL)

    log("👋 Scheduler 已停止")


# ====== 入口 ======
def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def read_pid():
    if PID_FILE.exists():
        with open(PID_FILE) as f:
            try:
                return int(f.read().strip())
            except:
                return None
    return None

def stop_scheduler():
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            log(f"已发送停止信号到进程 {pid}")
            PID_FILE.unlink(missing_ok=True)
            return True
        except ProcessLookupError:
            log("进程不存在，清理 PID 文件")
            PID_FILE.unlink(missing_ok=True)
            return True
        except Exception as e:
            log(f"停止失败: {e}")
            return False
    else:
        log("没有找到运行中的 scheduler")
        return False

def status_scheduler():
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, 0)  # 检查进程是否存在
            log(f"✅ Scheduler 正在运行 (PID: {pid})")
            return True
        except:
            log("⚠️ PID 文件存在但进程已不存在")
            PID_FILE.unlink(missing_ok=True)
            return False
    else:
        log("❌ Scheduler 未运行")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--stop":
            stop_scheduler()
        elif sys.argv[1] == "--status":
            status_scheduler()
        sys.exit(0)

    # 检查是否已在运行
    if read_pid():
        log("⚠️ Scheduler 已在运行，请先停止")
        sys.exit(1)

    # 注册信号处理
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # 写 PID 文件
    write_pid()
    log(f"PID: {os.getpid()}")

    # 运行主循环
    asyncio.run(main_loop())
