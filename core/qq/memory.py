"""
Memory management mixin and DB schema for QQGateway.
Extracted from gateway.py to reduce file size.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# DB Schema
# ──────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key  TEXT    NOT NULL,
    role         TEXT    NOT NULL,
    sender_qq    INTEGER,
    sender_name  TEXT,
    content      TEXT    NOT NULL,
    attachments  TEXT    NOT NULL DEFAULT '[]',
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_key, id);

CREATE TABLE IF NOT EXISTS long_term_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key  TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    memory_type  TEXT    NOT NULL DEFAULT 'summary',
    importance   INTEGER DEFAULT 1,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ltm_session ON long_term_memory(session_key);

CREATE TABLE IF NOT EXISTS pending_friend_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_qq    INTEGER NOT NULL,
    requester_nick  TEXT,
    comment         TEXT,
    flag            TEXT    NOT NULL,
    received_at     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS pending_group_invites (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id     INTEGER NOT NULL,
    group_name   TEXT,
    inviter_qq   INTEGER,
    flag         TEXT    NOT NULL,
    sub_type     TEXT,
    received_at  TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS group_info (
    group_id     INTEGER PRIMARY KEY,
    group_name   TEXT,
    updated_at   TEXT
);
"""


class MemoryMixin:
    """Mixin providing DB initialization, message storage and memory compression for QQGateway."""

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT NOT NULL DEFAULT '[]'")
            conn.commit()
        except Exception:
            pass
        conn.commit()
        conn.close()
        logger.info(f"数据库已初始化: {self._db_path}")

    def _create_bg_task(self, coro) -> asyncio.Task:
        """创建后台任务并保持强引用，防止 GC 取消，同时记录未捕获异常。"""
        t = asyncio.create_task(coro)
        self._bg_tasks.add(t)
        t.add_done_callback(self._bg_tasks.discard)

        def _log_exc(task: asyncio.Task):
            if not task.cancelled() and task.exception():
                logger.warning(f"后台任务异常: {task.exception()}")

        t.add_done_callback(_log_exc)
        return t

    def _save_message(
        self,
        session_key: str,
        role: str,
        content: str,
        sender_qq: int = None,
        sender_name: str = None,
        attachments: list = None,
    ) -> Optional[int]:
        conn = sqlite3.connect(self._db_path)
        try:
            cur = conn.execute(
                """INSERT INTO messages (session_key, role, sender_qq, sender_name, content, attachments, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_key,
                    role,
                    sender_qq,
                    sender_name,
                    content,
                    json.dumps(attachments or [], ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
            return None
        finally:
            conn.close()

    def _update_message_content(self, msg_id: int, content: str) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("UPDATE messages SET content=? WHERE id=?", (content, msg_id))
            conn.commit()
        except Exception as e:
            logger.error(f"更新消息失败: {e}")
        finally:
            conn.close()

    def _get_recent_messages(self, session_key: str, limit: int = 30) -> List[dict]:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                """SELECT id, role, sender_qq, sender_name, content, attachments, created_at
                   FROM messages WHERE session_key=?
                   ORDER BY id DESC LIMIT ?""",
                (session_key, limit),
            )
            rows = [dict(r) for r in c.fetchall()]
            return list(reversed(rows))
        except Exception as e:
            logger.debug(f"读取最近消息失败 ({session_key}): {e}")
            return []
        finally:
            conn.close()

    def _get_long_term_memory(self, session_key: str, limit: int = 5) -> str:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                """SELECT content FROM long_term_memory WHERE session_key=?
                   ORDER BY importance DESC, id DESC LIMIT ?""",
                (session_key, limit),
            )
            rows = [r["content"] for r in c.fetchall()]
            return "\n".join(rows)
        except Exception as e:
            logger.debug(f"读取长期记忆失败 ({session_key}): {e}")
            return ""
        finally:
            conn.close()

    def _maybe_compress(self, session_key: str) -> None:
        """异步触发记忆压缩"""
        conn = sqlite3.connect(self._db_path)
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM messages WHERE session_key=?", (session_key,))
            count = c.fetchone()[0]
        except Exception as e:
            logger.debug(f"检查压缩阈值失败 ({session_key}): {e}")
            return
        finally:
            conn.close()

        if count > 0 and count % self._compress_every == 0:
            self._create_bg_task(self._compress_memory(session_key))

    async def _compress_memory(self, session_key: str) -> None:
        """将旧消息压缩为长期记忆摘要，同步写到 MEMORY.md，并触发 soul 反思。"""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                """SELECT id, role, sender_name, content FROM messages
                   WHERE session_key=? ORDER BY id ASC""",
                (session_key,),
            )
            all_rows = [dict(r) for r in c.fetchall()]
            conn.close()

            if len(all_rows) <= self._short_term_keep:
                return

            to_compress = all_rows[: -self._short_term_keep]
            lines = []
            for r in to_compress:
                name = r.get("sender_name") or (
                    self._bot_name if r["role"] == "assistant" else "用户"
                )
                lines.append(f"{name}: {r['content']}")
            conversation_text = "\n".join(lines)

            adapter = self._router.get_basic_adapter()
            if adapter is None:
                return

            is_private = session_key.startswith("private:")

            if is_private:
                conv_prompt = (
                    "以下是一段私信对话记录。请用中文简洁总结这段对话的主要话题和重要信息，"
                    "以要点列表输出（最多6条，每条以'- '开头）。\n"
                    "只写实际发生的事情，不要评价，不要重复废话。\n\n"
                    f"对话记录：\n{conversation_text}"
                )
            else:
                conv_prompt = (
                    "以下是一段群聊记录。请用中文提取其中值得记住的信息，"
                    "以要点列表输出（最多8条，每条以'- '开头）。\n"
                    "包含：重要话题、有价值的信息、谁说了什么值得记录的事。\n"
                    "格式：'- [昵称] 说了/提到了…' 或 '- 群里讨论了…'\n"
                    "忽略：打招呼、无实质内容的闲聊、重复性内容。\n\n"
                    f"对话记录：\n{conversation_text}"
                )

            summary_resp = await adapter.chat(
                [{"role": "user", "content": conv_prompt}],
                max_tokens=250,
            )
            summary = summary_resp.content.strip()
            if not summary:
                return

            person_facts = ""
            if is_private:
                person_prompt = (
                    "以下是一段私信对话记录。请只提取**对方（人类用户）**透露的个人信息，"
                    "以简洁要点列表输出（最多6条，每条以'- '开头）。\n\n"
                    "要提取的内容（关于对方的）：\n"
                    "  - 他/她的名字、职业、年龄、所在地等基本信息\n"
                    "  - 他/她表达的喜好、偏好、观点、情感\n"
                    "  - 他/她提到的重要事情、约定、请求\n\n"
                    "严格不要写的：\n"
                    "  - AI（小萌）自己的行为、能力、回答内容\n"
                    "  - 打招呼、泛泛的对话\n"
                    "  - 对方没有明确说出的推测\n\n"
                    "如果对话中对方几乎没透露个人信息，直接回复 SKIP。\n\n"
                    f"对话记录：\n{conversation_text}"
                )
                facts_resp = await adapter.chat(
                    [{"role": "user", "content": person_prompt}],
                    max_tokens=200,
                )
                facts = facts_resp.content.strip()
                if facts and facts.upper() != "SKIP" and len(facts) > 5:
                    person_facts = facts

            ids_to_delete = [r["id"] for r in to_compress]
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids_to_delete))})",
                ids_to_delete,
            )
            conn.execute(
                """INSERT INTO long_term_memory (session_key, content, memory_type, importance, created_at)
                   VALUES (?, ?, 'summary', 1, ?)""",
                (session_key, summary, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()

            now_str = datetime.now().strftime("%Y-%m-%d")
            if is_private:
                try:
                    qq = int(session_key.split(":", 1)[1])
                    identity = self._resolve_identity(qq)
                    mem_file = self._memory_dir / f"{identity}.md"
                    entry = f"\n## {now_str} 对话摘要\n\n{summary}\n"
                    if person_facts:
                        entry += f"\n### 了解到的信息\n\n{person_facts}\n"
                    with open(mem_file, "a", encoding="utf-8") as f:
                        f.write(entry)
                    logger.info(f"身份记忆文件已更新: memory/{identity}.md")
                except Exception as e:
                    logger.debug(f"写身份记忆文件失败: {e}")
            else:
                group_id_str = session_key.split(":", 1)[1] if ":" in session_key else session_key
                group_file = self._memory_dir / f"group_{group_id_str}.md"
                try:
                    now_str_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                    entry = f"\n## {now_str_ts}\n\n{summary}\n"
                    with open(group_file, "a", encoding="utf-8") as f:
                        f.write(entry)
                    logger.info(f"群记忆文件已更新: memory/group_{group_id_str}.md")
                except Exception as e:
                    logger.debug(f"写群记忆文件失败: {e}")

            logger.info(f"会话 {session_key} 记忆已压缩")

        except Exception as e:
            logger.error(f"记忆压缩失败: {e}")

    def _append_memory_md(self, session_key: str, summary: str) -> None:
        """将摘要追加到 data/persona/MEMORY.md。"""
        try:
            self._memory_md_path.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = f"\n## {now}  [{session_key}]\n\n{summary}\n"
            with open(self._memory_md_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"写 MEMORY.md 失败: {e}")

    def _load_person_memory(
        self, identity: str, sender_qq: int, exclude_session: str = ""
    ) -> str:
        """
        加载某人的跨对话、跨平台记忆。
        """
        parts: List[str] = []

        mem_file = self._memory_dir / f"{identity}.md"
        if mem_file.exists():
            content = mem_file.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)

        explicit = self._get_long_term_memory(f"user:{sender_qq}")
        if explicit:
            parts.append(explicit)

        private_sk = f"private:{sender_qq}"
        if private_sk != exclude_session:
            ltm = self._get_long_term_memory(private_sk)
            if ltm:
                parts.append(ltm)

        for sk in self._get_identity_sessions(identity):
            if sk in (exclude_session, private_sk):
                continue
            ltm = self._get_long_term_memory(sk)
            if ltm:
                parts.append(ltm)

        if private_sk != exclude_session:
            raw = self._get_recent_messages(private_sk, 12)
            if raw:
                lines = []
                for r in raw:
                    name = r.get("sender_name") or (
                        self._bot_name if r["role"] == "assistant" else "对方"
                    )
                    lines.append(f"{name}: {r['content'][:120]}")
                parts.append("（与此人的私信记录）\n" + "\n".join(lines))

        return "\n\n".join(parts)

    def _load_knowledge(self) -> str:
        """读取 data/memory/knowledge.md（通用知识库），限制长度避免撑爆 context。"""
        knowledge_file = self._memory_dir / "knowledge.md"
        if not knowledge_file.exists():
            return ""
        try:
            text = knowledge_file.read_text(encoding="utf-8").strip()
            if len(text) > self._knowledge_truncate:
                text = "…（更早的知识已省略）\n" + text[-self._knowledge_truncate:]
            return text
        except Exception:
            return ""