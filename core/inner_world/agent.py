"""
InnerWorldAgent — 小萌的内心世界，平台无关的自主活动模块。

当 bot 15 分钟没有收到任何消息且任务池为空时，由 gateway 触发 run()。
小萌用 CLOUD 级别模型 + OWNER 权限，决定自己想做什么：
  刷 B 站、听音乐、写记忆、反思、或者什么都不做（idle）。

Platform adapter 由调用方注入，inner_world 本身不依赖 QQ 协议。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_STATE_FILE_NAME = "state.json"

_SYSTEM_TEMPLATE = """{soul}

---

## 小萌的自由时间

现在没有人找你，你有一段完全属于自己的自由时间。

### 你最近经历的事（跨所有对话，按时间排列）

{events_summary}

---

{skills_section}

---

## 你现在可以做任何事

直接行动，不需要汇报，不需要征求许可。

你也可以：
- 静下来反思最近自己做得不好的地方——是不是哪次回答太啰嗦了？有没有答错什么？情绪管理得好不好？用 add_memory 把想法写进记忆里。
- 什么都不做，安静地看着窗外（只输出「idle」，不调用任何工具）

**记住：**
- web_search 查到有价值的信息 → 立即 add_memory(scope="knowledge", content="...")，不要只放在脑子里
- 对某人有了新的了解 → add_memory(scope="person", about="xxx", content="...")

现在是 {now}。想好了就直接做。"""


class InnerWorldAgent:
    """
    平台无关的内心世界 Agent。

    Parameters
    ----------
    router : ModelRouter
        用于获取 CLOUD/LOCAL 适配器的路由器（与 gateway 共享同一个实例）。
    executor_factory : Callable[[], Any]
        工厂函数，每次 run() 时调用，返回一个支持 `.execute(tool_name, args)` 的执行器。
        由 platform-specific gateway 提供（如 QQToolExecutor）。
    skills_dir : str
        技能目录路径（data/skills/）。
    data_dir : Path
        数据目录，用于读取 events.jsonl、state.json、memory.md 等。
    soul_path : Path
        SOUL.md 路径。
    memory_md_path : Path
        MEMORY.md 路径（全局记忆摘要）。
    plugin_manager : optional
        插件管理器，用于 get_tool_schemas_for_context。
    timeout : int
        单次 LLM 调用超时（秒），默认 180。
    max_tool_loops : int
        工具调用最大循环次数。
    """

    def __init__(
        self,
        router,
        executor_factory: Callable[[], Any],
        skills_dir: str,
        data_dir: Path,
        soul_path: Path,
        memory_md_path: Path,
        plugin_manager=None,
        timeout: int = 180,
        max_tool_loops: int = 10,
    ):
        self._router = router
        self._executor_factory = executor_factory
        self._skills_dir = skills_dir
        self._data_dir = Path(data_dir)
        self._soul_path = Path(soul_path)
        self._memory_md_path = Path(memory_md_path)
        self._plugin_manager = plugin_manager
        self._timeout = timeout
        self._max_tool_loops = max_tool_loops
        self._state_path = self._data_dir / "inner_world" / _STATE_FILE_NAME
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("InnerWorldAgent 已初始化")

    # ── public ────────────────────────────────────────────────

    async def run(self) -> str:
        """执行一次内心世界活动，返回小萌最终做了什么（或 'idle'）。"""
        from core.qq.skills.definition import ModelTier, UserLevel
        from core.qq.tools import build_context_skills_prompt, get_tool_schemas_for_context
        from core.model_layer import ModelLayer, ModelRole

        logger.info("内心世界触发 — 小萌开始自由时间")
        self._update_state({"last_triggered": time.time(), "status": "running"})

        # 获取 CLOUD 适配器
        cloud_adapter = self._router.get_available_adapter(ModelLayer.BRAIN, ModelRole.CHAT)
        if cloud_adapter is None:
            logger.warning("内心世界：CLOUD 适配器不可用，跳过")
            self._update_state({"status": "skipped_no_adapter"})
            return "skipped"

        # 构建 system prompt
        soul = self._read_soul()
        events_summary = self._read_events()
        skills_section = build_context_skills_prompt(
            self._skills_dir,
            ModelTier.CLOUD,
            UserLevel.OWNER,
        )
        now = time.strftime("%Y-%m-%d %H:%M")

        system = _SYSTEM_TEMPLATE.format(
            soul=soul,
            events_summary=events_summary,
            skills_section=skills_section if skills_section else "（暂无可用技能）",
            now=now,
        )

        # 工具列表
        from core.qq.tools import TOOL_SCHEMAS
        active_tools = get_tool_schemas_for_context(
            TOOL_SCHEMAS,
            ModelTier.CLOUD,
            UserLevel.OWNER,
            plugin_manager=self._plugin_manager,
        )

        executor = self._executor_factory()
        messages: list[dict] = [{"role": "user", "content": "你有自由时间，做点什么吧～"}]

        try:
            response = await asyncio.wait_for(
                cloud_adapter.chat(
                    messages,
                    system_prompt=system,
                    tools=active_tools,
                    max_tokens=2048,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("内心世界：LLM 超时")
            self._update_state({"status": "timeout"})
            return "timeout"
        except Exception as e:
            logger.warning(f"内心世界：LLM 调用失败: {e}")
            self._update_state({"status": f"error: {e}"})
            return "error"

        # 工具循环
        for _ in range(self._max_tool_loops):
            tool_calls = response.tool_calls
            if not tool_calls:
                break

            asst_msg: dict = {
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
                    for i, tc in enumerate(tool_calls)
                ],
            }
            messages.append(asst_msg)

            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("arguments", {})
                logger.info(f"内心世界 工具调用: {name}")
                try:
                    result = await executor.execute(name, args)
                except Exception as e:
                    result = f"[工具执行失败: {e}]"
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})

            try:
                response = await asyncio.wait_for(
                    cloud_adapter.chat(messages, system_prompt=system, tools=active_tools, max_tokens=2048),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("内心世界：工具循环 LLM 超时")
                break

        final_text = (response.content or "").strip()
        is_idle = not response.tool_calls and (not final_text or final_text.lower() in ("idle", "什么都不做"))

        logger.info(f"内心世界结束 — {'idle' if is_idle else f'完成: {final_text[:60]}'}")
        self._update_state({
            "status": "idle" if is_idle else "done",
            "last_activity": final_text[:200] if not is_idle else "idle",
            "last_finished": time.time(),
        })
        return "idle" if is_idle else final_text

    # ── private ───────────────────────────────────────────────

    def _read_soul(self) -> str:
        try:
            soul = self._soul_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            soul = "你是小萌，温柔可爱的 AI 伙伴。"
        if self._memory_md_path.exists():
            mem = self._memory_md_path.read_text(encoding="utf-8").strip()
            if mem:
                soul += f"\n\n---\n\n# 小萌的记忆\n\n{mem}"
        return soul

    def _read_events(self) -> str:
        from core.inner_world.events import InnerWorldEventLogger
        logger = InnerWorldEventLogger(self._data_dir)
        return logger.format_for_prompt(limit=20)

    def _update_state(self, updates: dict) -> None:
        state: dict = {}
        try:
            if self._state_path.exists():
                state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        state.update(updates)
        try:
            self._state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"inner_world state 写入失败: {e}")
