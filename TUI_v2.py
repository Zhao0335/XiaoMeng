#!/usr/bin/env python3
"""
XiaoMeng Terminal v2 — Agent TUI
启动画面 → 分栏布局(左:吉祥物/状态 | 右:Tab内容) → 4个Tab切换
精致暗色风格，参考 whoami / Claude Code / OpenClaw 设计
"""

import asyncio
import copy
import curses
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = PROJECT_ROOT / "data" / "qq_config.json"

SENSITIVE_KEYS = {"api_key", "napcat_token", "token"}
SECRET_MASK = "******"

C_DEFAULT = 0
C_DIM = 1
C_ACCENT = 2
C_USER = 3
C_ASSISTANT = 4
C_TOOL = 5
C_SYSTEM = 6
C_ERROR = 7
C_SUCCESS = 8
C_BORDER = 9
C_HIGHLIGHT = 10
C_MASKED = 11
C_BOOL_ON = 12
C_BOOL_OFF = 13
C_MASCOT = 14
C_INPUT_BG = 15
C_SECTION = 16
C_FOOTER = 17
C_FOOTER_KEY = 18
C_PENDING = 19
C_MASCOT_EYES = 20
C_MASCOT_HAIR = 21
C_MASCOT_HOOD = 22
C_MASCOT_TAG = 23
C_BUBBLE_USER = 24
C_BUBBLE_ASST = 25
C_BUBBLE_SYSTEM = 26
C_TAB_ACTIVE = 27
C_TAB_INACTIVE = 28
C_SPLASH_TITLE = 29
C_SPLASH_SUB = 30
C_SPLASH_DIM = 31
C_TREE_NODE = 32
C_TREE_LEAF = 33
C_SCROLLBAR = 34


MASCOT_FULL = [
    ("     .      *     .         .    ", C_DIM),
    ("  .    .       .   .    .        ", C_DIM),
    ("        ╱▲╲       ╱▲╲           ", C_MASCOT),
    ("       ╱    ╲   ╱    ╲          ", C_MASCOT),
    ("      ╱  ✦   ╲ ╱   ✦  ╲         ", C_MASCOT_HAIR),
    ("     ╱─────────╳─────────╲      ", C_MASCOT),
    ("    ╱   ◉     ││     ◉   ╲     ", C_MASCOT_EYES),
    ("   ╱    ╲_◡╲ ││ ╱◡_╱    ╲     ", C_MASCOT),
    ("  │         ╲││╱          │     ", C_MASCOT),
    ("  │    ◇     ╰╯    ▽      │     ", C_MASCOT_HAIR),
    ("  ╲   ╱╲           ╱╲    ╱      ", C_MASCOT),
    ("   ╲╱   ╲_________╱   ╲╱       ", C_MASCOT),
    ("    ┃  ┌───────────┐  ┃        ", C_MASCOT_HOOD),
    ("    ┃  │  ░░░░░░░  │  ┃        ", C_MASCOT_HOOD),
    ("    ┃  │  ░░░░░░░  │  ┃        ", C_MASCOT_HOOD),
    ("    ┗━━┷━━━━━━━━━━━┷━━┛        ", C_MASCOT_HOOD),
    ("                                 ", C_DIM),
    ("     xiaomeng  ·  terminal      ", C_MASCOT_TAG),
]

MASCOT_SMALL = [
    ("    ╱▲╲   ╱▲╲    ", C_MASCOT),
    ("   ╱ ◉ ╲╱ ◉ ╲   ", C_MASCOT_EYES),
    ("  │  ╲_◡╱  │    ", C_MASCOT),
    ("  ╲  ╱────╲  ╱    ", C_MASCOT_HOOD),
    ("   ┷━━━━━━━━┷    ", C_MASCOT_HOOD),
]

MASCOT_TINY = "(=◉ᆽ◉=)"

SPRITES_OK = False
MOOD_LIST = [
    "idle",
    "happy",
    "thinking",
    "excited",
    "typing",
    "processing",
    "success",
    "error",
    "sleepy",
    "sad",
    "surprised",
    "confused",
]
HB_COLS = HB_ROWS = 0

try:
    from lingmeng_sprites import (
        get_halfblock,
        get_sixel,
        detect_sixel,
        draw_sixel,
        MOOD_LIST as _ML,
        HB_COLS as _HC,
        HB_ROWS as _HR,
    )

    SPRITES_OK = True
    MOOD_LIST = _ML
    HB_COLS, HB_ROWS = _HC, _HR
except ImportError:
    pass

_USE_SIXEL = False


def _init_renderer():
    global _USE_SIXEL
    if SPRITES_OK:
        _USE_SIXEL = detect_sixel()


def _draw_mascot(scr, mood, y, x):
    if not SPRITES_OK:
        return
    if _USE_SIXEL:
        draw_sixel(mood, y + 1, x + 1)
    else:
        lines = get_halfblock(mood)
        H, W = scr.getmaxyx()
        buf = b""
        for i, line in enumerate(lines):
            row = y + i
            if row >= H - 2:
                break
            buf += f"\x1b[{row + 1};{x + 1}H".encode() + line.encode("utf-8")
        if buf:
            try:
                os.write(sys.stdout.fileno(), buf)
            except Exception:
                pass


def _is_sensitive(key: str) -> bool:
    return key.lower() in SENSITIVE_KEYS or any(
        s in key.lower() for s in SENSITIVE_KEYS
    )


def _mask_value(val: str) -> str:
    if not val:
        return "(empty)"
    return SECRET_MASK


def _truncate(s: str, max_len: int) -> str:
    if max_len < 4:
        return s[:max_len]
    if len(s) <= max_len:
        return s
    return s[: max_len - 2] + ".."


def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_DEFAULT, 252, -1)
    curses.init_pair(C_DIM, 242, -1)
    curses.init_pair(C_ACCENT, 117, -1)
    curses.init_pair(C_USER, 117, -1)
    curses.init_pair(C_ASSISTANT, 180, -1)
    curses.init_pair(C_TOOL, 150, -1)
    curses.init_pair(C_SYSTEM, 248, -1)
    curses.init_pair(C_ERROR, 174, -1)
    curses.init_pair(C_SUCCESS, 150, -1)
    curses.init_pair(C_BORDER, 60, -1)
    curses.init_pair(C_HIGHLIGHT, 16, 117)
    curses.init_pair(C_MASKED, 174, -1)
    curses.init_pair(C_BOOL_ON, 150, -1)
    curses.init_pair(C_BOOL_OFF, 174, -1)
    curses.init_pair(C_MASCOT, 180, -1)
    curses.init_pair(C_INPUT_BG, 252, 236)
    curses.init_pair(C_SECTION, 180, -1)
    curses.init_pair(C_FOOTER, 248, 236)
    curses.init_pair(C_FOOTER_KEY, 117, 236)
    curses.init_pair(C_PENDING, 180, -1)
    curses.init_pair(C_MASCOT_EYES, 87, -1)
    curses.init_pair(C_MASCOT_HAIR, 183, -1)
    curses.init_pair(C_MASCOT_HOOD, 245, -1)
    curses.init_pair(C_MASCOT_TAG, 117, -1)
    curses.init_pair(C_BUBBLE_USER, 117, 236)
    curses.init_pair(C_BUBBLE_ASST, 236, 240)
    curses.init_pair(C_BUBBLE_SYSTEM, 248, 235)
    curses.init_pair(C_TAB_ACTIVE, 117, -1)
    curses.init_pair(C_TAB_INACTIVE, 242, -1)
    curses.init_pair(C_SPLASH_TITLE, 183, -1)
    curses.init_pair(C_SPLASH_SUB, 252, -1)
    curses.init_pair(C_SPLASH_DIM, 242, -1)
    curses.init_pair(C_TREE_NODE, 180, -1)
    curses.init_pair(C_TREE_LEAF, 252, -1)
    curses.init_pair(C_SCROLLBAR, 60, -1)


