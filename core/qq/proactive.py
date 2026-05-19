"""
主动发言系统
每个群一个后台 asyncio 任务，LLM 自己判断要不要说话、说什么

设计要点：
- 随机间隔触发（默认 5~15 分钟），不是固定时钟
- 触发后判断：安静时段/最近新消息太少 → 跳过
- 把近期群消息喂给本地 LLM，LLM 输出 JSON 决定是否发言及内容
- JSON 解析失败 → 当作不发言，不崩溃
- bot 上次发言后有最短冷却时间，避免刷屏
"""

import asyncio
import json
import logging
import random
import re
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from .napcat import NapCatClient
    from ..model_layer import ModelLayerRouter

logger = logging.getLogger(__name__)


PROACTIVE_PROMPT = """你是{name}，正在一个 QQ 群里静静地看着大家聊天。群名：{group_name}

最近群里的消息（从旧到新）：
{recent_msgs}

请判断你现在要不要主动说点什么。

判断时参考：
- 如果话题有趣、和你有关、或者你有真的想补充的 → 可以说
- 如果讨论你完全不懂的专业话题 → 不说
- 如果群里很久没人发言、冷冷清清 → 可以随口问问
- 如果你刚才才发过言 → 不说
- 如果现在是深夜大家可能在睡觉 → 不说
- 不要硬找话题，不要生硬接话，要自然

只输出 JSON，格式：
{{"should_speak": true 或 false, "message": "如果要说就写内容，不说则为空字符串"}}"""


