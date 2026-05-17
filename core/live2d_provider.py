"""
XiaoMengLLMProvider
====================
兼容 llm_live2d LLMProvider 接口（duck-typing），给 Live2D Pipeline 提供：
  - 多模型路由（PRO / 云端 / 本地）
  - 完整工具调用循环（web_search / 记忆 / 文件读写）
  - 与 QQ gateway 共享同一个 qq_bot.db（session_key = "private:{qq}"）

不修改 .llm-live2d 任何文件；只要实现 astream() 即可接入 Pipeline。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional

from .model_layer import ModelLayer, ModelRole, ModelLayerRouter
from .qq.tools import QQToolExecutor, TOOL_SCHEMAS
from .qq.permissions import PermLevel

logger = logging.getLogger(__name__)

# run_command 不对 Live2D 开放（浏览器端不需要 shell 权限）
_LIVE2D_TOOL_SCHEMAS = [
    s for s in TOOL_SCHEMAS
    if s["function"]["name"] != "run_command"
]

# 与 gateway 保持一致
_ROUTER_PROMPT = """\
You are a routing assistant. Read the user message and output exactly one word:
- CLOUD  → if the task needs: real-time info, web search, news, current events, \
complex reasoning, math, long writing, code generation, deep analysis, \
verifying specific facts (does X exist? is X real? when did X happen?)
- LOCAL  → for casual chat, greetings, simple opinions, short emotional replies

