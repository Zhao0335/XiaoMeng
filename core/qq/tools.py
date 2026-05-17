"""
QQ Bot 工具系统
提供 bot 可以主动调用的工具：
  web_search / add_memory / search_memory / update_soul
  read_file / write_file / list_files（workspace 文件操作，write 需要 ADMIN+）
"""

import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .permissions import PermLevel as _PermLevel

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 工具 Schema（OpenAI function-calling 格式）
# ──────────────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "上网搜索信息。当需要查找最新新闻、实时数据、不确定的事实时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，尽量简洁准确"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_memory",
            "description": (
                "记住某件重要的事情。"
                "scope=\"person\"（默认）：记录关于这个人的信息（姓名/喜好/职业/重要事件），下次见到他/她时能想起来，跨聊天窗口有效。"
                "scope=\"conversation\"：记录关于当前对话主题的信息，仅在本聊天窗口有效。"
                "scope=\"knowledge\"：记录通用知识/世界知识，如动漫设定、乐队成员介绍、歌手背景等，所有对话都能用到。"
                "【重要】对方一旦透露了个人信息（哪怕只是名字、年级、喜好），立即用 scope=\"person\" 记下来！"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "【必填，字段名必须是 content】要记住的内容，用一句话描述清楚，包含主语（如「用户叫小明，大学生」）"
                    },
                    "scope": {
                        "type": "string",
                        "description": "person = 关于这个人（跨对话生效）；conversation = 关于当前对话；knowledge = 通用知识/世界知识（跨所有对话生效，如动漫设定、歌手信息等）",
                        "enum": ["person", "conversation", "knowledge"]
                    },
                    "importance": {
                        "type": "integer",
                        "description": "重要程度 1-3，1=普通，2=重要，3=非常重要",
                        "enum": [1, 2, 3]
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "搜索自己的记忆，回忆之前聊过的事情或这个人说过的话。会同时搜索关于这个人的记忆和当前对话的记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "想要搜索的关键词或描述"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_soul",
            "description": (
                "更新自己的 SOUL.md 进化区，记录真实的成长和新发现。"
                "适合用在：遇到了以前没想过的问题、某次对话让你有了新的认知、发现自己喜欢/不喜欢某件事。"
                "不要强行写，要真实。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "以「- 」开头的一两句话，说清楚是什么、为什么值得写进来"
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall_conversations",
            "description": (
                "回忆近期和其他人聊过的内容（跨群跨私聊）。仅主人和管理员可用。"
                "主人问「最近和谁聊了什么」「群里有没有人提过xxx」时使用。"
                "可以按关键词搜索，也可以查最近的所有对话记录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的关键词（为空时返回最近的对话记录）"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回最多多少条消息，默认 20",
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取 workspace（data/）下的任意文件。"
                "可以读 persona/SOUL.md、memory/owner.md、identity_links.json、skills/ 下的技能文件等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于 data/ 的路径，如 'persona/SOUL.md' 或 'identity_links.json'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "写入或修改 workspace（data/）下的文件。需要管理员或主人权限。"
                "可以用来：更新 identity_links.json 把某个 QQ 号关联到一个人、"
                "修改某人的记忆文件（memory/xxx.md）、更新 persona 文件等。"
                "修改 identity_links.json 后身份映射立即生效。"
                "path 留空时自动在 notes/ 下创建带时间戳的新文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于 data/ 的路径；留空则自动生成文件名（notes/时间戳.md）"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容（overwrite 模式）或追加的内容（append 模式）"
                    },
                    "mode": {
                        "type": "string",
                        "description": "overwrite（覆盖，默认）或 append（在末尾追加）",
                        "enum": ["overwrite", "append"]
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出 workspace（data/）某目录下的文件列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于 data/ 的目录路径，空字符串表示根目录"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "删除 workspace（data/）下的文件或空目录。需要管理员或主人权限。"
                "可以用来：删除过期的 skill、清理不需要的笔记、移除错误的记忆文件等。"
                "只能删 data/ 内的文件，不能删系统文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于 data/ 的路径，如 'skills/old_skill.md' 或 'notes/draft.md'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_voice",
            "description": (
                "合成并发送语音消息。适合：用户明确要求语音回复、朗读诗词/歌词、"
                "简短情感化的表达需要语音时。调用后会直接发送语音，无需再重复文字内容。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要合成为语音的文字内容，建议100字以内"
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "在服务器上执行 shell 命令。**仅主人可用。**"
                "可以用来：管理服务，查看日志，安装依赖，重启程序，查看系统状态等。"
                "返回命令的 stdout 和 stderr。超时 60 秒自动终止。"
                "工作目录为 XiaoMeng 项目根目录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令，如 'systemctl status nginx' 或 'pip install requests'"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数，默认 30，最大 60"
                    }
                },
                "required": ["command"]
            }
        }
    },
]

