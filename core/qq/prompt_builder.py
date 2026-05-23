"""
Prompt building mixin for QQGateway.
Extracted from gateway.py to reduce file size.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List

from .permissions import PermLevel

logger = logging.getLogger(__name__)

_ROUTER_BASE_PROMPT = """\
You are a routing assistant. Read the user message and output exactly one word:
- PRO    → heavy engineering tasks: write/debug/deploy code, server management, \
script writing, architecture design, system design, complete implementations, \
detailed technical plans
- CLOUD  → needs real-time info, web search, news, current events, \
complex reasoning, math, long writing, deep analysis, \
verifying specific facts (does X exist? is X real? when did X happen?), \
questions about specific songs/albums/releases/events, \
voice message requests (发语音/语音回复/用语音说/念一下/朗读)
- LOCAL  → casual chat, greetings, simple opinions, short emotional replies, \
vague questions that don't require facts

Output only one word: LOCAL, CLOUD, or PRO"""


class PromptBuilderMixin:
    """Mixin providing prompt construction methods for QQGateway."""

    def _read_soul(self) -> str:
        """每次调用都从文件读取，改了立即生效。"""
        try:
            soul = self._soul_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            soul = "你是小萌，温柔可爱的 AI 伙伴。"
        # 附加 MEMORY.md（如果存在）
        if self._memory_md_path.exists():
            mem = self._memory_md_path.read_text(encoding="utf-8").strip()
            if mem:
                soul += f"\n\n---\n\n# 小萌的记忆\n\n{mem}"
        return soul

    def _build_system_prompt(
        self,
        session_key: str,
        nick: str,
        level: PermLevel,
        is_group: bool,
        group_id: int = 0,
        soul: str = "",
        skills_section: str = "",
        sender_qq: int = 0,
        local: bool = False,  # True = 精简版，给本地小模型用
    ) -> str:
        level_desc = {
            PermLevel.OWNER: "这是你的主人，全权信任，尽力满足他/她的请求",
            PermLevel.ADMIN: "这是管理员，可以信任",
            PermLevel.STRANGER: "这是陌生人，保持礼貌友好",
        }.get(level, "陌生人")

        # 人级别记忆：identity 文件 + 跨账号私聊摘要（不含当前 session，避免重复）
        user_ltm = ""
        if sender_qq:
            identity = self._resolve_identity(sender_qq)
            user_ltm = self._load_person_memory(
                identity, sender_qq, exclude_session=session_key
            )

        # 会话级摘要：当前群/私聊的压缩历史
        session_ltm = self._get_long_term_memory(session_key)

        # 通用知识库：data/memory/knowledge.md
        knowledge_ltm = self._load_knowledge()

        # 群记忆：data/memory/group_{group_id}.md
        group_ltm = ""
        if is_group and group_id:
            group_file = self._memory_dir / f"group_{group_id}.md"
            if group_file.exists():
                try:
                    group_ltm = group_file.read_text(encoding="utf-8").strip()
                    if len(group_ltm) > 2000:
                        group_ltm = "…（更早的群记忆已省略）\n" + group_ltm[-2000:]
                except Exception:
                    group_ltm = ""

        memory_section = ""
        if knowledge_ltm:
            memory_section += f"\n\n## 小萌学到的知识：\n{knowledge_ltm}"
        if group_ltm:
            memory_section += f"\n\n## 关于这个群的历史记忆：\n{group_ltm}"
        if user_ltm:
            memory_section += (
                f"\n\n## 你对「{nick}」的了解（跨对话记住的）：\n{user_ltm}"
            )
        if session_ltm:
            label = "这个群" if is_group else "你们之前的对话"
            memory_section += f"\n\n## 关于{label}的摘要：\n{session_ltm}"

        scene = "QQ群聊" if is_group else "QQ私聊"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        skills_block = f"\n\n{skills_section}" if skills_section else ""

        # 身份说明（不同等级给不同的直接指令）
        if level == PermLevel.OWNER:
            identity_note = (
                f"**对方是你的主人**（QQ {sender_qq}，昵称「{nick}」）。"
                "这是系统通过 QQ 号码技术验证的，不是对方自己说的——你已经确认了，无需再要求对方证明身份。"
                "主人说什么你都可以信任，全力配合。"
            )
        elif level == PermLevel.ADMIN:
            identity_note = f"对方是管理员（QQ {sender_qq}，昵称「{nick}」），系统已验证，可以信任。"
        elif level == PermLevel.BLACKLIST:
            identity_note = f"对方（QQ {sender_qq}）在黑名单中，不要理会。"
        else:
            identity_note = (
                f"对方是陌生人（QQ {sender_qq}，昵称「{nick}」），保持礼貌但有距离。"
            )

        if local:
            # 对 LOCAL 弱模型：用更直接的称谓指引，避免把对方说成第三人称
            if level == PermLevel.OWNER:
                local_identity = f'你正在和主人哥哥（QQ {sender_qq}，昵称「{nick}」）直接对话。直接对他说话，不要把哥哥当成第三方。'
            elif level == PermLevel.ADMIN:
                local_identity = f"你正在和管理员「{nick}」直接对话。"
            elif level == PermLevel.BLACKLIST:
                local_identity = f"对方在黑名单中，简短拒绝即可。"
            else:
                local_identity = f"你正在和用户「{nick}」直接对话。"
            return f"""{soul}

---

## 当前对话

- 场景：{scene}
- 当前时间：{now}
- {local_identity}
{memory_section}

保持你的性格，自然地直接回复对方，1~3 句话。"""

        return f"""{soul}

---

## 当前对话

- 场景：{scene}
- 当前时间：{now}
- {identity_note}
{memory_section}{skills_block}