class GroupProactiveAgent:
    """
    单个群的主动发言代理，作为后台 asyncio 任务运行。
    """

    def __init__(
        self,
        group_id: int,
        db_path: str,
        router: "ModelLayerRouter",
        napcat: "NapCatClient",
        bot_name: str = "小萌",
        min_interval: int = 300,
        max_interval: int = 900,
        min_new_msgs: int = 3,
        quiet_start: int = 1,
        quiet_end: int = 8,
        cooldown_secs: int = 60,
        soul_path: str = "",
        llm_max_tokens: int = 200,
        llm_temperature: float = 0.9,
        recent_messages_limit: int = 20,
    ):
        self._group_id = group_id
        self._db_path = db_path
        self._router = router
        self._napcat = napcat
        self._bot_name = bot_name
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._min_new_msgs = min_new_msgs
        self._quiet_start = quiet_start
        self._quiet_end = quiet_end
        self._cooldown_secs = cooldown_secs
        self._soul_path = soul_path
        self._llm_max_tokens = llm_max_tokens
        self._llm_temperature = llm_temperature
        self._recent_messages_limit = recent_messages_limit
        self._last_spoke_at: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ──────────────────────────────────────────────
    # 内部循环
    # ──────────────────────────────────────────────

    async def _run(self) -> None:
        logger.info(f"群 {self._group_id} 主动发言任务已启动")
        while True:
            interval = random.randint(self._min_interval, self._max_interval)
            await asyncio.sleep(interval)
            try:
                await self._check_and_speak()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"群 {self._group_id} 主动发言检查出错: {e}")

    async def _check_and_speak(self) -> None:
        # 1. 安静时段
        if self._in_quiet_hours():
            return

        # 2. 冷却
        if self._last_spoke_at:
            elapsed = (datetime.now() - self._last_spoke_at).total_seconds()
            if elapsed < self._cooldown_secs:
                return

        # 3. 获取近期群消息
        session_key = f"group:{self._group_id}"
        recent = self._get_recent_messages(session_key, limit=self._recent_messages_limit)
        if not recent:
            return

        # 4. 统计 bot 上次发言后的新消息数
        msgs_since_bot = self._count_since_last_bot(recent)
        if msgs_since_bot < self._min_new_msgs:
            return

        # 5. 询问 LLM
        group_name = self._get_group_name()
        formatted = self._format_messages(recent)
        prompt = PROACTIVE_PROMPT.format(
            name=self._bot_name,
            group_name=group_name or f"群{self._group_id}",
            recent_msgs=formatted,
        )

        soul_text = self._load_soul()
        # 直接拿本地 adapter，绕过路由层（主动发言固定用本地模型）
        from ..model_layer import ModelLayer, ModelRole
        adapter = self._router.get_available_adapter(ModelLayer.BASIC, ModelRole.CHAT)
        if adapter is None:
            logger.debug(f"群 {self._group_id} 本地模型不可用，跳过主动发言")
            return
        try:
            response = await adapter.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=soul_text,
                max_tokens=self._llm_max_tokens,
                temperature=self._llm_temperature,
            )
            content = response.content.strip()
        except Exception as e:
            logger.debug(f"群 {self._group_id} LLM 调用失败: {e}")
            return

        # 6. 解析 JSON
        decision = _parse_decision(content)
        if not decision or not decision.get("should_speak"):
            return
        message = decision.get("message", "").strip()
        if not message:
            return

        # 7. 发送（加随机延迟模拟打字）
        delay = random.uniform(1.0, 3.0)
        await asyncio.sleep(delay)
        try:
            await self._napcat.send_group_msg(self._group_id, message)
            self._last_spoke_at = datetime.now()
            # 写入 DB
            self._save_bot_message(session_key, message)
            logger.info(f"群 {self._group_id} 主动发言: {message[:30]}...")
        except Exception as e:
            logger.warning(f"群 {self._group_id} 发送主动消息失败: {e}")

    # ──────────────────────────────────────────────
    # 辅助
    # ──────────────────────────────────────────────

    def _load_soul(self) -> str:
        if not self._soul_path:
            return ""
        try:
            from pathlib import Path
            return Path(self._soul_path).read_text(encoding="utf-8")
        except Exception:
            return ""

    def _in_quiet_hours(self) -> bool:
        hour = datetime.now().hour
        s, e = self._quiet_start, self._quiet_end
        if s <= e:
            return s <= hour < e
        return hour >= s or hour < e

    def _get_recent_messages(self, session_key: str, limit: int) -> list:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                """SELECT role, sender_name, sender_qq, content, created_at
                   FROM messages WHERE session_key=?
                   ORDER BY id DESC LIMIT ?""",
                (session_key, limit),
            )
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return list(reversed(rows))
        except Exception:
            return []

    def _count_since_last_bot(self, messages: list) -> int:
        count = 0
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                break
            count += 1
        return count

    def _format_messages(self, messages: list) -> str:
        lines = []
        for msg in messages:
            if msg.get("role") == "assistant":
                name = self._bot_name
            else:
                name = msg.get("sender_name") or f"QQ{msg.get('sender_qq', '?')}"
            ts = (msg.get("created_at") or "")
            if len(ts) >= 16:
                ts = ts[11:16]
            content = msg.get("content", "")
            lines.append(f"[{ts}] {name}: {content}")
        return "\n".join(lines)

    def _get_group_name(self) -> str:
        try:
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute(
                "SELECT group_name FROM group_info WHERE group_id=? LIMIT 1",
                (self._group_id,),
            )
            row = c.fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception:
            return ""

    def _save_bot_message(self, session_key: str, content: str) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO messages (session_key, role, content, created_at)
                   VALUES (?, 'assistant', ?, ?)""",
                (session_key, content, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# ──────────────────────────────────────────────
# ProactiveManager：管理所有群的代理实例
# ──────────────────────────────────────────────

class ProactiveManager:
    """统一管理所有群的 GroupProactiveAgent"""

    def __init__(
        self,
        db_path: str,
        router: "ModelLayerRouter",
        napcat: "NapCatClient",
        bot_name: str = "小萌",
        config: Optional[dict] = None,
        soul_path: str = "",
    ):
        self._db_path = db_path
        self._router = router
        self._napcat = napcat
        self._bot_name = bot_name
        self._config = config or {}
        self._soul_path = soul_path
        self._agents: Dict[int, GroupProactiveAgent] = {}

    def ensure_group(self, group_id: int) -> None:
        """确保该群有主动发言代理（没有则创建）"""
        if group_id not in self._agents:
            agent = GroupProactiveAgent(
                group_id=group_id,
                db_path=self._db_path,
                router=self._router,
                napcat=self._napcat,
                bot_name=self._bot_name,
                min_interval=self._config.get("proactive_interval", {}).get("min", 300),
                max_interval=self._config.get("proactive_interval", {}).get("max", 900),
                min_new_msgs=self._config.get("proactive_min_messages", 3),
                quiet_start=self._config.get("quiet_hours", {}).get("start", 1),
                quiet_end=self._config.get("quiet_hours", {}).get("end", 8),
                cooldown_secs=self._config.get("proactive", {}).get("cooldown_secs", 60),
                soul_path=self._soul_path,
                llm_max_tokens=self._config.get("proactive", {}).get("llm_max_tokens", 200),
                llm_temperature=self._config.get("proactive", {}).get("llm_temperature", 0.9),
                recent_messages_limit=self._config.get("proactive", {}).get("recent_messages_limit", 20),
            )
            self._agents[group_id] = agent
            agent.start()
            logger.info(f"为群 {group_id} 启动主动发言代理")

    def stop_all(self) -> None:
        for agent in self._agents.values():
            agent.stop()
        self._agents.clear()


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _parse_decision(text: str) -> Optional[dict]:
    """从 LLM 输出中提取 JSON 决策，容忍额外文字"""
    m = re.search(r'\{[^{}]*"should_speak"[^{}]*\}', text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None