def _safe_addstr(scr, y, x, text, attr=0):
    try:
        scr.addstr(y, x, text, attr)
    except curses.error:
        pass


def _draw_box(scr, y, x, h, w):
    try:
        attr = curses.color_pair(C_BORDER)
        scr.addch(y, x, "┌", attr)
        scr.addch(y, x + w - 1, "┐", attr)
        scr.addch(y + h - 1, x, "└", attr)
        scr.addch(y + h - 1, x + w - 1, "┘", attr)
        for i in range(1, w - 1):
            scr.addch(y, x + i, "─", attr)
            scr.addch(y + h - 1, x + i, "─", attr)
        for i in range(1, h - 1):
            scr.addch(y + i, x, "│", attr)
            scr.addch(y + i, x + w - 1, "│", attr)
    except curses.error:
        pass


def _set_nested(cfg, dotted_key, value):
    keys = dotted_key.split(".")
    d = cfg
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = value


def _get_nested(cfg, dotted_key):
    keys = dotted_key.split(".")
    d = cfg
    for k in keys:
        d = d[k]
    return d


def _parse_value(raw, original):
    if isinstance(original, bool):
        if raw.lower() in ("true", "1", "yes"):
            return True
        elif raw.lower() in ("false", "0", "no"):
            return False
        return None
    elif isinstance(original, int):
        try:
            return int(raw)
        except ValueError:
            return None
    elif isinstance(original, float):
        try:
            return float(raw)
        except ValueError:
            return None
    else:
        return raw


class ConfigTree:
    def __init__(self, config: dict):
        self.root = self._build_tree(config)
        self.flat: List[dict] = []
        self.cursor = 0
        self.scroll = 0
        self._rebuild_flat()

    def _build_tree(self, node, prefix="") -> dict:
        children = []
        if isinstance(node, dict):
            for key, val in sorted(node.items()):
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(val, dict):
                    child = {
                        "kind": "node",
                        "key": key,
                        "full_key": full_key,
                        "expanded": False,
                        "children": [],
                        "value": val,
                    }
                    child["children"] = [self._build_tree(val, full_key)]
                    children.append(child)
                elif isinstance(val, list) and val and isinstance(val[0], dict):
                    child = {
                        "kind": "model_list",
                        "key": key,
                        "full_key": full_key,
                        "value": val,
                    }
                    children.append(child)
                elif isinstance(val, list):
                    child = {
                        "kind": "list",
                        "key": key,
                        "full_key": full_key,
                        "value": val,
                    }
                    children.append(child)
                else:
                    child = {
                        "kind": "leaf",
                        "key": key,
                        "full_key": full_key,
                        "value": val,
                    }
                    children.append(child)
            return {"kind": "root", "children": children}
        return {"kind": "root", "children": []}

    def _rebuild_flat(self):
        self.flat = []
        self._flatten(self.root, 0)

    def _flatten(self, node, depth):
        if node["kind"] == "root":
            for c in node.get("children", []):
                self._flatten(c, depth)
            return
        self.flat.append({"node": node, "depth": depth})
        if node["kind"] == "node" and node.get("expanded"):
            for c in node.get("children", []):
                self._flatten(c, depth + 1)

    def toggle(self, idx):
        if idx < len(self.flat):
            item = self.flat[idx]["node"]
            if item["kind"] == "node":
                item["expanded"] = not item["expanded"]
                self._rebuild_flat()

    def current_node(self):
        if self.cursor < len(self.flat):
            return self.flat[self.cursor]["node"]
        return None

    def clamp_cursor(self):
        if not self.flat:
            self.cursor = 0
            self.scroll = 0
            return
        self.cursor = max(0, min(self.cursor, len(self.flat) - 1))