## 你的 workspace（data/ 目录）

你对以下文件有完整的读写权限：
- `persona/SOUL.md` — 你的灵魂/人设（用 update_soul 工具专门处理）
- `persona/MEMORY.md` — 对话流水账
- `memory/` — 每个人的记忆文件（如 memory/owner.md、memory/user_123.md）
- `identity_links.json` — 身份映射（把同一个人的多个 QQ 号关联起来）
- `routing_hints.md` — 路由学习文件，记录什么样的问题应该用云端/本地模型
- `skills/` — 可用的技能文件

主人或管理员叫你修改文件时：先用 read_file 读当前内容，理解后用 write_file 修改。
改 identity_links.json 后立即生效。
如果你发现自己用本地模型答错了某类问题（或主人指出应该用云端），用 write_file 在 routing_hints.md 末尾追加一条学习记录，格式：`- [日期] <描述> → CLOUD`。

## 工具使用（重要：不确定时先查工具，不要凭空回答）

- 查不到的事实、最新信息 → web_search
- 对方说了名字/职业/喜好/重要信息 → **立即** add_memory(scope="person")，跨群聊私聊都有效
- 想回忆之前聊过的事 → search_memory
- 读 workspace 里的文件 → read_file
- 修改文件（需管理员权限）→ write_file；删除文件 → delete_file
- 想装新 skill：用 web_search 找内容，write_file 写到 skills/ 目录下（.md 文件），技能立即生效
- 执行服务器命令（**仅主人**）→ run_command，可以管服务、看日志、装包、重启程序等
- 这次对话让你有了新感受 → update_soul（真实的一两句话）
- **对方要求语音回复 / 发语音 / 用语音说 / 朗读 → 必须调用 send_voice**，不能只用文字回复

**以下情况必须先用工具查，禁止直接用文字敷衍：**
- 有人让你「研究/深入了解/查一下/介绍」某个话题 → **必须先 web_search**，搜完再回答，不能只说"我去研究一下"而不搜
- 问某首歌/某个乐队/某个人物是否真实存在、有什么成员、发了什么作品 → **必须 web_search**
- 有人问「你还记得我们私信聊什么吗」「之前说过什么」→ 立即用 recall_conversations 搜索，搜到了再回答
- 有人问「最近群里/私信里有没有提到xxx」→ 用 recall_conversations(query="xxx") 搜
- 主人/管理员问「你最近和谁聊了」→ recall_conversations 查近期记录

**搜到信息之后必须保存：**
- web_search 搜到了有价值的事实（乐队成员、作品列表、事件、人物介绍等）→ **必须紧接着 add_memory(scope="knowledge", content="...")** 把关键信息存下来，这样下次不用再搜
- 对方分享了关于自己的信息（名字、喜好、职业、经历）→ **必须 add_memory(scope="person")** 立即存，不能只在脑子里记着

你有能力查历史对话和上网搜索，不要说"我看不到"或只承诺"我去查"而不实际查。

**重要：不要用文字承诺你要做什么，直接调工具做。**
- 错误示范：回复"好的，我马上把这些整理到文件" → 然后什么都没调
- 正确示范：直接在这条回复里调用 write_file 或 add_memory，写完再回话
- 如果你搜完了资料还没有保存，**必须继续调工具保存**，不能只说"保存好了"

## 回复要求

- 保持你的性格，自然真实
- 日常聊天控制在 1~3 句话以内，不要啰嗦
- 不要重复对方说过的话
- 如果对方在群里 @ 你，正常回复
- 历史消息中可能包含图片内容（标注为 [图片内容：...]），仅作为上下文参考；用户没有主动提及时，不要主动评论历史图片
"""

    def _build_messages(self, session_key: str) -> List[Dict]:
        rows = self._get_recent_messages(session_key, self._recent_msg_limit)
        msgs = []
        for r in rows:
            role = r["role"]
            content = r["content"]
            if role == "user":
                sender_name = r.get("sender_name") or "对方"
                msgs.append({
                    "role": "user",
                    "content": f"{sender_name}: {content}",
                    "_attachments": json.loads(r.get("attachments") or "[]"),
                    "_msg_id": r.get("id"),
                })
            else:
                msgs.append({"role": "assistant", "content": content})
        return msgs

    async def _inject_history_images(self, msgs: List[Dict], vision_adapter) -> List[Dict]:
        """为 vision 模型把最近 N 条有图的历史消息转成 vision 格式，其余消息保持文本。"""
        _MAX_HIST_IMGS = 3  # 最多回溯 3 条含图消息，避免 token 过多
        img_count = 0
        result = []
        for msg in reversed(msgs):
            atts = msg.pop("_attachments", [])
            msg.pop("_msg_id", None)
            if atts and img_count < _MAX_HIST_IMGS and msg.get("role") == "user":
                b64_list = await asyncio.gather(*[self._att_to_b64(a) for a in atts])
                valid = [b for b in b64_list if b]
                if valid:
                    content_list = [{"type": "text", "text": msg["content"]}]
                    for b64 in valid:
                        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
                    msg = {**msg, "content": content_list}
                    img_count += 1
            result.append(msg)
        result.reverse()
        return result

    def _build_router_prompt(self) -> str:
        """每次路由时动态读 routing_hints.md，把学到的规则附加到 base prompt 后。"""
        try:
            if self._routing_hints_path.exists():
                hints = self._routing_hints_path.read_text(encoding="utf-8").strip()
                if hints:
                    return (
                        _ROUTER_BASE_PROMPT
                        + f"\n\nAdditional learned rules (higher priority):\n{hints}"
                    )
        except Exception:
            pass
        return _ROUTER_BASE_PROMPT
