"""
ReActLoop - ReAct 循环执行器
=============================
Thought → Action → Observation → Reflection → Respond
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional

from .config import ReActConfig, ReActPhase, ReActStep

logger = logging.getLogger(__name__)


class ReActLoop:
    """
    ReAct 任务循环执行器。

    用法：
        loop = ReActLoop(config=ReActConfig())
        result = await loop.run(
            adapter=adapter,
            tool_executor=executor,
            messages=messages,
            system_prompt=system,
            tools=tools,
            on_progress=send_progress,
            is_cancelled=lambda: False,
            max_tokens=8192,
            timeout=180,
        )
    """

    def __init__(self, config: Optional[ReActConfig] = None):
        self.config = config or ReActConfig()
        self.steps: List[ReActStep] = []

    # ── 公开接口 ─────────────────────────────────────────────────

    async def run(
        self,
        *,
        adapter,
        tool_executor,
        messages: List[Dict],
        system_prompt: str,
        tools: List[Dict],
        on_progress,
        is_cancelled,
        max_tokens: int = 8192,
        timeout: float = 180,
    ) -> str:
        """执行完整的 ReAct 循环，返回最终回复文本。"""
        self.steps = []
        loop_messages = list(messages)
        search_count = 0
        wrote_something = False

        if is_cancelled():
            return "任务已取消"

        response = await self._call_model(
            adapter=adapter,
            messages=loop_messages,
            system_prompt=system_prompt,
            tools=tools,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if isinstance(response, str):
            await self._safe_progress(on_progress, response)
            return response

        for loop_i in range(self.config.max_tool_loops):
            if is_cancelled():
                return "任务已取消"

            tool_calls = response.tool_calls
            if not tool_calls:
                break

            asst_msg = self._build_assistant_message(response, tool_calls)
            loop_messages.append(asst_msg)

            for tc in tool_calls:
                if is_cancelled():
                    return "任务已取消"

                name = tc.get("name", "")
                args = tc.get("arguments", {})

                step = ReActStep(ReActPhase.ACTION)
                step.action = {"name": name, "arguments": args}
                self.steps.append(step)

                if name in self.config.search_tools:
                    search_count += 1
                elif name in self.config.write_tools:
                    wrote_something = True

                result = await tool_executor.execute(name, args)
                step.observation = result

                loop_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result,
                    }
                )

            if (
                search_count >= self.config.max_searches_before_write
                and not wrote_something
            ):
                loop_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "【系统】你已经搜索了足够多的资料，不要再继续搜索了。"
                            "现在必须立刻调用 write_file 或 add_memory 保存。"
                        ),
                    }
                )

            step = ReActStep(ReActPhase.REFLECT)
            step.thought = f"已完成第 {loop_i + 1} 轮工具调用，继续思考..."
            self.steps.append(step)

            response = await self._call_model(
                adapter=adapter,
                messages=loop_messages,
                system_prompt=system_prompt,
                tools=tools,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if isinstance(response, str):
                logger.warning(f"ReAct 循环第 {loop_i + 1} 轮超时")
                break

        final_text = self._clean_reply(
            response.content if hasattr(response, "content") else str(response)
        )

        if not final_text.strip():
            final_text = "（处理完成，但没有生成回复内容）"
            logger.warning("ReAct 循环空结果")

        loop_messages.append({"role": "assistant", "content": final_text})

        step = ReActStep(ReActPhase.RESPOND)
        step.thought = final_text[:200]
        self.steps.append(step)

        return final_text

    # ── 内部方法 ─────────────────────────────────────────────────

    async def _call_model(
        self, *, adapter, messages, system_prompt, tools, max_tokens, timeout
    ):
        try:
            return await asyncio.wait_for(
                adapter.chat(
                    messages,
                    system_prompt=system_prompt,
                    tools=tools,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return f"模型响应超时（{timeout}秒），请稍后重试或简化问题~"

    async def _safe_progress(self, on_progress, text: str):
        try:
            await on_progress(text)
        except Exception as e:
            logger.warning(f"发送进度消息失败: {e}")

    def _build_assistant_message(self, response, tool_calls) -> Dict:
        msg: Dict = {
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
                for i, tc in enumerate(tool_calls)
            ],
        }
        if getattr(response, "reasoning_content", None):
            msg["reasoning_content"] = response.reasoning_content
        return msg

    @staticmethod
    def _clean_reply(text: str) -> str:
        P = "｜｜DSML｜｜"
        tc_open = f"<{P}tool_calls>"
        tc_close = f"</{P}tool_calls>"
        while tc_open in text:
            s = text.find(tc_open)
            if s == -1:
                break
            e = text.find(tc_close, s)
            if e == -1:
                text = text[:s]
                break
            text = text[:s] + text[e + len(tc_close) :]
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return text.strip()