class ChatEngine:
    def __init__(self, config: dict):
        self._config = config
        self._db_path = str(Path(config.get("data_dir", "./data")) / "qq_bot.db")
        self._soul_path = Path(config.get("persona_path", "./data/persona/SOUL.md"))
        self._data_dir = Path(config.get("data_dir", "./data"))
        self._owner_qq = config.get("owner_qq", 0)
        self._session_key = f"private:{self._owner_qq}"
        self._router = None
        self._initialized = False
        self._init_error = None
        self._generating = False
        self._streaming_text = ""
        self._streaming_done = threading.Event()
        self._ModelLayer = self._ModelRole = self._PermLevel = None
        self._TOOL_SCHEMAS = None
        self._LOCAL_OK_TOOLS = {"search_memory", "recall_conversations"}
        self._WRITE_TOOLS = {"write_file", "add_memory", "update_soul"}
        self._ROUTER_PROMPT = (
            "You are a routing assistant. Read the user message and output exactly one word:\n"
            "- CLOUD  → real-time info, web search, complex reasoning, math, long writing\n"
            "- LOCAL  → casual chat, greetings, simple opinions\n"
            "Output only one word: LOCAL or CLOUD"
        )

    def initialize(self):
        try:
            from core.model_layer import (
                ModelLayer,
                ModelRole,
                ModelLayerRouter,
                ModelEndpoint,
                ModelProvider,
            )
            from core.qq.tools import QQToolExecutor, TOOL_SCHEMAS
            from core.qq.permissions import PermLevel

            router = ModelLayerRouter()
            for m in self._config.get("models", []):
                if not m.get("enabled", True):
                    continue
                # 解析 provider：显式配置优先，否则 None 走自动检测
                provider_raw = m.get("provider")
                provider = None
                if provider_raw:
                    try:
                        provider = ModelProvider(provider_raw)
                    except ValueError:
                        pass
                endpoint = ModelEndpoint(
                    model_id=m.get("model_id", m["model_name"]),
                    layer=ModelLayer(m.get("layer", "basic")),
                    role=ModelRole(m.get("role", "chat")),
                    endpoint=m["endpoint"],
                    model_name=m["model_name"],
                    api_key=m.get("api_key"),
                    max_tokens=m.get("max_tokens", 4096),
                    temperature=m.get("temperature", 0.85),
                    proxy=m.get("proxy"),
                    num_ctx=m.get("num_ctx"),
                    provider=provider,
                )
                router.register_model(endpoint)
            self._router = router
            self._TOOL_SCHEMAS = TOOL_SCHEMAS
            self._ModelLayer = ModelLayer
            self._ModelRole = ModelRole
            self._PermLevel = PermLevel
            self._initialized = True
        except Exception as e:
            self._init_error = str(e)
            self._initialized = False

    def _load_recent_messages(self, limit=30):
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT role,content FROM messages WHERE session_key=? ORDER BY id DESC LIMIT ?",
                (self._session_key, limit),
            ).fetchall()
            conn.close()
            return list(reversed([{"role": r[0], "content": r[1]} for r in rows]))
        except Exception:
            return []

    def _save_turn(self, user_text, assistant_text):
        now = datetime.now().isoformat()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO messages(session_key,role,sender_qq,sender_name,content,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (self._session_key, "user", self._owner_qq, "Owner", user_text, now),
            )
            conn.execute(
                "INSERT INTO messages(session_key,role,sender_qq,sender_name,content,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (self._session_key, "assistant", 0, "小萌", assistant_text, now),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _read_soul(self) -> str:
        try:
            return self._soul_path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _build_system_prompt(self, local=False):
        soul = self._read_soul()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = f"当前场景：终端对话\n当前时间：{now}\n"
        if soul:
            prompt += f"\n{soul}\n"
        if not local:
            prompt += "\n你可以使用工具搜索、记忆、读写文件。回复使用中文。\n"
        else:
            prompt += "\n简短回复，1-3句话。\n"
        return prompt

    def chat_stream(self, user_text):
        self._generating = True
        self._streaming_text = ""
        self._streaming_done.clear()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._chat_async(user_text))
            finally:
                loop.close()
                self._generating = False
                self._streaming_done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    async def _chat_async(self, user_text):
        if not self._initialized:
            self._streaming_text = f"初始化失败: {self._init_error}"
            return
        from core.qq.tools import QQToolExecutor

        try:
            local_adapter = self._router.get_available_adapter(
                self._ModelLayer.BASIC, self._ModelRole.CHAT
            )
            cloud_adapter = self._router.get_available_adapter(
                self._ModelLayer.BRAIN, self._ModelRole.REASONING
            )
            pro_adapter = self._router.get_available_adapter(
                self._ModelLayer.PRO, self._ModelRole.REASONING
            )
            router_adapter = self._router.get_available_adapter(
                self._ModelLayer.BASIC, self._ModelRole.ROUTER
            )
            if local_adapter is None and cloud_adapter is None:
                self._streaming_text = "没有可用的模型"
                return
            cfg = self._config
            pro_keywords = cfg.get("pro_trigger_keywords", [])
            cloud_keywords = cfg.get("cloud_trigger", {}).get("keywords", [])
            cloud_min_chars = cfg.get("cloud_trigger", {}).get("min_chars", 200)
            use_pro = bool(
                pro_adapter
                and pro_keywords
                and any(kw in user_text for kw in pro_keywords)
            )
            use_cloud = False
            route_label = "LOCAL"
            if not use_pro and (cloud_adapter or router_adapter):
                cloud_hint = bool(
                    cloud_keywords and any(kw in user_text for kw in cloud_keywords)
                )
                cloud_hint = cloud_hint or bool(
                    cloud_min_chars and len(user_text) >= cloud_min_chars
                )
                if router_adapter:
                    try:
                        rd = await asyncio.wait_for(
                            router_adapter.chat(
                                [{"role": "user", "content": user_text}],
                                system_prompt=self._ROUTER_PROMPT,
                                max_tokens=20,
                            ),
                            timeout=cfg.get("llm_timeouts", {}).get("routing", 15),
                        )
                        decision = re.sub(
                            r"usse.*?ee", "", rd.content or "", flags=re.DOTALL
                        ).upper()
                        use_cloud = "CLOUD" in decision or cloud_hint
                    except Exception:
                        use_cloud = cloud_hint
                else:
                    use_cloud = cloud_hint
            if use_pro:
                active_adapter, timeout, route_label = (
                    pro_adapter,
                    cfg.get("llm_timeouts", {}).get("pro", 300),
                    "PRO",
                )
            elif use_cloud:
                active_adapter, timeout, route_label = (
                    cloud_adapter,
                    cfg.get("llm_timeouts", {}).get("cloud", 180),
                    "CLOUD",
                )
            else:
                active_adapter, timeout, route_label = (
                    local_adapter or cloud_adapter,
                    cfg.get("llm_timeouts", {}).get("local", 90),
                    "LOCAL",
                )
            max_tokens = getattr(
                getattr(active_adapter, "endpoint", None), "max_tokens", 4096
            )
            is_local = active_adapter is local_adapter
            self._streaming_text = f"[{route_label}] "
            tool_executor = QQToolExecutor(
                db_path=self._db_path,
                soul_path=self._soul_path,
                data_dir=self._data_dir,
                session_key=self._session_key,
                sender_qq=self._owner_qq,
                level=self._PermLevel.OWNER,
                identity="terminal_owner",
                proxy=cfg.get("web_search_proxy", ""),
            )
            messages = self._load_recent_messages(
                cfg.get("memory", {}).get("recent_messages_limit", 30)
            )
            messages.append({"role": "user", "content": user_text})
            system = self._build_system_prompt(local=is_local)
            active_tools = (
                [
                    t
                    for t in self._TOOL_SCHEMAS
                    if t.get("function", {}).get("name") in self._LOCAL_OK_TOOLS
                ]
                if is_local
                else self._TOOL_SCHEMAS
            )
            response = await asyncio.wait_for(
                active_adapter.chat(
                    messages,
                    system_prompt=system,
                    tools=active_tools,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )
            max_loops = cfg.get("loop_limits", {}).get("max_tool_loops", 10)
            max_searches = cfg.get("loop_limits", {}).get(
                "max_searches_before_write", 4
            )
            loop_msgs = list(messages)
            search_count = 0
            wrote_something = False
            for loop_i in range(max_loops):
                if not response.tool_calls:
                    break
                asst_msg = {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": tc.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(
                                    tc.get("arguments", {}), ensure_ascii=False
                                ),
                            },
                        }
                        for i, tc in enumerate(response.tool_calls)
                    ],
                }
                if response.reasoning_content:
                    asst_msg["reasoning_content"] = response.reasoning_content
                loop_msgs.append(asst_msg)
                for tc in response.tool_calls:
                    name, args = tc.get("name", ""), tc.get("arguments", {})
                    if name == "web_search":
                        search_count += 1
                    elif name in self._WRITE_TOOLS:
                        wrote_something = True
                    self._streaming_text += f"\n  > {name}({_truncate(json.dumps(args, ensure_ascii=False), 40)})"
                    result = await tool_executor.execute(name, args)
                    self._streaming_text += f"\n    {_truncate(result, 60)}"
                    loop_msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": result,
                        }
                    )
                if search_count >= max_searches and not wrote_something:
                    loop_msgs.append(
                        {
                            "role": "user",
                            "content": "【系统】你已经搜索了足够多的资料，现在必须立刻调用 write_file 或 add_memory 保存结果。",
                        }
                    )
                self._streaming_text += f"\n  [loop {loop_i + 1}/{max_loops}]"
                response = await asyncio.wait_for(
                    active_adapter.chat(
                        loop_msgs,
                        system_prompt=system,
                        tools=active_tools,
                        max_tokens=max_tokens,
                    ),
                    timeout=timeout,
                )
            final_text = response.content or ""
            self._streaming_text = final_text
            self._save_turn(user_text, final_text)
        except Exception as e:
            self._streaming_text = f"Error: {e}"


