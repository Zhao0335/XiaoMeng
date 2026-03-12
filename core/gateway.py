"""
XiaoMengCore 统一消息系统
参考 OpenClaw Gateway 架构

核心概念：
1. Message: 统一消息格式，包含来源、用户、内容
2. Session: 会话管理，每个用户组独立 session
3. Gateway: 统一消息入口，路由到对应 session
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from pathlib import Path
import json
import asyncio
import hashlib


class Channel(Enum):
    CLI = "cli"
    HTTP = "http"
    WEBSOCKET = "websocket"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WEBCHAT = "webchat"
    PLUGIN = "plugin"


class UserLevel(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    WHITELIST = "whitelist"
    NORMAL = "normal"
    GUEST = "guest"


@dataclass
class UserInfo:
    user_id: str
    level: UserLevel = UserLevel.NORMAL
    group_id: Optional[str] = None
    identities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "level": self.level.value,
            "group_id": self.group_id,
            "identities": self.identities,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserInfo":
        return cls(
            user_id=data["user_id"],
            level=UserLevel(data.get("level", "normal")),
            group_id=data.get("group_id"),
            identities=data.get("identities", []),
            metadata=data.get("metadata", {})
        )


@dataclass
class MessageSource:
    channel: Channel
    account_id: Optional[str] = None
    chat_id: Optional[str] = None
    thread_id: Optional[str] = None
    is_group: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel.value,
            "account_id": self.account_id,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
            "is_group": self.is_group
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageSource":
        return cls(
            channel=Channel(data["channel"]),
            account_id=data.get("account_id"),
            chat_id=data.get("chat_id"),
            thread_id=data.get("thread_id"),
            is_group=data.get("is_group", False)
        )


@dataclass
class Message:
    content: str
    source: MessageSource
    user: UserInfo
    message_id: Optional[str] = None
    reply_to: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def get_session_key(self, agent_id: str = "main") -> str:
        """
        生成会话键
        
        格式: agent:<agentId>:<channel>:<scope>:<id>
        
        参考 OpenClaw:
        - 私信: agent:<agentId>:<mainKey>
        - 群组: agent:<agentId>:<channel>:group:<id>
        - 用户组: agent:<agentId>:group:<groupId>
        """
        if self.user.group_id:
            return f"agent:{agent_id}:group:{self.user.group_id}"
        
        if self.source.is_group and self.source.chat_id:
            return f"agent:{agent_id}:{self.source.channel.value}:group:{self.source.chat_id}"
        
        if self.user.level == UserLevel.OWNER:
            return f"agent:{agent_id}:main"
        
        return f"agent:{agent_id}:{self.source.channel.value}:user:{self.user.user_id}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source.to_dict(),
            "user": self.user.to_dict(),
            "message_id": self.message_id,
            "reply_to": self.reply_to,
            "attachments": self.attachments,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "session_key": self.get_session_key()
        }


@dataclass
class SessionEntry:
    session_key: str
    user_id: str
    group_id: Optional[str] = None
    channel: Optional[Channel] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    context: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_key": self.session_key,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "channel": self.channel.value if self.channel else None,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "message_count": self.message_count,
            "metadata": self.metadata
        }


class SessionManager:
    """
    会话管理器
    
    参考 OpenClaw 的会话管理：
    - 每个用户组独立 session
    - 支持会话持久化
    - 支持上下文管理
    """
    
    _instance: Optional["SessionManager"] = None
    
    def __init__(self, data_dir: str = "data/sessions"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, SessionEntry] = {}
        self._sessions_file = self._data_dir / "sessions.json"
        self._load_sessions()
    
    @classmethod
    def get_instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _load_sessions(self):
        if self._sessions_file.exists():
            try:
                with open(self._sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, entry in data.items():
                        entry["created_at"] = datetime.fromisoformat(entry["created_at"])
                        entry["last_active"] = datetime.fromisoformat(entry["last_active"])
                        if entry.get("channel"):
                            entry["channel"] = Channel(entry["channel"])
                        self._sessions[key] = SessionEntry(**entry)
            except Exception as e:
                print(f"加载会话失败: {e}")
    
    def _save_sessions(self):
        data = {}
        for key, entry in self._sessions.items():
            data[key] = entry.to_dict()
        
        with open(self._sessions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    def get_or_create_session(self, message: Message, agent_id: str = "main") -> SessionEntry:
        """获取或创建会话"""
        session_key = message.get_session_key(agent_id)
        
        if session_key not in self._sessions:
            session = SessionEntry(
                session_key=session_key,
                user_id=message.user.user_id,
                group_id=message.user.group_id,
                channel=message.source.channel
            )
            self._sessions[session_key] = session
        else:
            session = self._sessions[session_key]
            session.last_active = datetime.now()
        
        session.message_count += 1
        self._save_sessions()
        
        return session
    
    def get_session(self, session_key: str) -> Optional[SessionEntry]:
        return self._sessions.get(session_key)
    
    def add_context(self, session_key: str, role: str, content: str):
        if session_key in self._sessions:
            session = self._sessions[session_key]
            session.context.append({"role": role, "content": content})
            session.last_active = datetime.now()
            self._save_sessions()
    
    def get_context(self, session_key: str, limit: int = 20) -> List[Dict[str, str]]:
        if session_key in self._sessions:
            return self._sessions[session_key].context[-limit:]
        return []
    
    def clear_context(self, session_key: str):
        if session_key in self._sessions:
            self._sessions[session_key].context = []
            self._save_sessions()
    
    def list_sessions(self) -> List[SessionEntry]:
        return list(self._sessions.values())
    
    def delete_session(self, session_key: str):
        if session_key in self._sessions:
            del self._sessions[session_key]
            self._save_sessions()


class MessageRouter:
    """
    消息路由器
    
    将消息路由到对应的处理器
    """
    
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._middlewares: List[Callable] = []
    
    def register_handler(self, channel: Channel, handler: Callable):
        self._handlers[channel.value] = handler
    
    def add_middleware(self, middleware: Callable):
        self._middlewares.append(middleware)
    
    async def route(self, message: Message) -> Dict[str, Any]:
        """路由消息到对应处理器"""
        for middleware in self._middlewares:
            message = await middleware(message)
            if message is None:
                return {"success": False, "error": "消息被中间件拦截"}
        
        handler = self._handlers.get(message.source.channel.value)
        if handler:
            return await handler(message)
        
        return {"success": False, "error": f"未找到渠道处理器: {message.source.channel.value}"}


class Gateway:
    """
    统一消息网关
    
    参考 OpenClaw Gateway 架构：
    - 统一消息入口
    - 用户分组路由
    - 会话隔离
    - 多渠道支持
    """
    
    _instance: Optional["Gateway"] = None
    
    def __init__(self, data_dir: str = "data"):
        self._data_dir = Path(data_dir)
        self._session_manager = SessionManager(str(self._data_dir / "sessions"))
        self._router = MessageRouter()
        self._user_groups: Dict[str, Dict[str, Any]] = {}
        self._processors: Dict[str, Callable] = {}
        self._load_user_groups()
    
    @classmethod
    def get_instance(cls) -> "Gateway":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _load_user_groups(self):
        config_path = self._data_dir / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self._user_groups = config.get("user_groups", {})
            except Exception as e:
                print(f"加载用户分组失败: {e}")
    
    def register_processor(self, name: str, processor: Callable):
        """注册消息处理器"""
        self._processors[name] = processor
    
    async def receive(
        self,
        content: str,
        channel: Channel,
        user_id: str,
        user_level: UserLevel = UserLevel.NORMAL,
        group_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        is_group: bool = False,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        统一消息接收入口
        
        所有渠道的消息都通过这个方法进入系统
        
        Args:
            content: 消息内容
            channel: 消息来源渠道
            user_id: 用户ID
            user_level: 用户等级
            group_id: 用户组ID (可选，用于分组会话)
            chat_id: 聊天ID (群组/频道)
            thread_id: 线程ID
            is_group: 是否群组消息
            attachments: 附件列表
            metadata: 其他元数据
        
        Returns:
            处理结果
        """
        source = MessageSource(
            channel=channel,
            chat_id=chat_id,
            thread_id=thread_id,
            is_group=is_group
        )
        
        user = UserInfo(
            user_id=user_id,
            level=user_level,
            group_id=group_id
        )
        
        message = Message(
            content=content,
            source=source,
            user=user,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        session = self._session_manager.get_or_create_session(message)
        
        processor = self._processors.get("default")
        if not processor:
            return {"success": False, "error": "未注册消息处理器"}
        
        try:
            result = await processor(message, session)
            
            if result.get("success"):
                self._session_manager.add_context(
                    session.session_key,
                    "user",
                    content
                )
                if result.get("response"):
                    self._session_manager.add_context(
                        session.session_key,
                        "assistant",
                        result["response"]
                    )
            
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_session_context(self, session_key: str, limit: int = 20) -> List[Dict[str, str]]:
        """获取会话上下文"""
        return self._session_manager.get_context(session_key, limit)
    
    def get_user_sessions(self, user_id: str) -> List[SessionEntry]:
        """获取用户的所有会话"""
        return [s for s in self._session_manager.list_sessions() if s.user_id == user_id]
    
    def get_group_sessions(self, group_id: str) -> List[SessionEntry]:
        """获取用户组的所有会话"""
        return [s for s in self._session_manager.list_sessions() if s.group_id == group_id]


async def default_processor(message: Message, session: SessionEntry) -> Dict[str, Any]:
    """默认消息处理器"""
    from core.llm_client import LLMClient
    
    client = LLMClient.get_instance()
    
    context = session.context[-10:] if session.context else []
    messages = context + [{"role": "user", "content": message.content}]
    
    try:
        response = await client.chat(messages=messages, max_tokens=500)
        return {
            "success": True,
            "response": response.get("content", ""),
            "session_key": session.session_key
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
