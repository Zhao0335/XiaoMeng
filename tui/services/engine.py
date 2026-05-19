"""Chat Engine service — wraps AI model routing and streaming."""

import asyncio
import json
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ChatEngine:
    """Handles AI chat with model routing, tool execution, and streaming."""

    MOOD_LIST = [
        "idle", "happy", "thinking", "excited", "typing", "processing",
        "success", "error", "sleepy", "sad", "surprised", "confused",
    ]

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
        self._ModelLayer = None
        self._ModelRole = None
        self._PermLevel = None
        self._TOOL_SCHEMAS = None
        self._LOCAL_OK_TOOLS = {"search_memory", "recall_conversations"}
        self._WRITE_TOOLS = {"write_file", "add_memory", "update_soul"}
        self._ROUTER_PROMPT = (
            "You are a routing assistant. Read the user message and output exactly one word:\n"
            "- CLOUD  → real-time info, web search, complex reasoning, math, long writing\n"
            "- LOCAL  → casual chat, greetings, simple opinions\n"
            "Output only one word: LOCAL or CLOUD"
        )

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    @property
    def generating(self) -> bool:
        return self._generating

    @property
    def streaming_text(self) -> str:
        return self._streaming_text

    @property
    def session_key(self) -> str:
        return self._session_key

    def initialize(self) -> None:
        try:
            from core.model_layer import (
                ModelLayer,
                ModelRole,
                ModelLayerRouter,
                ModelEndpoint,
            )
            from core.qq.tools import QQToolExecutor, TOOL_SCHEMAS
            from core.qq.permissions import PermLevel

            router = ModelLayerRouter()
            for m in self._config.get("models", []):
                if not m.get("enabled", True):
                    continue
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

    def chat_stream(self, user_text: str) -> None:
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

    def _load_recent_messages(self, limit: int = 30) -> List[dict]:
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

    def _save_turn(self, user_text: str, assistant_text: str) -> None:
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

    def _build_system_prompt(self, local: bool = False) -> str:
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

    async def _chat_async(self, user_text: str) -> None:
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
                    cloud_keywords
                    and any(kw in user_text for kw in cloud_keywords)
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
                            r"usse.*?ee",
                            "",
                            rd.content or "",
                            flags=re.DOTALL,
                        ).upper()
                        use_cloud = "CLOUD" in decision or cloud_hint
                    except Exception:
                        use_cloud = cloud_hint
                else:
                    use_cloud = cloud_hint

            if use_pro:
                active_adapter = pro_adapter
                timeout = cfg.get("llm_timeouts", {}).get("pro", 300)
                route_label = "PRO"
            elif use_cloud:
                active_adapter = cloud_adapter
                timeout = cfg.get("llm_timeouts", {}).get("cloud", 180)
                route_label = "CLOUD"
            else:
                active_adapter = local_adapter or cloud_adapter
                timeout = cfg.get("llm_timeouts", {}).get("local", 90)
                route_label = "LOCAL"

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
            max_searches = cfg.get("loop_limits", {}).get("max_searches_before_write", 4)
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
                    name = tc.get("name", "")
                    args = tc.get("arguments", {})
                    if name == "web_search":
                        search_count += 1
                    elif name in self._WRITE_TOOLS:
                        wrote_something = True
                    self._streaming_text += (
                        f"\n  > {name}({json.dumps(args, ensure_ascii=False)[:40]})"
                    )
                    result = await tool_executor.execute(name, args)
                    self._streaming_text += f"\n    {result[:60]}"
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