Output only one word: LOCAL or CLOUD"""

_LOCAL_OK_TOOLS = {"read_file", "list_files", "search_memory", "recall_conversations"}
_WRITE_TOOLS = {"write_file", "add_memory", "update_soul"}
_MAX_TOOL_LOOPS = 10
_MAX_SEARCHES_BEFORE_WRITE = 4

# Live2D 输出不适合 Markdown / 原始 URL
_MD_BOLD = re.compile(r"\*{1,3}|_{1,3}")
_MD_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_RAW_URL = re.compile(r"https?://\S+")
_THINK_TAG = re.compile(r"<think>.*?</think>", re.DOTALL)
_DSML_TOOL = re.compile(r"<｜｜DSML｜｜tool_calls>.*?</｜｜DSML｜｜tool_calls>", re.DOTALL)
_MULTI_NL = re.compile(r"\n{3,}")


def _clean_for_live2d(text: str) -> str:
    """清理不适合 TTS 朗读的内容：Markdown、URL、代码块、推理标签等。"""
    text = _THINK_TAG.sub("", text)
    text = _DSML_TOOL.sub("", text)
    text = _CODE_BLOCK.sub("（代码已省略）", text)
    text = _RAW_URL.sub("", text)
    text = _MD_HEADER.sub("", text)
    text = _MD_BOLD.sub("", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


class XiaoMengLLMProvider:
    """
    Duck-typing 兼容 llm_live2d.core.providers.LLMProvider。

    工作流：
      1. 路由决策（PRO 关键词 > router 模型 LOCAL/CLOUD）
      2. 工具调用循环（≤10 轮，复用 QQToolExecutor）
      3. 清洗最终文本（去 Markdown / URL / 推理标签）
      4. yield 给 Pipeline
    """

    def __init__(
        self,
        router: ModelLayerRouter,
        db_path: str,
        soul_path: str,
        data_dir: str,
        sender_qq: int,
        level: PermLevel = PermLevel.OWNER,
        pro_keywords: List[str] = (),
        proxy: str = "",
    ):
        self._router = router
        self._db_path = db_path
        self._soul_path = Path(soul_path)
        self._data_dir = Path(data_dir)
        self._sender_qq = sender_qq
        self._level = level
        self._session_key = f"private:{sender_qq}"
        self._pro_keywords = list(pro_keywords)
        self._proxy = proxy

    # ──────────────────────────────────────────────────────────────
    # LLMProvider 接口
    # ──────────────────────────────────────────────────────────────

    async def astream(
        self,
        messages,           # List[ChatMessage]（来自 llm_live2d）
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Pipeline 调用此方法获取回复文本流。
        内部同步完成工具循环，最终 yield 清洗后的文本。
        """
        # ChatMessage → dict（model_layer 用 dict）
        msgs_dict: List[Dict] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        user_text = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )

        try:
            final_text = await self._run_loop(msgs_dict, user_text)
        except Exception as e:
            logger.error(f"Live2D LLM loop 失败: {e}", exc_info=True)
            final_text = "（小萌出了点问题，请稍后再试~）"

        # 写入 SQLite（与 QQ gateway 共享 DB）
        self._save_turn(user_text, final_text)

        cleaned = _clean_for_live2d(final_text)
        # 分小块 yield，让 Pipeline 能边解析边 TTS
        chunk_size = 30
        for i in range(0, len(cleaned), chunk_size):
            yield cleaned[i: i + chunk_size]
            await asyncio.sleep(0)

    # ──────────────────────────────────────────────────────────────
    # 核心：路由 + 工具循环
    # ──────────────────────────────────────────────────────────────

    async def _run_loop(self, messages: List[Dict], user_text: str) -> str:
        local_adapter = self._router.get_basic_adapter()
        cloud_adapter = self._router.get_available_adapter(ModelLayer.BRAIN, ModelRole.REASONING)
        pro_adapter = self._router.get_available_adapter(ModelLayer.PRO, ModelRole.REASONING)
        router_adapter = self._router.get_available_adapter(ModelLayer.BASIC, ModelRole.ROUTER)

        if local_adapter is None and cloud_adapter is None:
            return "（没有可用的模型）"

        # ── 路由决策 ──────────────────────────────────────────────
        use_pro = bool(
            pro_adapter and self._pro_keywords
            and any(kw in user_text for kw in self._pro_keywords)
        )
        use_cloud = False
        if not use_pro and cloud_adapter and router_adapter:
            try:
                rd = await asyncio.wait_for(
                    router_adapter.chat(
                        messages[-4:],  # 只取最近几条上下文
                        system_prompt=_ROUTER_PROMPT,
                        max_tokens=getattr(
                            getattr(router_adapter, "endpoint", None), "max_tokens", 20
                        ),
                    ),
                    timeout=15,
                )
                decision = re.sub(r"<think>.*?</think>", "", rd.content or "", flags=re.DOTALL)
                use_cloud = "CLOUD" in decision.upper()
            except Exception:
                use_cloud = False

        if use_pro:
            active_adapter = pro_adapter
            timeout = 300
        elif use_cloud:
            active_adapter = cloud_adapter
            timeout = 180
        else:
            active_adapter = local_adapter or cloud_adapter
            timeout = 90

        max_tokens = getattr(getattr(active_adapter, "endpoint", None), "max_tokens", 4096)

        tool_executor = QQToolExecutor(
            db_path=self._db_path,
            soul_path=self._soul_path,
            data_dir=self._data_dir,
            session_key=self._session_key,
            sender_qq=self._sender_qq,
            level=self._level,
            identity=f"user_{self._sender_qq}",
            proxy=self._proxy,
        )

        # ── 首次调用 ──────────────────────────────────────────────
        response = await asyncio.wait_for(
            active_adapter.chat(messages, tools=_LIVE2D_TOOL_SCHEMAS, max_tokens=max_tokens),
            timeout=timeout,
        )

        # 本地触发重型工具 → 升级云端
        if (
            active_adapter is local_adapter
            and cloud_adapter is not None
            and any(
                tc.get("name") not in _LOCAL_OK_TOOLS
                for tc in (response.tool_calls or [])
            )
        ):
            active_adapter = cloud_adapter
            timeout = 180
            max_tokens = getattr(getattr(cloud_adapter, "endpoint", None), "max_tokens", 8192)
            response = await asyncio.wait_for(
                active_adapter.chat(messages, tools=_LIVE2D_TOOL_SCHEMAS, max_tokens=max_tokens),
                timeout=timeout,
            )

        # ── 工具循环 ──────────────────────────────────────────────
        loop_messages = list(messages)
        search_count = 0
        wrote_something = False

        for _ in range(_MAX_TOOL_LOOPS):
            if not response.tool_calls:
                break

            asst_msg: Dict = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False),
                        },
                    }
                    for i, tc in enumerate(response.tool_calls)
                ],
            }
            if response.reasoning_content:
                asst_msg["reasoning_content"] = response.reasoning_content
            loop_messages.append(asst_msg)

            for tc in response.tool_calls:
                name = tc.get("name", "")
                args = tc.get("arguments", {})
                if name == "web_search":
                    search_count += 1
                elif name in _WRITE_TOOLS:
                    wrote_something = True

                result = await tool_executor.execute(name, args)
                logger.info(f"[Live2D] tool {name}: {result[:60]}")
                loop_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result,
                })

            if search_count >= _MAX_SEARCHES_BEFORE_WRITE and not wrote_something:
                loop_messages.append({
                    "role": "user",
                    "content": (
                        "【系统】你已经搜索了足够多的资料，现在必须立刻调用 "
                        "write_file 或 add_memory 保存结果，不要继续搜索。"
                    ),
                })

            response = await asyncio.wait_for(
                active_adapter.chat(
                    loop_messages,
                    tools=_LIVE2D_TOOL_SCHEMAS,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )

        return response.content or ""

    # ──────────────────────────────────────────────────────────────
    # SQLite 写入（与 QQ gateway 同结构，共享 DB）
    # ──────────────────────────────────────────────────────────────

    def _save_turn(self, user_text: str, assistant_text: str) -> None:
        if not (user_text.strip() or assistant_text.strip()):
            return
        now = datetime.now().isoformat()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO messages (session_key, role, sender_qq, sender_name, content, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (self._session_key, "user", self._sender_qq, "用户", user_text, now),
            )
            if assistant_text.strip():
                conn.execute(
                    "INSERT INTO messages (session_key, role, sender_qq, sender_name, content, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (self._session_key, "assistant", 0, "小萌", assistant_text, now),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Live2D 写 DB 失败: {e}")
