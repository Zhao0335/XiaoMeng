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
import uuid
from datetime import datetime
from pathlib import Path

# data/ 根目录（main.py 在 data/skills/scheduler/ 下，往上三级）
DATA_DIR = Path(__file__).parent.parent.parent

# ====== 配置 ======
TASKS_FILE = Path(__file__).parent / "tasks.json"
PID_FILE = Path(__file__).parent / "scheduler.pid"
LOG_FILE = Path(__file__).parent / "scheduler.log"
POLL_INTERVAL = 5  # 每5秒检查一次任务文件

# NapCat WebSocket 连接参数（从 qq_config.json 读取）
def _load_napcat_cfg():
    cfg_file = DATA_DIR / "qq_config.json"
    try:
        return json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

_napcat_cfg = _load_napcat_cfg()
NAPCAT_WS_URL = _napcat_cfg.get("napcat_ws_url", "ws://127.0.0.1:3002")
NAPCAT_TOKEN = _napcat_cfg.get("napcat_token", "")

def _get_model_for_route(route: str):
    """根据 route 获取模型配置"""
    models = _napcat_cfg.get("models", [])
    route = route.lower()
    
    if route == "local":
        for m in models:
            if m.get("layer") == "basic" and m.get("role") == "chat":
                return m
    elif route == "cloud":
        for m in models:
            if m.get("layer") == "brain" and m.get("role") == "reasoning":
                return m
    elif route == "pro":
        for m in models:
            if m.get("layer") == "pro" and m.get("role") == "reasoning":
                return m
    
    for m in models:
        if m.get("layer") == "brain" and m.get("role") == "reasoning":
            return m
    for m in models:
        if m.get("layer") == "basic" and m.get("role") == "chat":
            return m
    
    return None

# ====== 日志 ======
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{ts}] {msg}")


# ====== NapCat WebSocket 发送消息 ======
async def send_msg(text: str, target):
    """直接通过 NapCat WebSocket 发送 QQ 消息"""
    import websockets

    if isinstance(target, str):
        target = {"user_id": int(target)} if target.isdigit() else {}

    if "group_id" in target:
        action = "send_group_msg"
        params = {"group_id": target["group_id"], "message": text}
    elif "user_id" in target:
        action = "send_private_msg"
        params = {"user_id": target["user_id"], "message": text}
    else:
        log(f"❌ 无效目标: {target}")
        return

    echo = str(uuid.uuid4())[:8]
    payload = json.dumps({"action": action, "params": params, "echo": echo})
    headers = {"Authorization": f"Bearer {NAPCAT_TOKEN}"} if NAPCAT_TOKEN else {}
    try:
        async with websockets.connect(NAPCAT_WS_URL, additional_headers=headers, open_timeout=5) as ws:
            await ws.send(payload)
            resp_raw = await asyncio.wait_for(ws.recv(), timeout=8)
            resp = json.loads(resp_raw)
            if resp.get("status") == "ok":
                log(f"✅ 消息发送成功 -> {target}")
            else:
                log(f"❌ 消息发送失败: {resp}")
    except Exception as e:
        log(f"❌ 消息发送异常: {e}")


async def call_llm(prompt: str, route: str = "cloud", max_tokens: int = 2048, timeout: int = 120) -> str:
    """调用 LLM 生成内容"""
    import aiohttp
    
    model_cfg = _get_model_for_route(route)
    if not model_cfg:
        log(f"❌ 未找到 route={route} 的模型配置")
        return ""
    
    endpoint = model_cfg.get("endpoint", "")
    model_name = model_cfg.get("model_name", "")
    api_key = model_cfg.get("api_key", "")
    proxy = model_cfg.get("proxy", "")
    
    if not endpoint or not model_name:
        log(f"❌ 模型配置不完整: endpoint={endpoint}, model_name={model_name}")
        return ""
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": model_cfg.get("temperature", 0.7),
    }
    
    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        proxy_url = proxy if proxy else None
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(
                f"{endpoint}/chat/completions",
                json=payload,
                headers=headers,
                proxy=proxy_url,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    log(f"❌ LLM API 错误: {resp.status} - {text[:200]}")
                    return ""
                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content.strip()
    except asyncio.TimeoutError:
        log(f"❌ LLM 调用超时 ({timeout}s)")
        return ""
    except Exception as e:
        log(f"❌ LLM 调用异常: {e}")
        return ""


def clean_markdown(text: str) -> str:
    """清洗 markdown 语法"""
    import re
    if not text:
        return text
    result = text
    result = re.sub(r'```[\w]*\n.*?```', lambda m: m.group(0).replace('```', '').strip(), result, flags=re.DOTALL)
    result = re.sub(r'`([^`]+)`', r'\1', result)
    result = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', result)
    result = re.sub(r'\*\*([^*]+)\*\*', r'\1', result)
    result = re.sub(r'\*([^*]+)\*', r'\1', result)
    result = re.sub(r'__([^_]+)__', r'\1', result)
    result = re.sub(r'_([^_]+)_', r'\1', result)
    result = re.sub(r'~~([^~]+)~~', r'\1', result)
    result = re.sub(r'^#{1,6}\s*', '', result, flags=re.MULTILINE)
    result = re.sub(r'^>\s*', '', result, flags=re.MULTILINE)
    result = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', result)
    result = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'[图片]', result)
    result = re.sub(r'^[-*+]\s+', '• ', result, flags=re.MULTILINE)
    result = re.sub(r'^\d+\.\s+', '', result, flags=re.MULTILINE)
    result = re.sub(r'---+', '─────────', result)
    return result


