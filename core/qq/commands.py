"""
QQ 管理命令解析器
主人/管理员可以通过 QQ 私聊或群聊发送命令来管理 bot

命令前缀 /
陌生人发命令：静默忽略
"""

import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .permissions import QQPermissionManager, PermLevel
    from .napcat import NapCatClient

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    success: bool
    reply: str
    action: Optional[str] = None


class QQCommandParser:
    """
    解析并执行管理命令。
    所有命令返回 CommandResult，调用方负责发送回复。
    """

    COMMANDS = {
        "/管理员":       ("owner", "grant_admin",      "用法: /管理员 {QQ号}"),
        "/取消管理员":   ("owner", "revoke_admin",     "用法: /取消管理员 {QQ号}"),
        "/拉黑":         ("admin", "blacklist",         "用法: /拉黑 {QQ号}"),
        "/取消拉黑":     ("owner", "unblacklist",       "用法: /取消拉黑 {QQ号}"),
        "/同意好友":     ("owner", "approve_friend",    "用法: /同意好友 {QQ号}"),
        "/拒绝好友":     ("owner", "reject_friend",     "用法: /拒绝好友 {QQ号}"),
        "/待处理好友":   ("owner", "list_friend_req",   ""),
        "/同意入群":     ("owner", "approve_group",     "用法: /同意入群 {群号}"),
        "/拒绝入群":     ("owner", "reject_group",      "用法: /拒绝入群 {群号}"),
        "/待处理入群":   ("owner", "list_group_inv",    ""),
        "/管理员列表":   ("owner", "list_admins",       ""),
        "/黑名单":       ("owner", "list_blacklist",    ""),
        "/重置记忆":     ("admin", "reset_memory",      ""),
        "/帮助":         ("admin", "help",              ""),
    }

    def __init__(
        self,
        perm: "QQPermissionManager",
        napcat: "NapCatClient",
        db_path: str,
    ):
        self._perm = perm
        self._napcat = napcat
        self._db_path = db_path

    async def handle(
        self,
        text: str,
        sender_qq: int,
        session_key: str,     # "private:{qq}" 或 "group:{gid}"
    ) -> Optional[CommandResult]:
        """
        解析命令并执行。
        非命令消息返回 None；无权限静默返回空结果。
        """
        text = text.strip()
        if not text.startswith("/"):
            return None

        # 匹配命令名
        matched_cmd = None
        matched_args = ""
        for cmd in sorted(self.COMMANDS.keys(), key=len, reverse=True):
            if text == cmd or text.startswith(cmd + " "):
                matched_cmd = cmd
                matched_args = text[len(cmd):].strip()
                break

        if not matched_cmd:
            return None  # 未知命令，当普通消息处理

        min_level_str, action, usage = self.COMMANDS[matched_cmd]
        level = self._perm.get_level(sender_qq)

        # 权限检查
        from .permissions import PermLevel
        required = PermLevel.OWNER if min_level_str == "owner" else PermLevel.ADMIN
        if level < required:
            # 陌生人/黑名单静默忽略（返回 None 让 gateway 不回复）
            return None

        return await self._dispatch(action, matched_args, sender_qq, session_key, usage)

    async def _dispatch(
        self,
        action: str,
        args: str,
        sender_qq: int,
        session_key: str,
        usage: str,
    ) -> CommandResult:
        if action == "grant_admin":
            return await self._grant_admin(args, sender_qq)
        elif action == "revoke_admin":
            return await self._revoke_admin(args, sender_qq)
        elif action == "blacklist":
            return await self._blacklist(args, sender_qq)
        elif action == "unblacklist":
            return await self._unblacklist(args, sender_qq)
        elif action == "approve_friend":
            return await self._handle_friend(args, sender_qq, approve=True)
        elif action == "reject_friend":
            return await self._handle_friend(args, sender_qq, approve=False)
        elif action == "list_friend_req":
            return self._list_friend_requests()
        elif action == "approve_group":
            return await self._handle_group_invite(args, approve=True)
        elif action == "reject_group":
            return await self._handle_group_invite(args, approve=False)
        elif action == "list_group_inv":
            return self._list_group_invites()
        elif action == "list_admins":
            return self._list_admins()
        elif action == "list_blacklist":
            return self._list_blacklist()
        elif action == "reset_memory":
            return self._reset_memory(session_key)
        elif action == "help":
            return self._help()
        return CommandResult(False, "未知操作")

    # ──────────────────────────────────────────────
    # 具体命令实现
    # ──────────────────────────────────────────────

    async def _grant_admin(self, args: str, by_qq: int) -> CommandResult:
        qq = _parse_qq(args)
        if not qq:
            return CommandResult(False, "请输入有效的 QQ 号，例如: /管理员 123456")
        nick = await self._get_nick(qq)
        is_new = self._perm.grant_admin(qq, by_qq, nick)
        if not is_new:
            return CommandResult(True, f"✅ {nick}({qq}) 已经是管理员了")
        return CommandResult(True, f"✅ 已将 {nick}({qq}) 设为管理员", action="grant_admin")

    async def _revoke_admin(self, args: str, by_qq: int) -> CommandResult:
        qq = _parse_qq(args)
        if not qq:
            return CommandResult(False, "请输入有效的 QQ 号")
        ok = self._perm.revoke_admin(qq, by_qq)
        if not ok:
            return CommandResult(False, f"❌ {qq} 不在管理员列表里")
        return CommandResult(True, f"✅ 已撤销 {qq} 的管理员权限", action="revoke_admin")

    async def _blacklist(self, args: str, by_qq: int) -> CommandResult:
        qq = _parse_qq(args)
        if not qq:
            return CommandResult(False, "请输入有效的 QQ 号")
        if self._perm.is_owner(qq):
            return CommandResult(False, "❌ 不能拉黑主人")
        nick = await self._get_nick(qq)
        self._perm.add_blacklist(qq, by_qq, nick)
        return CommandResult(True, f"✅ 已将 {nick}({qq}) 加入黑名单，后续消息将被忽略", action="blacklist")

    async def _unblacklist(self, args: str, by_qq: int) -> CommandResult:
        qq = _parse_qq(args)
        if not qq:
            return CommandResult(False, "请输入有效的 QQ 号")
        ok = self._perm.remove_blacklist(qq, by_qq)
        if not ok:
            return CommandResult(False, f"❌ {qq} 不在黑名单里")
        return CommandResult(True, f"✅ 已将 {qq} 移出黑名单", action="unblacklist")

    async def _handle_friend(self, args: str, by_qq: int, approve: bool) -> CommandResult:
        qq = _parse_qq(args)
        if not qq:
            return CommandResult(False, "请输入有效的 QQ 号")
        row = self._get_pending_friend(qq)
        if not row:
            return CommandResult(False, f"❌ 未找到 {qq} 的待处理好友申请")
        try:
            await self._napcat.set_friend_add_request(row["flag"], approve)
            self._resolve_friend_request(row["flag"], "approved" if approve else "rejected")
            action_str = "同意" if approve else "拒绝"
            nick = row.get("requester_nick") or str(qq)
            return CommandResult(
                True,
                f"✅ 已{action_str} {nick}({qq}) 的好友申请",
                action="approve_friend" if approve else "reject_friend",
            )
        except Exception as e:
            return CommandResult(False, f"❌ 操作失败: {e}")

    async def _handle_group_invite(self, args: str, approve: bool) -> CommandResult:
        group_id = _parse_qq(args)  # 群号和 QQ 号都是数字，复用同一个解析函数
        if not group_id:
            return CommandResult(False, "请输入有效的群号，例如: /同意入群 123456789")
        row = self._get_pending_group_invite(group_id)
        if not row:
            return CommandResult(False, f"❌ 未找到群 {group_id} 的待处理邀请（可能已过期）")
        try:
            await self._napcat.set_group_add_request(row["flag"], row["sub_type"] or "invite", approve)
            self._resolve_group_invite(row["flag"], "approved" if approve else "rejected")
            action_str = "同意" if approve else "拒绝"
            return CommandResult(True, f"✅ 已{action_str}加入群 {group_id} 的邀请")
        except Exception as e:
            return CommandResult(False, f"❌ 操作失败: {e}")

    def _list_group_invites(self) -> CommandResult:
        rows = self._get_all_pending_group_invites()
        if not rows:
            return CommandResult(True, "📋 当前没有待处理的入群邀请")
        lines = [f"📋 待处理入群邀请（共 {len(rows)} 条）："]
        for i, r in enumerate(rows, 1):
            group_name = r.get("group_name") or "未知群名"
            inviter = r.get("inviter_qq") or "未知"
            lines.append(f"  {i}. {group_name}（群号 {r['group_id']}），邀请人：{inviter}")
        lines.append("\n回复 /同意入群 {群号} 或 /拒绝入群 {群号} 来处理")
        return CommandResult(True, "\n".join(lines))

    def _list_friend_requests(self) -> CommandResult:
        rows = self._get_all_pending_friends()
        if not rows:
            return CommandResult(True, "📋 当前没有待处理的好友申请")
        lines = [f"📋 待处理好友申请（共 {len(rows)} 条）："]
        for i, r in enumerate(rows, 1):
            nick = r.get("requester_nick") or "未知"
            comment = r.get("comment") or "无"
            lines.append(f"  {i}. {nick}({r['requester_qq']}) - 留言: {comment}")
        lines.append("\n回复 /同意好友 {QQ号} 或 /拒绝好友 {QQ号} 来处理")
        return CommandResult(True, "\n".join(lines))

    def _list_admins(self) -> CommandResult:
        admins = self._perm.list_admins()
        if not admins:
            return CommandResult(True, "📋 当前没有管理员")
        lines = [f"📋 管理员列表（共 {len(admins)} 人）："]
        for a in admins:
            nick = a.get("nickname") or "未知"
            lines.append(f"  • {nick}({a['qq']})")
        return CommandResult(True, "\n".join(lines))

    def _list_blacklist(self) -> CommandResult:
        bl = self._perm.list_blacklist()
        if not bl:
            return CommandResult(True, "📋 黑名单为空")
        lines = [f"📋 黑名单（共 {len(bl)} 人）："]
        for b in bl:
            nick = b.get("nickname") or "未知"
            lines.append(f"  • {nick}({b['qq']})")
        return CommandResult(True, "\n".join(lines))

    def _reset_memory(self, session_key: str) -> CommandResult:
        try:
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute("DELETE FROM messages WHERE session_key = ?", (session_key,))
            c.execute("DELETE FROM long_term_memory WHERE session_key = ?", (session_key,))
            conn.commit()
            conn.close()
            return CommandResult(True, "✅ 已清除当前会话的记忆", action="reset_memory")
        except Exception as e:
            return CommandResult(False, f"❌ 清除记忆失败: {e}")

    def _help(self) -> CommandResult:
        lines = [
            "📖 可用命令：",
            "  /管理员 {QQ}      - 授予管理员",
            "  /取消管理员 {QQ}  - 撤销管理员",
            "  /拉黑 {QQ}        - 加入黑名单",
            "  /取消拉黑 {QQ}    - 移出黑名单",
            "  /同意好友 {QQ}    - 同意好友申请",
            "  /拒绝好友 {QQ}    - 拒绝好友申请",
            "  /待处理好友       - 查看待审好友申请",
            "  /同意入群 {群号}  - 同意入群邀请",
            "  /拒绝入群 {群号}  - 拒绝入群邀请",
            "  /待处理入群       - 查看待审入群邀请",
            "  /管理员列表       - 查看管理员",
            "  /黑名单           - 查看黑名单",
            "  /重置记忆         - 清除当前会话记忆",
        ]
        return CommandResult(True, "\n".join(lines))

    # ──────────────────────────────────────────────
    # 辅助
    # ──────────────────────────────────────────────

    async def _get_nick(self, qq: int) -> str:
        info = await self._napcat.get_stranger_info(qq)
        return info.get("nickname") or str(qq)

    def _get_pending_friend(self, qq: int) -> Optional[dict]:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM pending_friend_requests WHERE requester_qq=? AND status='pending'",
                (qq,),
            )
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    def _get_all_pending_friends(self) -> list:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM pending_friend_requests WHERE status='pending' ORDER BY received_at DESC LIMIT 20"
            )
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def _resolve_friend_request(self, flag: str, status: str) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE pending_friend_requests SET status=? WHERE flag=?", (status, flag)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _get_pending_group_invite(self, group_id: int) -> Optional[dict]:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM pending_group_invites WHERE group_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
                (group_id,),
            )
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    def _get_all_pending_group_invites(self) -> list:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM pending_group_invites WHERE status='pending' ORDER BY received_at DESC LIMIT 20"
            )
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def _resolve_group_invite(self, flag: str, status: str) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE pending_group_invites SET status=? WHERE flag=?", (status, flag)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _parse_qq(text: str) -> Optional[int]:
    """从文本中提取 QQ 号（5~12位数字）"""
    m = re.search(r'\b(\d{5,12})\b', text)
    if m:
        return int(m.group(1))
    return None
