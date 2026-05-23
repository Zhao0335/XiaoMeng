"""
InnerWorldEventLogger — 跨群事件流，记录小萌视角的感受摘要。

每次小萌回复消息后，调用 append_event() 将本次交流压缩成一句话存入
data/inner_world/events.jsonl，供内心世界上下文使用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_EVENTS = 200
_KEEP_EVENTS = 150


class InnerWorldEventLogger:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "inner_world" / "events.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append_event(self, source: str, summary: str, emotion: str = "", who: str = "") -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M"),
            "source": source,
            "summary": summary,
        }
        if emotion:
            entry["emotion"] = emotion
        if who:
            entry["who"] = who
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._maybe_trim()
        except Exception as e:
            logger.warning(f"inner_world events 写入失败: {e}")

    def _maybe_trim(self) -> None:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            if len(lines) > _MAX_EVENTS:
                kept = lines[-_KEEP_EVENTS:]
                self._path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        except Exception:
            pass

    def read_recent(self, limit: int = 30) -> list[dict]:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            events = []
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return events
        except FileNotFoundError:
            return []

    def format_for_prompt(self, limit: int = 20) -> str:
        events = self.read_recent(limit)
        if not events:
            return "（暂无记录）"
        lines = []
        for e in events:
            ts = e.get("ts", "")
            src = e.get("source", "")
            summary = e.get("summary", "")
            emotion = e.get("emotion", "")
            who = e.get("who", "")
            tag = f"[{src}] " if src else ""
            who_tag = f"和{who} " if who else ""
            emo_tag = f" [{emotion}]" if emotion else ""
            lines.append(f"{ts} {tag}{who_tag}{summary}{emo_tag}")
        return "\n".join(lines)

    # ── CLOUD 批量标注 ────────────────────────────────

    async def enrich_with_cloud(self, cloud_adapter, soul: str = "", timeout: int = 60) -> int:
        """用 CLOUD 模型为最近没有情绪标签的事件批量补充 emotion + topic。
        返回实际标注的条数。soul 是小萌的人设文本，让模型从她的视角判断情绪。"""
        events = self.read_recent(limit=50)
        untagged = [(i, e) for i, e in enumerate(events) if not e.get("emotion")]
        if not untagged:
            return 0

        soul_brief = soul.split("---")[0].strip()[:400] if soul else "你是小萌，温柔可爱的 AI 伙伴。"
        system_prompt = (
            f"{soul_brief}\n\n"
            "以下记录是你（小萌）最近经历的对话感受摘要。"
            "请从你自己的性格出发，为每条补充一个情绪标签和话题标签。"
        )
        lines = "\n".join(f"{i+1}. {e['summary']}" for i, (_, e) in enumerate(untagged))
        prompt = (
            "为每条记录补充情绪标签和话题标签，格式为 `序号|情绪|话题`，每行一条。\n"
            "情绪选项：开心、平静、好奇、有成就感、有点无聊、感动、紧张\n"
            "话题选项：技术问题、音乐、闲聊、帮忙做事、学习、娱乐、其他\n\n"
            + lines
        )
        try:
            resp = await asyncio.wait_for(
                cloud_adapter.chat(
                    [{"role": "user", "content": prompt}],
                    system_prompt=system_prompt,
                    max_tokens=300,
                ),
                timeout=timeout,
            )
            tagged: dict[int, dict] = {}
            for line in (resp.content or "").strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 3:
                    try:
                        idx = int(parts[0].strip()) - 1
                        tagged[idx] = {"emotion": parts[1].strip(), "topic": parts[2].strip()}
                    except ValueError:
                        pass
            if not tagged:
                return 0
            all_events = self._read_all()
            tail_start = max(0, len(all_events) - 50)
            count = 0
            for local_idx in range(len(untagged)):
                if local_idx in tagged:
                    abs_idx = tail_start + local_idx
                    if abs_idx < len(all_events):
                        all_events[abs_idx].update(tagged[local_idx])
                        count += 1
            self._write_all(all_events)
            return count
        except Exception as e:
            logger.debug(f"inner_world 事件标注失败: {e}")
            return 0

    def _read_all(self) -> list[dict]:
        try:
            result = []
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return result
        except FileNotFoundError:
            return []

    def _write_all(self, events: list[dict]) -> None:
        self._path.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
            encoding="utf-8",
        )


async def compress_session_to_event(
    session_key: str,
    last_exchange: str,
    adapter,
    event_logger: InnerWorldEventLogger,
    soul: str = "",
    sender_name: str = "",
    timeout: int = 30,
) -> None:
    """调用 LOCAL 模型，将一次对话浓缩成小萌的一句感受，写入 events.jsonl。"""
    soul_brief = (soul.split("---")[0].strip()[:300] + "\n---") if soul else "你是小萌，温柔可爱的AI助手。"
    system_prompt = (
        f"{soul_brief}\n\n"
        "现在请用第一人称写一句话（不超过15个字）表达你刚才聊天的感受，只写感受本身。"
    )
    who_hint = f"和{sender_name}" if sender_name else ""
    try:
        resp = await asyncio.wait_for(
            adapter.chat(
                [{"role": "user", "content": f"刚才{who_hint}的对话：\n{last_exchange}"}],
                system_prompt=system_prompt,
                max_tokens=30,
            ),
            timeout=timeout,
        )
        summary = (resp.content or "").strip().split("\n")[0][:40]
        if summary and len(summary) <= 30:
            event_logger.append_event(source=session_key, summary=summary, who=sender_name)
        else:
            logger.debug(f"inner_world 事件结果无效，已丢弃: {summary[:30]!r}")
    except Exception as e:
        logger.debug(f"inner_world 事件压缩失败 ({session_key}): {e}")