# ====== 任务解析和执行 ======
def parse_cron(cron_str: str):
    """解析 cron 表达式 '9:30' -> (hour=9, minute=30)"""
    try:
        parts = cron_str.strip().split(":")
        return {"hour": int(parts[0]), "minute": int(parts[1])}
    except Exception:
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



async def check_and_run_tasks(tasks: list, last_run: dict, warned_tasks: set) -> tuple:
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
            interval_minutes = task.get("interval_minutes", 60)
            last = task.get("_last_run_time", 0)
            if time.time() - last >= interval_minutes * 60:
                log(f"🔔 执行间隔任务 [{task_id}]: {task.get('msg', '')}")
                await send_msg(task.get("msg", "⏰ 小萌提醒时间到！"), task.get("target", {}))
                task["_last_run_time"] = time.time()

        elif task_type == "once":
            run_at = task.get("run_at", "")
            if not task.get("_done", False):
                triggered = False
                # 支持 "YYYY-MM-DD HH:MM" 精确日期格式
                try:
                    from datetime import datetime as _dt
                    target_dt = _dt.strptime(run_at, "%Y-%m-%d %H:%M")
                    if (now.year == target_dt.year and now.month == target_dt.month and
                            now.day == target_dt.day and now.hour == target_dt.hour and
                            now.minute == target_dt.minute):
                        triggered = True
                except ValueError:
                    # 兼容旧格式 "HH:MM"（每天触发直到标记完成）
                    target_time = parse_cron(run_at)
                    if target_time and now.hour == target_time["hour"] and now.minute == target_time["minute"]:
                        triggered = True
                if triggered:
                    log(f"🔔 执行一次性任务 [{task_id}]: {task.get('msg', '')}")
                    await send_msg(task.get("msg", "⏰ 小萌提醒时间到！"), task.get("target", {}))
                    task["_done"] = True
                    # 持久化 _done 标记，防止重载后重复触发
                    _persist_task_done(TASKS_FILE, task_id)

        elif task_type == "instruct":
            if should_run_now(task, last_run):
                prompt = task.get("prompt", "")
                route = task.get("route", "cloud")
                target = task.get("target", {})
                
                if not prompt:
                    log(f"⚠️ instruct 任务 [{task_id}] 缺少 prompt")
                    continue
                
                log(f"🤖 执行 instruct 任务 [{task_id}]: 调用 {route} 模型...")
                content = await call_llm(prompt, route=route)
                
                if content:
                    content = clean_markdown(content)
                    parts = [p.strip() for p in content.split("\n\n") if p.strip()]
                    for part in parts:
                        await send_msg(part, target)
                    last_run[task_id] = f"{now.hour}:{now.minute}"
                else:
                    log(f"❌ instruct 任务 [{task_id}] LLM 返回空内容")

    return last_run, warned_tasks


def _persist_task_done(tasks_file: Path, task_id: str) -> None:
    """将 once 任务的 _done 标记写回 tasks.json，防止重启后重复触发。"""
    try:
        with open(tasks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for t in data.get("tasks", []):
            if t.get("id") == task_id:
                t["_done"] = True
                break
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"⚠️ 持久化 _done 失败: {e}")


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
    warned_tasks = set()
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
            last_run, warned_tasks = await check_and_run_tasks(tasks, last_run, warned_tasks)

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
            except Exception:
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
        except Exception:
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

    # 检查是否已在运行（排除 PID 被新进程复用的情况）
    old_pid = read_pid()
    my_pid = os.getpid()
    if old_pid and old_pid != my_pid:
        is_running = False
        try:
            os.kill(old_pid, 0)
            cmdline_path = Path(f"/proc/{old_pid}/cmdline")
            if cmdline_path.exists():
                cmdline = cmdline_path.read_bytes().replace(b"\x00", b" ").decode(errors="replace")
                is_running = "scheduler" in cmdline
        except (ProcessLookupError, PermissionError, OSError):
            pass
        if is_running:
            log("⚠️ Scheduler 已在运行，请先停止")
            sys.exit(1)
        else:
            log(f"清理过期 PID 文件 (pid={old_pid})")
            PID_FILE.unlink(missing_ok=True)
    elif old_pid == my_pid:
        log(f"清理自身 PID 复用的旧文件 (pid={old_pid})")
        PID_FILE.unlink(missing_ok=True)

    # 注册信号处理
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # 写 PID 文件
    write_pid()
    log(f"PID: {os.getpid()}")

    # 运行主循环
    asyncio.run(main_loop())
