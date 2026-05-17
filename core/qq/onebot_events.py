"""
OneBot v11 事件解析
将 NapCat 推送的原始 JSON 解析为类型化的事件对象
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


# ──────────────────────────────────────────────────────────
# 数据类
# ──────────────────────────────────────────────────────────

@dataclass
class Sender:
    user_id: int
    nickname: str = ""
    card: str = ""       # 群名片
    role: str = "member" # owner / admin / member


@dataclass
class PrivateMsgEvent:
    """私聊消息"""
    time: int
    self_id: int
    user_id: int
    message_id: int
    raw_message: str
    message: str          # 纯文本内容
    sender: Sender
    sub_type: str = "friend"
    attachments: List[Dict] = field(default_factory=list)  # 非文本消息段


@dataclass
class GroupMsgEvent:
    """群消息"""
    time: int
    self_id: int
    group_id: int
    user_id: int
    message_id: int
    raw_message: str
    message: str
    sender: Sender
    at_bot: bool = False
    sub_type: str = "normal"
    attachments: List[Dict] = field(default_factory=list)


@dataclass
class FriendRequestEvent:
    """好友申请"""
    time: int
    self_id: int
    user_id: int
    comment: str
    flag: str


@dataclass
class GroupInviteEvent:
    """被邀请进群 / 申请加群"""
    time: int
    self_id: int
    group_id: int
    user_id: int
    comment: str
    flag: str
    sub_type: str  # "invite" / "add"


@dataclass
class NoticeEvent:
    """通知事件（加好友成功、群成员变动等）"""
    time: int
    self_id: int
    notice_type: str
    raw: Dict[str, Any] = field(default_factory=dict)


Event = Union[PrivateMsgEvent, GroupMsgEvent, FriendRequestEvent, GroupInviteEvent, NoticeEvent]


# ──────────────────────────────────────────────────────────
# 解析函数
# ──────────────────────────────────────────────────────────

def parse_event(raw: Dict[str, Any]) -> Optional[Event]:
    """
    将 NapCat 推送的原始字典解析为类型化事件。
    无法识别的事件返回 None。

    兼容说明：llbot 7.x 的消息事件不含 post_type，
    直接通过 message_type / request_type / notice_type 字段判断。
    """
    post_type = raw.get("post_type")

    # llbot 兼容：没有 post_type 时，根据其他字段推断
    if not post_type:
        if "message_type" in raw:
            post_type = "message"
        elif "request_type" in raw:
            post_type = "request"
        elif "notice_type" in raw:
            post_type = "notice"

    if post_type == "message":
        return _parse_message(raw)
    elif post_type == "request":
        return _parse_request(raw)
    elif post_type == "notice":
        return NoticeEvent(
            time=raw.get("time", 0),
            self_id=raw.get("self_id", 0),
            notice_type=raw.get("notice_type", ""),
            raw=raw,
        )
    # meta_event（heartbeat / lifecycle）忽略
    return None


def _parse_message(raw: Dict) -> Optional[Union[PrivateMsgEvent, GroupMsgEvent]]:
    msg_type = raw.get("message_type")
    self_id = raw.get("self_id", 0)
    text, attachments = _extract_content(raw.get("message", ""), self_id)
    at_bot = _has_at(raw.get("message", ""), self_id)

    sender_data = raw.get("sender", {})
    sender = Sender(
        user_id=raw.get("user_id", 0),
        nickname=sender_data.get("nickname", ""),
        card=sender_data.get("card", ""),
        role=sender_data.get("role", "member"),
    )

    if msg_type == "private":
        return PrivateMsgEvent(
            time=raw.get("time", 0),
            self_id=self_id,
            user_id=raw.get("user_id", 0),
            message_id=raw.get("message_id", 0),
            raw_message=raw.get("raw_message", ""),
            message=text,
            sender=sender,
            sub_type=raw.get("sub_type", "friend"),
            attachments=attachments,
        )
    elif msg_type == "group":
        return GroupMsgEvent(
            time=raw.get("time", 0),
            self_id=self_id,
            group_id=raw.get("group_id", 0),
            user_id=raw.get("user_id", 0),
            message_id=raw.get("message_id", 0),
            raw_message=raw.get("raw_message", ""),
            message=text,
            sender=sender,
            at_bot=at_bot,
            sub_type=raw.get("sub_type", "normal"),
            attachments=attachments,
        )
    return None


def _parse_request(raw: Dict) -> Optional[Union[FriendRequestEvent, GroupInviteEvent]]:
    req_type = raw.get("request_type")
    if req_type == "friend":
        return FriendRequestEvent(
            time=raw.get("time", 0),
            self_id=raw.get("self_id", 0),
            user_id=raw.get("user_id", 0),
            comment=raw.get("comment", ""),
            flag=raw.get("flag", ""),
        )
    elif req_type == "group":
        return GroupInviteEvent(
            time=raw.get("time", 0),
            self_id=raw.get("self_id", 0),
            group_id=raw.get("group_id", 0),
            user_id=raw.get("user_id", 0),
            comment=raw.get("comment", ""),
            flag=raw.get("flag", ""),
            sub_type=raw.get("sub_type", "add"),
        )
    return None


# ──────────────────────────────────────────────────────────
# 消息内容提取
# ──────────────────────────────────────────────────────────

def _extract_content(message: Any, self_id: int) -> tuple[str, List[Dict]]:
    """
    从消息字段提取纯文本和附件列表。
    message 可能是字符串（含 CQ 码）或消息段列表。
    返回 (纯文本, 附件列表)
    """
    if isinstance(message, list):
        return _extract_from_segments(message)
    elif isinstance(message, str):
        return _extract_from_cq_string(message)
    return "", []


def _extract_from_segments(segments: List[Dict]) -> tuple[str, List[Dict]]:
    texts = []
    attachments = []
    for seg in segments:
        seg_type = seg.get("type", "")
        if seg_type == "text":
            texts.append(seg.get("data", {}).get("text", ""))
        elif seg_type == "at":
            # @某人 不计入纯文本
            pass
        else:
            attachments.append({"type": seg_type, "data": seg.get("data", {})})
    return "".join(texts).strip(), attachments


def _extract_from_cq_string(message: str) -> tuple[str, List[Dict]]:
    attachments = []
    # 提取所有 CQ 码作为附件
    for m in re.finditer(r'\[CQ:(\w+)(?:,([^\]]*))?\]', message):
        cq_type = m.group(1)
        params_str = m.group(2) or ""
        params = {}
        for kv in params_str.split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                params[k.strip()] = v.strip()
        if cq_type != "at":
            attachments.append({"type": cq_type, "data": params})
    # 去除 CQ 码，保留纯文本
    text = re.sub(r'\[CQ:[^\]]*\]', '', message).strip()
    return text, attachments


def _has_at(message: Any, self_id: int) -> bool:
    """检测消息中是否 @ 了 bot"""
    if not self_id:
        return False
    if isinstance(message, list):
        for seg in message:
            if seg.get("type") == "at":
                qq = str(seg.get("data", {}).get("qq", ""))
                if qq == str(self_id) or qq == "all":
                    # "all" 不算专门 at bot，只检查精确 at
                    if qq == str(self_id):
                        return True
        return False
    elif isinstance(message, str):
        return f"[CQ:at,qq={self_id}]" in message
    return False


def format_group_context(messages: List[Dict]) -> str:
    """
    将数据库中取出的群消息列表格式化为给 LLM 看的文本。
    messages 格式: [{"sender_name": ..., "sender_qq": ..., "content": ..., "created_at": ...}]
    """
    lines = []
    for msg in messages:
        name = msg.get("sender_name") or f"QQ{msg.get('sender_qq', '?')}"
        content = msg.get("content", "")
        ts = msg.get("created_at", "")
        if ts and len(ts) >= 16:
            ts = ts[11:16]  # HH:MM
        lines.append(f"[{ts}] {name}: {content}")
    return "\n".join(lines)