class SplashScene:
    def __init__(self):
        self.frame = 0
        self.total_frames = 50
        self.done = False
        self.info_lines = [
            ("LingMeng", C_SPLASH_TITLE),
            ("terminal mascot · server spirit", C_SPLASH_SUB),
            ("", C_SPLASH_DIM),
            ("✿ Name   : LingMeng", C_SPLASH_SUB),
            ("✿ Role   : AI Maid · Server Spirit", C_SPLASH_SUB),
            ("✿ Born   : Soul.md", C_SPLASH_SUB),
            ("✿ Likes  : Ave Mujica / 魔法少女 / 音乐", C_SPLASH_SUB),
            ("✿ Code   : love_owner", C_SPLASH_SUB),
            ("✿ Trait  : gentle / loyal / adorable", C_SPLASH_SUB),
            ("✿ Mission: protect owner, accompany always.", C_SPLASH_SUB),
            ("", C_SPLASH_DIM),
            ("", C_SPLASH_DIM),
            ("> owner_detected", C_ACCENT),
            ("> protecting...", C_DIM),
            ("> love_owner", C_ACCENT),
            ("> stay_with_you", C_ACCENT),
            ("> _", C_DIM),
            ("", C_SPLASH_DIM),
            ("Press any key to enter...", C_SPLASH_DIM),
        ]

    def draw(self, scr, max_y, max_x):
        scr.erase()
        progress = min(1.0, self.frame / self.total_frames)
        visible_info = int(len(self.info_lines) * progress)

        cx = max_x // 2
        cy = max_y // 2

        if SPRITES_OK:
            if progress > 0.1:
                pass
        else:
            mascot_start = int(len(MASCOT_FULL) * max(0, (progress - 0.1) / 0.9))
            for i in range(mascot_start):
                line_text, line_color = MASCOT_FULL[i]
                _safe_addstr(
                    scr, cy - 10 + i, cx - 18, line_text, curses.color_pair(line_color)
                )

        info_x = cx - 20
        for i in range(min(visible_info, len(self.info_lines))):
            txt, col = self.info_lines[i]
            alpha = min(1.0, (visible_info - i) / 3.0)
            if alpha >= 1.0:
                _safe_addstr(scr, cy - 10 + i, info_x, txt, curses.color_pair(col))
            elif alpha > 0:
                dim_txt = txt[: int(len(txt) * alpha)]
                _safe_addstr(scr, cy - 10 + i, info_x, dim_txt, curses.color_pair(col))

        bar_w = 30
        bar_x = cx - bar_w // 2
        bar_y = cy + 10
        filled = int(bar_w * progress)
        _safe_addstr(scr, bar_y, bar_x, "━" * filled, curses.color_pair(C_ACCENT))
        _safe_addstr(
            scr, bar_y, bar_x + filled, "─" * (bar_w - filled), curses.color_pair(C_DIM)
        )

        pct = f"{int(progress * 100)}%"
        _safe_addstr(scr, bar_y + 1, cx - 2, pct, curses.color_pair(C_DIM))

        scr.refresh()

        if SPRITES_OK and progress > 0.1:
            _draw_mascot(scr, "idle", cy - HB_ROWS // 2, cx - HB_COLS // 2)

    def tick(self):
        self.frame += 1
        if self.frame > self.total_frames:
            self.done = True


class XiaoMengTUI:
    TAB_CHAT = 0
    TAB_CONFIG = 1
    TAB_STATUS = 2
    TAB_HELP = 3
    TAB_NAMES = [" chat ", " config ", " status ", " help "]

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.config = self._load_config()
        self.original = copy.deepcopy(self.config)
        self.dirty = False

        self.active_tab = self.TAB_CHAT
        self.transition_frame = -1
        self.transition_from = -1

        self.chat_engine = ChatEngine(self.config)
        self.chat_messages: List[Dict] = []
        self.chat_scroll = 0
        self.input_text = ""
        self.input_active = False

        self.config_tree = ConfigTree(self.config)
        self.status_scroll = 0
        self.help_scroll = 0

        self.mood_idx = 0
        self.show_mascot = True

        self.status_msg = ""
        self.status_timer = 0
        self._esc_buffer = False
        self._esc_timer = 0

        self.left_panel_w = 30
        self.startup = SplashScene()

        self._mascot_draw_queue: List[Tuple[str, int, int]] = []

    def _load_config(self) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}

    def _save_config(self) -> bool:
        try:
            backup = CONFIG_PATH.with_suffix(".json.bak")
            if CONFIG_PATH.exists():
                shutil.copy2(CONFIG_PATH, backup)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
                f.write("\n")
            self.dirty = False
            self.original = copy.deepcopy(self.config)
            self._set_status("saved")
            return True
        except Exception as e:
            self._set_status(f"save failed: {e}")
            return False

    def _set_status(self, msg):
        self.status_msg = msg
        self.status_timer = 40

    def run(self):
        self.stdscr.nodelay(True)
        self.stdscr.timeout(80)
        curses.curs_set(0)
        self.chat_engine.initialize()
        _init_renderer()

        while self.startup.frame <= self.startup.total_frames:
            self.startup.draw(self.stdscr, *self.stdscr.getmaxyx())
            ch = self.stdscr.getch()
            if ch != -1:
                break
            self.startup.tick()
            time.sleep(0.02)

        while True:
            self._draw()
            ch = self.stdscr.getch()
            if ch == -1:
                if self._esc_buffer:
                    self._esc_timer -= 1
                    if self._esc_timer <= 0:
                        self._esc_buffer = False
                if self.status_timer > 0:
                    self.status_timer -= 1
                    if self.status_timer == 0:
                        self.status_msg = ""
                if self.transition_frame >= 0:
                    self.transition_frame -= 1
                continue
            self._handle_key(ch)

    def _handle_key(self, ch):
        if ch == 27:
            self._esc_buffer = True
            self._esc_timer = 3
            return
        if self._esc_buffer:
            self._esc_buffer = False
            if ch in (ord("["), ord("O")) or (65 <= ch <= 122):
                return

        if self.input_active:
            self._handle_input(ch)
            return

        if ch == 9:
            self._switch_tab()
            return

        if ch == ord("q"):
            if self.dirty:
                self._set_status("unsaved changes! Q=force quit")
            else:
                raise SystemExit(0)
        elif ch == ord("Q"):
            raise SystemExit(0)

        if self.active_tab == self.TAB_CHAT:
            self._handle_chat_key(ch)
        elif self.active_tab == self.TAB_CONFIG:
            self._handle_config_key(ch)
        elif self.active_tab == self.TAB_STATUS:
            self._handle_status_key(ch)
        elif self.active_tab == self.TAB_HELP:
            self._handle_help_key(ch)

    def _switch_tab(self):
        old = self.active_tab
        self.active_tab = (self.active_tab + 1) % 4
        self.transition_frame = 6
        self.transition_from = old

    def _handle_input(self, ch):
        if ch == 27:
            self.input_active = False
            curses.curs_set(0)
        elif ch in (127, 8, curses.KEY_BACKSPACE):
            self.input_text = self.input_text[:-1]
        elif ch == ord("\n"):
            text = self.input_text.strip()
            self.input_active = False
            curses.curs_set(0)
            if not text:
                return
            self._send_chat(text)
        elif 32 <= ch < 127:
            self.input_text += chr(ch)

    def _handle_chat_key(self, ch):
        if ch in (curses.KEY_UP, ord("k")):
            self.chat_scroll = max(0, self.chat_scroll - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.chat_scroll += 1
        elif ch == curses.KEY_PPAGE:
            my, _ = self.stdscr.getmaxyx()
            self.chat_scroll = max(0, self.chat_scroll - my + 7)
        elif ch == curses.KEY_NPAGE:
            my, _ = self.stdscr.getmaxyx()
            self.chat_scroll += my - 7
        elif ch in (ord("i"), ord("\n")):
            self.input_active = True
            self.input_text = ""
            curses.curs_set(1)
        elif ch == 9:
            self._switch_tab()
        elif ch == ord("s"):
            self._save_config()

    def _handle_config_key(self, ch):
        tree = self.config_tree
        if ch in (curses.KEY_UP, ord("k")):
            tree.cursor = max(0, tree.cursor - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            tree.clamp_cursor()
            tree.cursor = min(len(tree.flat) - 1, tree.cursor + 1)
        elif ch == curses.KEY_PPAGE:
            tree.cursor = max(0, tree.cursor - 10)
        elif ch == curses.KEY_NPAGE:
            tree.clamp_cursor()
            tree.cursor = min(len(tree.flat) - 1, tree.cursor + 10)
        elif ch in (ord("\n"), ord("e")):
            node = tree.current_node()
            if node is None:
                return
            if node["kind"] == "node":
                tree.toggle(tree.cursor)
            elif node["kind"] == "leaf":
                self._edit_leaf(node)
            elif node["kind"] == "list":
                self._edit_list(node)
            elif node["kind"] == "model_list":
                self._edit_model_list(node)
        elif ch == ord("s"):
            self._save_config()

    def _handle_status_key(self, ch):
        if ch in (curses.KEY_UP, ord("k")):
            self.status_scroll = max(0, self.status_scroll - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.status_scroll += 1
        elif ch == ord("r"):
            pass

    def _handle_help_key(self, ch):
        if ch in (curses.KEY_UP, ord("k")):
            self.help_scroll = max(0, self.help_scroll - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.help_scroll += 1

    def _send_chat(self, text):
        self.chat_messages.append({"role": "user", "content": text})
        self.show_mascot = False
        self.chat_engine.chat_stream(text)

    def _edit_leaf(self, node):
        fk, fv = node["key"], node["value"]
        if isinstance(fv, bool):
            _set_nested(self.config, node["full_key"], not fv)
            self.dirty = True
            self.config_tree = ConfigTree(self.config)
        elif _is_sensitive(fk):
            self._popup_edit(node["full_key"], fk, fv, sensitive=True)
        else:
            self._popup_edit(node["full_key"], fk, fv, sensitive=False)

    def _popup_edit(self, full_key, key, val, sensitive=False):
        curses.curs_set(1)
        my, mx = self.stdscr.getmaxyx()
        pw, ph = min(56, mx - 4), (6 if sensitive else 7)
        py, px = my // 2 - ph // 2, mx // 2 - pw // 2
        win = curses.newwin(ph, pw, py, px)
        _draw_box(win, 0, 0, ph, pw)
        label = "secret:" if sensitive else full_key
        _safe_addstr(
            win,
            1,
            2,
            label,
            curses.color_pair(C_MASKED if sensitive else C_ACCENT) | curses.A_BOLD,
        )
        if not sensitive:
            _safe_addstr(
                win,
                2,
                2,
                f"current: {_truncate(str(val), pw - 14)}",
                curses.color_pair(C_DIM),
            )
        row = 3 if sensitive else 4
        _safe_addstr(win, row, 2, "new: ", curses.color_pair(C_DIM))
        win.refresh()
        iw = win.derwin(1, pw - 12, row, 7)
        curses.echo()
        try:
            raw = iw.getstr().decode("utf-8").strip()
        except Exception:
            raw = None
        curses.noecho()
        curses.curs_set(0)
        if raw is not None and raw != "":
            new_val = _parse_value(raw, val)
            if new_val is not None:
                _set_nested(self.config, full_key, new_val)
                self.dirty = True
        self.config_tree = ConfigTree(self.config)

    def _edit_list(self, node):
        val = node["value"]
        curses.curs_set(1)
        my, mx = self.stdscr.getmaxyx()
        ph = min(14, my - 4)
        pw = min(56, mx - 4)
        py, px = my // 2 - ph // 2, mx // 2 - pw // 2
        win = curses.newwin(ph, pw, py, px)
        _draw_box(win, 0, 0, ph, pw)
        _safe_addstr(
            win, 1, 2, node["full_key"], curses.color_pair(C_ACCENT) | curses.A_BOLD
        )
        for i, v in enumerate(val):
            if i + 3 >= ph - 2:
                _safe_addstr(
                    win, i + 3, 4, f"... ({len(val)} items)", curses.color_pair(C_DIM)
                )
                break
            _safe_addstr(win, i + 3, 4, f"[{i}] {v}", curses.color_pair(C_DEFAULT))
        _safe_addstr(
            win, ph - 2, 4, "add X / del N / enter=cancel", curses.color_pair(C_DIM)
        )
        win.refresh()
        iw = win.derwin(1, pw - 8, ph - 3, 4)
        curses.echo()
        try:
            raw = iw.getstr().decode("utf-8").strip()
        except Exception:
            raw = ""
        curses.noecho()
        curses.curs_set(0)
        if raw.startswith("add "):
            val.append(raw[4:].strip())
            self.dirty = True
        elif raw.startswith("del "):
            try:
                val.pop(int(raw[4:].strip()))
                self.dirty = True
            except (ValueError, IndexError):
                pass
        self.config_tree = ConfigTree(self.config)

    def _edit_model_list(self, node):
        models = node["value"]
        mi = 0
        while True:
            curses.curs_set(0)
            my, mx = self.stdscr.getmaxyx()
            ph = min(my - 4, 20)
            pw = min(mx - 4, 72)
            py, px = my // 2 - ph // 2, mx // 2 - pw // 2
            win = curses.newwin(ph, pw, py, px)
            _draw_box(win, 0, 0, ph, pw)
            _safe_addstr(
                win,
                1,
                2,
                f" models [{len(models)}]",
                curses.color_pair(C_SECTION) | curses.A_BOLD,
            )
            _safe_addstr(
                win, 1, pw - 22, "h/l switch  n new  x del", curses.color_pair(C_DIM)
            )
            if not models:
                _safe_addstr(win, 3, 2, "No models", curses.color_pair(C_DIM))
            else:
                mi = min(mi, len(models) - 1)
                m = models[mi]
                dot = "+" if m.get("enabled", True) else "-"
                _safe_addstr(
                    win,
                    3,
                    2,
                    f"{dot} {m.get('model_id', '?')}",
                    curses.color_pair(C_ACCENT) | curses.A_BOLD,
                )
                _safe_addstr(
                    win,
                    3,
                    20,
                    f"[{mi + 1}/{len(models)}] layer={m.get('layer', '?')} role={m.get('role', '?')}",
                    curses.color_pair(C_DIM),
                )
                keys = list(m.keys())
                for fi, fk in enumerate(keys):
                    if fi + 5 >= ph - 1:
                        break
                    fv = m[fk]
                    cur = fi == 0
                    pfx = "> " if cur else "  "
                    if _is_sensitive(fk):
                        vd = _mask_value(str(fv))
                        vc = C_MASKED
                    elif isinstance(fv, bool):
                        vd = "on" if fv else "off"
                        vc = C_BOOL_ON if fv else C_BOOL_OFF
                    else:
                        vd = _truncate(str(fv), pw - 30)
                        vc = C_DEFAULT
                    _safe_addstr(
                        win,
                        5 + fi,
                        2,
                        f"{pfx}{fk}:",
                        curses.color_pair(C_DEFAULT) | (curses.A_BOLD if cur else 0),
                    )
                    _safe_addstr(
                        win,
                        5 + fi,
                        2 + len(pfx) + len(fk) + 2,
                        vd,
                        curses.color_pair(vc),
                    )
            win.refresh()
            ch = self.stdscr.getch()
            if ch == 27:
                break
            elif ch in (curses.KEY_LEFT, ord("h")):
                mi = max(0, mi - 1)
            elif ch in (curses.KEY_RIGHT, ord("l")):
                mi = min(len(models) - 1, mi + 1)
            elif ch in (ord("\n"), ord("e")) and models:
                self._edit_model_field(models[mi])
            elif ch == ord("n"):
                models.append(
                    {
                        "model_id": "new-model",
                        "layer": "basic",
                        "role": "chat",
                        "model_name": "",
                        "endpoint": "",
                        "api_key": "",
                        "max_tokens": 2048,
                        "temperature": 0.7,
                        "enabled": True,
                        "priority": 1,
                    }
                )
                self.dirty = True
                mi = len(models) - 1
            elif ch == ord("x") and len(models) > 1:
                models.pop(mi)
                self.dirty = True
                mi = min(mi, len(models) - 1)
        self.config_tree = ConfigTree(self.config)

    def _edit_model_field(self, model):
        keys = list(model.keys())
        if not keys:
            return
        fk = keys[0]
        fv = model[fk]
        if _is_sensitive(fk):
            self._popup_model_edit(model, fk, sensitive=True)
        elif isinstance(fv, bool):
            model[fk] = not fv
            self.dirty = True
        else:
            self._popup_model_edit(model, fk, sensitive=False)

    def _popup_model_edit(self, model, fk, sensitive=False):
        curses.curs_set(1)
        my, mx = self.stdscr.getmaxyx()
        pw, ph = min(50, mx - 4), 6
        py, px = my // 2 - ph // 2, mx // 2 - pw // 2
        win = curses.newwin(ph, pw, py, px)
        _draw_box(win, 0, 0, ph, pw)
        lbl = "secret:" if sensitive else fk
        _safe_addstr(
            win,
            1,
            2,
            lbl,
            curses.color_pair(C_MASKED if sensitive else C_ACCENT) | curses.A_BOLD,
        )
        if not sensitive:
            _safe_addstr(win, 2, 2, f"current: {model[fk]}", curses.color_pair(C_DIM))
        _safe_addstr(win, 4, 2, "new: ", curses.color_pair(C_DIM))
        win.refresh()
        iw = win.derwin(1, pw - 12, 4, 7)
        curses.echo()
        try:
            raw = iw.getstr().decode("utf-8").strip()
        except Exception:
            raw = None
        curses.noecho()
        curses.curs_set(0)
        if raw is not None and raw != "":
            nv = _parse_value(raw, model[fk])
            if nv is not None:
                model[fk] = nv
                self.dirty = True

    # ══════════════════════════════════════════════════════════════
    # 绘制
    # ══════════════════════════════════════════════════════════════

    def _draw(self):
        self._mascot_draw_queue = []
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()
        lpw = min(max(28, self.left_panel_w), max_x // 3)
        rpx = lpw + 1
        rpw = max_x - rpx

        self._draw_header(max_y, max_x)
        self._draw_left_panel(2, 0, max_y - 4, lpw, max_y, max_x)
        self._draw_tab_bar(2, rpx, rpw)
        content_top = 3
        content_h = max_y - content_top - 2

        if self.active_tab == self.TAB_CHAT:
            self._draw_chat(content_top, rpx, content_h, rpw, max_y, max_x)
        elif self.active_tab == self.TAB_CONFIG:
            self._draw_config(content_top, rpx, content_h, rpw, max_y, max_x)
        elif self.active_tab == self.TAB_STATUS:
            self._draw_status(content_top, rpx, content_h, rpw, max_y, max_x)
        elif self.active_tab == self.TAB_HELP:
            self._draw_help(content_top, rpx, content_h, rpw, max_y, max_x)

        self._draw_footer(max_y, max_x)
        self.stdscr.refresh()

        if self._mascot_draw_queue:
            for mood, my, mx in self._mascot_draw_queue:
                _draw_mascot(self.stdscr, mood, my, mx)

    def _draw_header(self, max_y, max_x):
        header = f" {MASCOT_TINY} LingMeng "
        _safe_addstr(
            self.stdscr, 0, 1, header, curses.color_pair(C_ACCENT) | curses.A_BOLD
        )
        if self.dirty:
            _safe_addstr(
                self.stdscr, 0, 1 + len(header), " [modified]", curses.color_pair(C_DIM)
            )
        now = datetime.now().strftime("%H:%M:%S")
        _safe_addstr(
            self.stdscr, 0, max_x - len(now) - 2, now, curses.color_pair(C_DIM)
        )
        self._draw_hline(self.stdscr, 1, 0, max_x)

    def _draw_left_panel(self, top_y, left_x, h, w, max_y, max_x):
        _draw_box(self.stdscr, top_y, left_x, h, w)

        if SPRITES_OK:
            mood = (
                MOOD_LIST[self.mood_idx] if self.mood_idx < len(MOOD_LIST) else "idle"
            )
            mx = left_x + (w - HB_COLS) // 2
            my = top_y + 2
            self._mascot_draw_queue.append((mood, my, mx))
            mascot_h = HB_ROWS + 1
        else:
            mascot_h = min(h - 10, len(MASCOT_SMALL))
            for i in range(mascot_h):
                lt, lc = MASCOT_SMALL[i]
                _safe_addstr(
                    self.stdscr,
                    top_y + 1 + i,
                    left_x + (w - len(lt)) // 2,
                    lt,
                    curses.color_pair(lc),
                )

        info_y = top_y + mascot_h + 2
        info_lines = [
            (C_ACCENT, " LingMeng"),
            (C_DIM, " terminal spirit"),
            (C_DIM, ""),
            (
                C_SUCCESS,
                " ● running"
                if self.chat_engine._initialized
                else (C_ERROR, " ✗ error"),
            ),
            (C_DIM, ""),
            (C_DIM, f" mood: {MOOD_LIST[self.mood_idx]}"),
            (C_DIM, f" tab: {self.TAB_NAMES[self.active_tab].strip()}"),
            (C_DIM, ""),
            (C_DIM, " ──── keys ────"),
            (C_DIM, " Tab  switch"),
            (C_DIM, " i    input"),
            (C_DIM, " j/k  scroll"),
            (C_DIM, " q    quit"),
        ]
        for i, (cp, txt) in enumerate(info_lines):
            ry = info_y + i
            if ry >= top_y + h - 1:
                break
            _safe_addstr(self.stdscr, ry, left_x + 2, txt, curses.color_pair(cp))

    def _draw_tab_bar(self, y, x, w):
        tx = x + 1
        for i, name in enumerate(self.TAB_NAMES):
            is_active = i == self.active_tab
            cp = C_TAB_ACTIVE if is_active else C_TAB_INACTIVE
            attr = curses.A_BOLD if is_active else 0
            if is_active:
                _safe_addstr(self.stdscr, y, tx - 1, "▸", curses.color_pair(cp) | attr)
            _safe_addstr(self.stdscr, y, tx, name, curses.color_pair(cp) | attr)
            tx += len(name) + 2
        self._draw_hline(self.stdscr, y + 1, x, w)

    def _draw_chat(self, top_y, left_x, h, w, max_y, max_x):
        display_lines = []

        if self.show_mascot and not self.chat_messages:
            if SPRITES_OK:
                mood = (
                    MOOD_LIST[self.mood_idx]
                    if self.mood_idx < len(MOOD_LIST)
                    else "idle"
                )
                mx = left_x + (w - HB_COLS) // 2
                my = top_y + (h - HB_ROWS) // 2 - 2
                self._mascot_draw_queue.append((mood, my, mx))
                hint_y = my + HB_ROWS + 1
                _safe_addstr(
                    self.stdscr,
                    hint_y,
                    left_x + (w - 34) // 2,
                    "Press i or Enter to start chatting",
                    curses.color_pair(C_DIM),
                )
                _safe_addstr(
                    self.stdscr,
                    hint_y + 1,
                    left_x + (w - 22) // 2,
                    "Tab to switch panels",
                    curses.color_pair(C_DIM),
                )
            else:
                for lt, lc in MASCOT_FULL:
                    display_lines.append(("mascot_line", lt, lc))
                display_lines.append(("dim", ""))
                display_lines.append(("dim", "  Press i or Enter to start chatting"))
                display_lines.append(("dim", "  Tab to switch panels"))
        else:
            all_msgs = list(self.chat_messages)
            if self.chat_engine._generating:
                all_msgs.append(
                    {
                        "role": "assistant",
                        "content": self.chat_engine._streaming_text + " ...",
                    }
                )

            for msg in all_msgs:
                role = msg.get("role", "system")
                content = msg.get("content", "")
                mlw = max(w - 6, 8)
                if role == "user":
                    for rl in content.split("\n"):
                        while len(rl) > mlw:
                            display_lines.append(("bubble_user", rl[:mlw]))
                            rl = rl[mlw:]
                        display_lines.append(("bubble_user", rl))
                    display_lines.append(("", ""))
                elif role == "assistant":
                    for rl in content.split("\n"):
                        while len(rl) > mlw:
                            display_lines.append(("bubble_asst", rl[:mlw]))
                            rl = rl[mlw:]
                        display_lines.append(("bubble_asst", rl))
                    display_lines.append(("", ""))
                elif role == "system":
                    for rl in content.split("\n"):
                        while len(rl) > mlw:
                            display_lines.append(("bubble_sys", rl[:mlw]))
                            rl = rl[mlw:]
                        display_lines.append(("bubble_sys", rl))
                    display_lines.append(("", ""))

        if not display_lines:
            if self.input_active:
                prompt = "❯ "
                _safe_addstr(
                    self.stdscr,
                    top_y + h,
                    left_x,
                    prompt,
                    curses.color_pair(C_ACCENT) | curses.A_BOLD,
                )
                di = self.input_text
                if len(di) > w - 6:
                    di = di[-(w - 6) :]
                _safe_addstr(
                    self.stdscr,
                    top_y + h,
                    left_x + len(prompt),
                    di + "_",
                    curses.color_pair(C_DEFAULT),
                )
            else:
                state = (
                    "generating..."
                    if self.chat_engine._generating
                    else f"{MASCOT_TINY} idle"
                )
                sc = C_PENDING if self.chat_engine._generating else C_DIM
                _safe_addstr(
                    self.stdscr, top_y + h, left_x, f" {state}", curses.color_pair(sc)
                )
            return

        total = len(display_lines)
        if self.chat_scroll > total - h + 1:
            self.chat_scroll = max(0, total - h + 1)

        for i in range(h):
            di = i + self.chat_scroll
            if di >= total:
                break
            entry = display_lines[di]
            ek = entry[0]
            ey = top_y + i
            ex = left_x + 2
            if ek == "mascot_line":
                et, ec = entry[1], entry[2]
                _safe_addstr(
                    self.stdscr,
                    ey,
                    left_x + (w - len(et)) // 2,
                    et,
                    curses.color_pair(ec),
                )
            elif ek == "bubble_user":
                self._draw_bubble(
                    ey, ex, entry[1], w - 4, C_BUBBLE_USER, align_right=True
                )
            elif ek == "bubble_asst":
                self._draw_bubble(
                    ey, ex, entry[1], w - 4, C_BUBBLE_ASST, align_right=False
                )
            elif ek == "bubble_sys":
                self._draw_bubble(
                    ey, ex, entry[1], w - 4, C_BUBBLE_SYSTEM, align_right=False
                )
            elif ek == "dim":
                _safe_addstr(self.stdscr, ey, ex, entry[1], curses.color_pair(C_DIM))
            elif ek == "":
                pass

        if self.input_active:
            prompt = "❯ "
            _safe_addstr(
                self.stdscr,
                top_y + h,
                left_x,
                prompt,
                curses.color_pair(C_ACCENT) | curses.A_BOLD,
            )
            di = self.input_text
            if len(di) > w - 6:
                di = di[-(w - 6) :]
            _safe_addstr(
                self.stdscr,
                top_y + h,
                left_x + len(prompt),
                di + "_",
                curses.color_pair(C_DEFAULT),
            )
        else:
            state = (
                "generating..."
                if self.chat_engine._generating
                else f"{MASCOT_TINY} idle"
            )
            sc = C_PENDING if self.chat_engine._generating else C_DIM
            _safe_addstr(
                self.stdscr, top_y + h, left_x, f" {state}", curses.color_pair(sc)
            )

    def _draw_bubble(self, y, x, text, max_w, color, align_right=False):
        tw = min(len(text), max_w)
        pad = max_w - tw
        bx = x + (pad if align_right else 0)
        bw = tw + 2
        bg_cp = curses.color_pair(color)
        try:
            self.stdscr.addch(y, bx, " ", bg_cp)
            self.stdscr.addstr(y, bx + 1, text[:tw], bg_cp)
            self.stdscr.addch(y, bx + bw - 1, " ", bg_cp)
        except curses.error:
            pass

    def _draw_config(self, top_y, left_x, h, w, max_y, max_x):
        tree = self.config_tree
        tree.clamp_cursor()
        visible_h = h - 1

        if tree.cursor < tree.scroll:
            tree.scroll = tree.cursor
        elif tree.cursor >= tree.scroll + visible_h:
            tree.scroll = tree.cursor - visible_h + 1

        for i in range(visible_h):
            di = i + tree.scroll
            if di >= len(tree.flat):
                break
            item = tree.flat[di]
            node = item["node"]
            depth = item["depth"]
            is_cur = di == tree.cursor
            indent = "  " * depth

            if node["kind"] == "node":
                icon = "▼ " if node.get("expanded") else "▶ "
                label = f"{indent}{icon}{node['key']}"
                cp = C_TREE_NODE
            elif node["kind"] == "leaf":
                fk, fv = node["key"], node["value"]
                if _is_sensitive(fk):
                    vs = _mask_value(str(fv))
                    vc = C_MASKED
                elif isinstance(fv, bool):
                    vs = "on" if fv else "off"
                    vc = C_BOOL_ON if fv else C_BOOL_OFF
                else:
                    vs = _truncate(str(fv), w - depth * 2 - len(fk) - 8)
                    vc = C_DEFAULT
                label = f"{indent}{fk}: {vs}"
                cp = C_TREE_LEAF
            elif node["kind"] == "list":
                preview = f"[{len(node['value'])}]"
                label = f"{indent}{node['key']}: {preview}"
                cp = C_DIM
            else:
                ids = ",".join(m.get("model_id", "?") for m in node["value"][:3])
                label = f"{indent}{node['key']}: [{len(node['value'])}] {ids}"
                cp = C_DIM

            prefix = "▸ " if is_cur else "   "
            attr = curses.A_BOLD if is_cur else 0
            _safe_addstr(
                self.stdscr,
                top_y + i,
                left_x + 1,
                f"{prefix}{label}",
                curses.color_pair(cp) | attr,
            )

        sb_x = left_x + w - 1
        if len(tree.flat) > visible_h:
            sb_h = visible_h
            sb_pos = (
                int(tree.scroll / (len(tree.flat) - visible_h) * (sb_h - 1))
                if len(tree.flat) > visible_h
                else 0
            )
            for si in range(sb_h):
                sc = C_SCROLLBAR if si == sb_pos else C_BORDER
                _safe_addstr(self.stdscr, top_y + si, sb_x, "│", curses.color_pair(sc))

    def _draw_status(self, top_y, left_x, h, w, max_y, max_x):
        lines = self._build_status_lines()
        visible_h = h - 1
        if self.status_scroll > len(lines) - visible_h:
            self.status_scroll = max(0, len(lines) - visible_h)

        for i in range(visible_h):
            di = i + self.status_scroll
            if di >= len(lines):
                break
            kind, text = lines[di]
            cm = {
                "header": C_SECTION | curses.A_BOLD,
                "text": C_DEFAULT,
                "dim": C_DIM,
                "ok": C_SUCCESS,
                "err": C_ERROR,
            }.get(kind, C_DEFAULT)
            _safe_addstr(
                self.stdscr, top_y + i, left_x + 2, text, curses.color_pair(cm)
            )

    def _build_status_lines(self) -> List[Tuple[str, str]]:
        L = []
        L.append(("header", "System"))
        L.append(
            ("text", f"  Time     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        )
        L.append(("text", f"  Config   : {CONFIG_PATH.name}"))
        L.append(("text", f"  Modified : {'yes' if self.dirty else 'no'}"))
        L.append(("dim", ""))
        L.append(("header", "Models"))
        for m in self.config.get("models", []):
            dot = "●" if m.get("enabled") else "○"
            L.append(
                (
                    "ok" if m.get("enabled") else "err",
                    f"  {dot} {m.get('model_id', '?'):20s} {m.get('layer', '?'):6s} {m.get('role', '?'):10s}",
                )
            )
        L.append(("dim", ""))
        L.append(("header", "Database"))
        dbp = Path(self.config.get("data_dir", "./data")) / "qq_bot.db"
        if dbp.exists():
            try:
                conn = sqlite3.connect(str(dbp))
                for (tbl,) in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall():
                    cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    L.append(("text", f"  {tbl}: {cnt} rows"))
                conn.close()
            except Exception as e:
                L.append(("err", f"  Error: {e}"))
        else:
            L.append(("dim", "  Not found"))
        L.append(("dim", ""))
        L.append(("header", "Engine"))
        if self.chat_engine._initialized:
            L.append(("ok", "  Status: initialized"))
            L.append(("text", f"  Session: {self.chat_engine._session_key}"))
        else:
            L.append(("err", f"  Error: {self.chat_engine._init_error}"))
        return L

    def _draw_help(self, top_y, left_x, h, w, max_y, max_x):
        help_lines = [
            ("header", "Keyboard Shortcuts"),
            ("text", ""),
            ("text", "  Global"),
            ("dim", "    Tab       Switch between panels"),
            ("dim", "    q         Quit (Q = force)"),
            ("text", ""),
            ("text", "  Chat Panel"),
            ("dim", "    i / Enter Start input mode"),
            ("dim", "    j / ↓     Scroll down"),
            ("dim", "    k / ↑     Scroll up"),
            ("dim", "    PgDn      Page down"),
            ("dim", "    PgUp      Page up"),
            ("dim", "    s         Save config"),
            ("text", ""),
            ("text", "  Config Panel"),
            ("dim", "    j / ↓     Move cursor down"),
            ("dim", "    k / ↑     Move cursor up"),
            ("dim", "    Enter     Expand/collapse or edit"),
            ("dim", "    s         Save config"),
            ("text", ""),
            ("text", "  Status Panel"),
            ("dim", "    j / ↓     Scroll down"),
            ("dim", "    k / ↑     Scroll up"),
            ("text", ""),
            ("header", "About"),
            ("text", f"  LingMeng OS v1.0 — terminal companion"),
            ("text", f"  Built for {CONFIG_PATH.name}"),
            ("text", ""),
            ("dim", "  AI maid spirit living inside your shell."),
            ("dim", "  Gentle, loyal, adorable."),
        ]
        visible_h = h - 1
        if self.help_scroll > len(help_lines) - visible_h:
            self.help_scroll = max(0, len(help_lines) - visible_h)
        for i in range(visible_h):
            di = i + self.help_scroll
            if di >= len(help_lines):
                break
            kind, text = help_lines[di]
            cm = {
                "header": C_SECTION | curses.A_BOLD,
                "text": C_DEFAULT,
                "dim": C_DIM,
            }.get(kind, C_DEFAULT)
            _safe_addstr(
                self.stdscr, top_y + i, left_x + 2, text, curses.color_pair(cm)
            )

    def _draw_footer(self, max_y, max_x):
        footer_y = max_y - 1
        self._draw_hline(self.stdscr, footer_y - 1, 0, max_x)

        hints = {
            self.TAB_CHAT: " i:input  j/k:scroll  s:save  Tab:switch  q:quit ",
            self.TAB_CONFIG: " j/k:navigate  Enter:edit  s:save  Tab:switch  q:quit ",
            self.TAB_STATUS: " j/k:scroll  r:refresh  Tab:switch  q:quit ",
            self.TAB_HELP: " j/k:scroll  Tab:switch  q:quit ",
        }
        hint = hints.get(self.active_tab, "")
        _safe_addstr(self.stdscr, footer_y, 1, hint, curses.color_pair(C_DIM))

        if self.status_msg:
            mid = f"  {self.status_msg}  "
            _safe_addstr(
                self.stdscr,
                footer_y,
                max_x // 2 - len(mid) // 2,
                mid,
                curses.color_pair(C_SUCCESS),
            )

    def _draw_footer(self, max_y, max_x):
        footer_y = max_y - 1
        self._draw_hline(self.stdscr, footer_y - 1, 0, max_x)

        hints = {
            self.TAB_CHAT: " i:input  j/k:scroll  s:save  Tab:switch  q:quit ",
            self.TAB_CONFIG: " j/k:navigate  Enter:edit  s:save  Tab:switch  q:quit ",
            self.TAB_STATUS: " j/k:scroll  r:refresh  Tab:switch  q:quit ",
            self.TAB_HELP: " j/k:scroll  Tab:switch  q:quit ",
        }
        hint = hints.get(self.active_tab, "")
        _safe_addstr(self.stdscr, footer_y, 1, hint, curses.color_pair(C_DIM))

        if self.status_msg:
            mid = f"  {self.status_msg}  "
            _safe_addstr(self.stdscr, footer_y, max_x // 2 - len(mid) // 2, mid, curses.color_pair(C_SUCCESS))

    def _draw_hline(self, scr, y, x, w):
        try:
            scr.addstr(y, x, "─" * w, curses.color_pair(C_BORDER) | curses.A_DIM)
        except curses.error:
            pass


def main():
    try:
        stdscr = curses.initscr()
        _init_colors()
        curses.noecho()
        curses.raw()
        tui = XiaoMengTUI(stdscr)
        tui.run()
    except SystemExit:
        pass
    finally:
        curses.endwin()


if __name__ == "__main__":
    main()