# 调用工具时展示给用户看的进度消息（None = 不展示）
TOOL_PROGRESS_MSG = {
    "web_search":           lambda args: f"让小萌查一下「{args.get('query', '')}」~",
    "send_voice":           lambda args: "（小萌合成语音中，稍等一下~）",
    "run_command":          lambda args: f"（小萌执行命令中：`{args.get('command', '')}` ~）",
    "write_file":           lambda args: f"（小萌写入 {args.get('path') or args.get('file_path', '文件')} ~）",
    "delete_file":          lambda args: f"（小萌删除 {args.get('path') or args.get('file_path', '文件')} ~）",
    "add_memory":           lambda args: None,
    "search_memory":        lambda args: None,
    "update_soul":          lambda args: None,
    "recall_conversations": lambda args: None,
    "read_file":            lambda args: None,
    "list_files":           lambda args: None,
}


# ──────────────────────────────────────────────────────────────
# 工具执行器
# ──────────────────────────────────────────────────────────────

class QQToolExecutor:
    """执行工具调用，返回结果字符串。"""

    def __init__(
        self,
        db_path: str,
        soul_path: Path,
        data_dir: Path,     # workspace 根目录（data/），沙箱范围
        session_key: str,
        sender_qq: int = 0,
        level=None,         # PermLevel，write_file 权限检查用
        identity: str = "", # canonical 身份名，记忆文件用
        proxy: str = "",    # web_search 代理
        napcat=None,        # NapCatClient，send_voice 需要
        tts=None,           # SoVITSTTS，send_voice 需要
        target_id: int = 0, # 发送目标（group_id 或 user_id）
        is_private: bool = False,
    ):
        self._db_path = db_path
        self._soul_path = soul_path
        self._data_dir = data_dir.resolve()
        self._memory_dir = data_dir / "memory"
        self._session_key = session_key
        self._sender_qq = sender_qq
        self._level = level
        self._identity = identity or (f"user_{sender_qq}" if sender_qq else "unknown")
        self._user_key = f"user:{sender_qq}" if sender_qq else session_key
        self._proxy = proxy
        self._napcat = napcat
        self._tts = tts
        self._target_id = target_id
        self._is_private = is_private

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        if tool_name == "web_search":
            return await self._web_search(arguments.get("query", ""))
        elif tool_name == "add_memory":
            # LLM 有时用各种字段名代替 content，逐一尝试
            content = (arguments.get("content")
                       or arguments.get("summary")
                       or arguments.get("text")
                       or arguments.get("note")
                       or arguments.get("value")
                       or arguments.get("fact")
                       or arguments.get("info", ""))
            # key+value 组合：拼成 "key: value"
            if not content and arguments.get("key") and arguments.get("value"):
                content = f"{arguments['key']}: {arguments['value']}"
            scope = arguments.get("scope", "person")
            if scope not in ("person", "conversation", "knowledge"):
                scope = "person"
            return self._add_memory(content, int(arguments.get("importance", 1)), scope)
        elif tool_name == "search_memory":
            return self._search_memory(arguments.get("query", ""))
        elif tool_name == "update_soul":
            content = arguments.get("content", "")
            # LLM 有时传 updates（列表）而不是 content（字符串），兼容处理
            if not content:
                updates = arguments.get("updates", [])
                if isinstance(updates, list):
                    parts = []
                    for u in updates:
                        if isinstance(u, dict):
                            parts.append(u.get("affirmation") or u.get("content") or u.get("text") or str(u))
                        elif isinstance(u, str):
                            parts.append(u)
                    content = "\n".join(p for p in parts if p)
                elif isinstance(updates, str):
                    content = updates
            return self._update_soul(content)
        elif tool_name == "recall_conversations":
            return self._recall_conversations(
                arguments.get("query", ""),
                int(arguments.get("limit", 20)),
            )
        elif tool_name == "read_file":
            path = arguments.get("path") or arguments.get("file_path", "")
            return self._read_file(path)
        elif tool_name == "write_file":
            # LLM 有时会传 file_path 而不是 path，兼容两种写法
            path = arguments.get("path") or arguments.get("file_path", "")
            return self._write_file(
                path,
                arguments.get("content", ""),
                arguments.get("mode", "overwrite"),
            )
        elif tool_name == "list_files":
            return self._list_files(arguments.get("path", ""))
        elif tool_name == "delete_file":
            path = arguments.get("path") or arguments.get("file_path", "")
            return self._delete_file(path)
        elif tool_name == "send_voice":
            return await self._send_voice(arguments.get("text", ""))
        elif tool_name == "run_command":
            return await self._run_command(
                arguments.get("command", ""),
                int(arguments.get("timeout", 30)),
            )
        else:
            return f"未知工具: {tool_name}"

    # ── web_search ──────────────────────────────────

    async def _web_search(self, query: str) -> str:
        if not query.strip():
            return "搜索词不能为空"
        try:
            from ddgs import DDGS
            import asyncio
            results = await asyncio.to_thread(_ddg_search, query, 4, self._proxy)
            if not results:
                return "没找到相关结果"
            lines = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")[:150]
                href = r.get("href", "")
                lines.append(f"**{title}**\n{body}\n{href}")
            return "\n\n".join(lines)
        except Exception as e:
            logger.warning(f"web_search 失败: {e}")
            return f"搜索失败: {e}"

    # ── add_memory ───────────────────────────────────

    def _add_memory(self, content: str, importance: int = 1, scope: str = "person") -> str:
        if not content.strip():
            return "内容不能为空"
        content = content.strip()
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d")

        if scope == "knowledge":
            # 通用知识：写 data/memory/knowledge.md + SQLite key=knowledge
            try:
                knowledge_file = self._memory_dir / "knowledge.md"
                if not knowledge_file.exists():
                    knowledge_file.write_text("# 小萌学到的知识\n\n", encoding="utf-8")
                with open(knowledge_file, "a", encoding="utf-8") as f:
                    f.write(f"- [{ts}] {content}\n")
            except Exception as e:
                return f"知识写入失败: {e}"
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO long_term_memory (session_key, content, memory_type, importance, created_at) VALUES (?, ?, 'knowledge', ?, ?)",
                    ("knowledge", content, importance, now.isoformat()),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return f"记住了（知识库）：{content}"

        elif scope == "person" and self._sender_qq:
            # 写到 data/memory/{identity}.md（对人的记忆，跨对话持久）
            try:
                mem_file = self._memory_dir / f"{self._identity}.md"
                line = f"- [{ts}] {content}\n"
                with open(mem_file, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                return f"记忆写入文件失败: {e}"
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO long_term_memory (session_key, content, memory_type, importance, created_at) VALUES (?, ?, 'person', ?, ?)",
                    (self._user_key, content, importance, now.isoformat()),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
        else:
            # 写到当前会话（群/私聊）的 SQLite 记忆
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO long_term_memory (session_key, content, memory_type, importance, created_at) VALUES (?, ?, 'explicit', ?, ?)",
                    (self._session_key, content, importance, now.isoformat()),
                )
                conn.commit()
                conn.close()
            except Exception as e:
                return f"记忆失败: {e}"

        return f"记住了：{content}"

    # ── search_memory ────────────────────────────────

    def _search_memory(self, query: str) -> str:
        if not query.strip():
            return "搜索词不能为空"
        like = f"%{query.strip()}%"
        lines = []
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            # 1. 长期记忆：当前会话 + 用户个人记忆 + 知识库
            keys = list({self._session_key, self._user_key, "knowledge"})
            placeholders = ",".join("?" * len(keys))
            c.execute(
                f"""SELECT content, session_key, memory_type, importance, created_at
                   FROM long_term_memory
                   WHERE session_key IN ({placeholders}) AND content LIKE ?
                   ORDER BY importance DESC, id DESC LIMIT 8""",
                (*keys, like),
            )
            for r in [dict(r) for r in c.fetchall()]:
                ts = (r.get("created_at") or "")[:10]
                if r["session_key"] == "knowledge":
                    tag = "（知识库）"
                elif r["session_key"] == self._user_key and self._user_key != self._session_key:
                    tag = "（关于ta）"
                else:
                    tag = ""
                lines.append(f"[{ts}]{tag} {r['content']}")

            # 2. 原始消息表：搜当前会话里小萌自己说过的话
            c.execute(
                """SELECT content, created_at FROM messages
                   WHERE session_key=? AND role='assistant' AND content LIKE ?
                   ORDER BY id DESC LIMIT 5""",
                (self._session_key, like),
            )
            for r in [dict(r) for r in c.fetchall()]:
                ts = (r.get("created_at") or "")[:10]
                lines.append(f"[{ts}]（小萌说过） {r['content'][:120]}")

            conn.close()
        except Exception as e:
            return f"记忆搜索失败: {e}"

        if not lines:
            return "没找到相关记忆"
        return "\n".join(lines)

    # ── update_soul ──────────────────────────────────

    def _update_soul(self, content: str) -> str:
        if not content.strip():
            return "内容不能为空"
        try:
            soul_text = self._soul_path.read_text(encoding="utf-8")
            evolving_end = soul_text.find("<!-- EVOLVING_END")
            if evolving_end == -1:
                return "SOUL.md 格式不对，找不到进化区标记"

            content = content.strip()
            if not content.startswith("- "):
                content = "- " + content

            now = datetime.now().strftime("%Y-%m-%d")
            insert = f"\n{content}  <!-- {now} -->\n"
            new_soul = soul_text[:evolving_end] + insert + soul_text[evolving_end:]
            self._soul_path.write_text(new_soul, encoding="utf-8")
            return f"SOUL.md 进化区已更新：{content}"
        except Exception as e:
            return f"更新失败: {e}"

    # ── recall_conversations ──────────────────────────

    def _recall_conversations(self, query="", limit: int = 20) -> str:
        query = str(query) if query else ""  # 防止 LLM 传 int
        # PermLevel.ADMIN == 1，用整数比较避免循环导入
        if self._level is None or int(self._level) < 1:
            return "没有权限查看对话记录（需要管理员或主人）"
        limit = max(1, min(limit, 100))
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            if query.strip():
                # 拆词：识别群/私聊类型词，剩余做内容关键词搜索
                raw_words = query.strip().split()
                session_prefix = None   # "group:" 或 "private:"
                kw_words = []
                for w in raw_words:
                    if w in ("群", "群聊", "group"):
                        session_prefix = "group:%"
                    elif w in ("私", "私聊", "私信", "private"):
                        session_prefix = "private:%"
                    else:
                        kw_words.append(w)

                # 构建 WHERE 子句
                where_parts = []
                params: list = []

                # session_key 过滤（可选）
                if session_prefix:
                    where_parts.append("session_key LIKE ?")
                    params.append(session_prefix)

                # 内容关键词（按词 OR，每词 content+sender_name）
                if kw_words:
                    kw_conds = []
                    for w in kw_words:
                        like = f"%{w}%"
                        kw_conds.append("(content LIKE ? OR sender_name LIKE ?)")
                        params.extend([like, like])
                    where_parts.append("(" + " OR ".join(kw_conds) + ")")

                if not where_parts:
                    where = "1"   # 不会走到这里，但做兜底
                elif len(where_parts) == 1:
                    where = where_parts[0]
                else:
                    where = " AND ".join(where_parts)

                params.append(limit)
                c.execute(
                    f"""SELECT session_key, role, sender_name, content, created_at
                       FROM messages
                       WHERE {where}
                       ORDER BY id DESC LIMIT ?""",
                    params,
                )
            else:
                c.execute(
                    """SELECT session_key, role, sender_name, content, created_at
                       FROM messages
                       ORDER BY id DESC LIMIT ?""",
                    (limit,),
                )
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            if not rows:
                return "没有找到相关对话记录"
            # 倒序排列（最旧在前），按 session 分组显示
            rows = list(reversed(rows))
            lines = []
            last_session = None
            for r in rows:
                sk = r["session_key"]
                if sk != last_session:
                    # 把 session_key 翻译成更可读的标题
                    if sk.startswith("group:"):
                        header = f"群聊 {sk[6:]}"
                    elif sk.startswith("private:"):
                        header = f"私聊 {sk[8:]}"
                    else:
                        header = sk
                    lines.append(f"\n# {header}：")
                    last_session = sk
                ts = (r.get("created_at") or "")[:16]
                name = r.get("sender_name") or ("小萌" if r["role"] == "assistant" else "?")
                lines.append(f"  [{ts}] {name}: {r['content'][:80]}")
            return "\n".join(lines)
        except Exception as e:
            return f"查询失败: {e}"

    # ── read_file ─────────────────────────────────────

    def _read_file(self, path: str) -> str:
        if not path:
            return "路径不能为空"
        try:
            target = self._resolve_workspace_path(path)
            if not target.exists():
                return f"文件不存在: {path}"
            if target.is_dir():
                return f"{path} 是目录，请用 list_files"
            content = target.read_text(encoding="utf-8")
            # 限制输出长度，避免撑爆 context
            if len(content) > 4000:
                content = content[:4000] + f"\n…（文件还有 {len(content)-4000} 字符，已截断）"
            return content
        except ValueError as e:
            return f"路径错误: {e}"
        except Exception as e:
            return f"读取失败: {e}"

    # ── write_file ────────────────────────────────────

    def _write_file(self, path: str, content: str, mode: str = "overwrite") -> str:
        # 权限检查：只有管理员和主人可以写文件（PermLevel.ADMIN == 1）
        if self._level is None or int(self._level) < 1:
            return "没有权限修改文件（需要管理员或主人）"
        # 路径为空 → 自动生成文件名（notes/YYYYMMDD_HHMMSS.md）
        if not path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"notes/{ts}.md"
        try:
            target = self._resolve_workspace_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if mode == "append":
                with open(target, "a", encoding="utf-8") as f:
                    f.write(content)
            else:
                target.write_text(content, encoding="utf-8")
            logger.info(f"write_file: {path} ({mode}) by {self._sender_qq}")
            return f"已写入 {path}"
        except ValueError as e:
            return f"路径错误: {e}"
        except Exception as e:
            return f"写入失败: {e}"

    # ── list_files ────────────────────────────────────

    def _list_files(self, path: str = "") -> str:
        try:
            target = self._resolve_workspace_path(path) if path else self._data_dir
            if not target.exists():
                return f"目录不存在: {path or '(root)'}"
            if not target.is_dir():
                return f"{path} 不是目录"
            items = []
            for item in sorted(target.iterdir()):
                if item.is_dir():
                    items.append(f"[dir]  {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"[file] {item.name}  ({size} bytes)")
            return "\n".join(items) if items else "（空目录）"
        except ValueError as e:
            return f"路径错误: {e}"
        except Exception as e:
            return f"列出失败: {e}"

    # ── delete_file ───────────────────────────────────

    def _delete_file(self, path: str) -> str:
        if self._level is None or int(self._level) < 1:
            return "没有权限删除文件（需要管理员或主人）"
        if not path:
            return "路径不能为空"
        # 保护核心文件不被误删
        PROTECTED = {"persona/SOUL.md", "identity_links.json", "qq_bot.db"}
        if path.strip("/") in PROTECTED:
            return f"禁止删除核心文件: {path}"
        try:
            target = self._resolve_workspace_path(path)
            if not target.exists():
                return f"文件不存在: {path}"
            if target.is_dir():
                # 只允许删空目录
                if any(target.iterdir()):
                    return f"目录非空，无法删除: {path}（请先删除里面的文件）"
                target.rmdir()
            else:
                target.unlink()
            logger.info(f"delete_file: {path} by {self._sender_qq}")
            return f"已删除 {path}"
        except ValueError as e:
            return f"路径错误: {e}"
        except Exception as e:
            return f"删除失败: {e}"

    # ── send_voice ────────────────────────────────────

    async def _send_voice(self, text: str) -> str:
        import base64
        if not text.strip():
            return "语音内容不能为空"
        if not self._tts:
            return "TTS 服务未配置，无法发送语音"
        if not self._napcat or not self._target_id:
            return "发送目标未配置，无法发送语音"
        audio_bytes = await self._tts.synthesize(text)
        if not audio_bytes:
            return "语音合成失败，请稍后再试"
        b64 = base64.b64encode(audio_bytes).decode()
        cq = f"[CQ:record,file=base64://{b64}]"
        try:
            if self._is_private:
                await self._napcat.send_private_msg(self._target_id, cq)
            else:
                await self._napcat.send_group_msg(self._target_id, cq)
            return "✅ 语音消息已发送"
        except Exception as e:
            return f"语音发送失败: {e}"

    # ── run_command ───────────────────────────────────

    async def _run_command(self, command: str, timeout: int = 30) -> str:
        if self._level is None or int(self._level) < 2:  # 2 == PermLevel.OWNER
            return "没有权限执行命令（仅主人可用）"
        if not command.strip():
            return "命令不能为空"
        timeout = max(1, min(timeout, 60))
        import asyncio, subprocess
        # 工作目录：项目根（data/ 的上一级）
        cwd = str(self._data_dir.parent)
        logger.info(f"run_command by {self._sender_qq}: {command!r}")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return f"命令超时（>{timeout}s）已终止"
            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()
            rc = proc.returncode
            parts = []
            if out:
                parts.append(out)
            if err:
                parts.append(f"[stderr]\n{err}")
            result = "\n".join(parts) if parts else "（无输出）"
            # 回复太长时截断
            if len(result) > 3000:
                result = result[:3000] + f"\n…（输出过长，已截断，共 {len(result)} 字符）"
            return f"返回码: {rc}\n{result}"
        except Exception as e:
            return f"执行失败: {e}"

    # ── workspace 路径解析（防穿越）─────────────────────

    def _resolve_workspace_path(self, path: str) -> Path:
        resolved = (self._data_dir / path).resolve()
        if not str(resolved).startswith(str(self._data_dir)):
            raise ValueError(f"路径越界，只能访问 data/ 目录内的文件: {path}")
        return resolved


# ──────────────────────────────────────────────────────────────
# Skill 加载（OpenClaw SKILL.md 格式）
# ──────────────────────────────────────────────────────────────

def load_skills_prompt(skills_dir: str) -> str:
    """
    扫描 data/skills/ 下的技能文件，构建注入 system prompt 的技能段落。

    支持两种布局：
      - 平铺 .md 文件（推荐）：data/skills/skill-name.md
      - 子目录格式：data/skills/skill-name/SKILL.md

    frontmatter 可选。有 frontmatter 则提取 name/description 构建索引；
    无 frontmatter 则用文件名作为 name。每个技能的完整正文都会附上。
    """
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        return ""

    skills: List[Tuple[str, str, str]] = []  # (name, desc, body)

    def _collect(md_file: Path) -> None:
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            return
        name, desc, body = _parse_skill(text, md_file.stem)
        skills.append((name, desc, body))

    for item in sorted(skills_path.iterdir()):
        if item.is_file() and item.suffix == ".md":
            _collect(item)
        elif item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                _collect(skill_md)

    if not skills:
        return ""

    index_lines = [f"- **{n}**: {d}" if d else f"- **{n}**" for n, d, _ in skills]
    body_sections = [f"### {n}\n\n{b}" for n, _, b in skills]

    return (
        "## 可用技能\n\n"
        + "\n".join(index_lines)
        + "\n\n---\n\n"
        + "\n\n---\n\n".join(body_sections)
    )


def _parse_skill(text: str, stem: str) -> Tuple[str, str, str]:
    """解析技能文件，返回 (name, description, body_without_frontmatter)。"""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return stem, "", text.strip()
    fm = m.group(1)
    body = text[m.end():].strip()
    name_m = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    desc_m = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else stem
    desc = desc_m.group(1).strip() if desc_m else ""
    return name, desc, body


def _parse_skill_meta(text: str) -> Tuple[str, str]:
    """从 SKILL.md frontmatter 提取 name 和 description（向后兼容）。"""
    name, desc, _ = _parse_skill(text, "")
    return name, desc


# ──────────────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────────────

def _ddg_search(query: str, max_results: int = 4, proxy: str = "") -> List[Dict]:
    """同步 DuckDuckGo 搜索，用 asyncio.to_thread 包装后调用。"""
    from ddgs import DDGS
    kwargs = {"proxy": proxy} if proxy else {}
    with DDGS(**kwargs) as ddgs:
        return list(ddgs.text(query, max_results=max_results))


def parse_tool_calls(response_content: str) -> List[Dict]:
    """
    兜底解析：如果模型没走 function-calling 而是在文本里输出了 JSON，
    尝试提取 tool_call 结构。
    正常情况下不会用到这个，OpenAI 格式的 tool_calls 由 adapter 直接解析。
    """
    results = []
    for m in re.finditer(r'\{"tool":\s*"(\w+)".*?\}', response_content, re.DOTALL):
        try:
            obj = json.loads(m.group())
            if "tool" in obj and "args" in obj:
                results.append({"name": obj["tool"], "arguments": obj["args"]})
        except Exception:
            pass
    return results
