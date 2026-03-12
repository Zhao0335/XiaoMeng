"""
XiaoMengCore v2 - 统一网关

核心特性：
1. 跨平台身份统一：QQ、微信、Telegram 等平台的用户映射到同一个 Identity
2. 统一会话：同一 Identity 在不同平台的对话共享同一个 Session
3. 消息队列：支持 STEER、FOLLOWUP、COLLECT 等模式
4. 钩子系统：在 Agent 生命周期注入自定义逻辑
5. 双层持久化：sessions.json + .jsonl 记录
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime
from pathlib import Path
import asyncio
import uuid

from .identity import Identity, Platform, IdentityManager, PlatformIdentity
from .queue import MessageQueue, QueueMode, QueuedMessage
from .hooks import HookSystem, HookPoint, HookContext
from .session import SessionStore, TranscriptEntry


@dataclass
class IncomingMessage:
    content: str
    platform: Platform
    platform_user_id: str
    platform_display_name: Optional[str] = None
    chat_id: Optional[str] = None
    is_group: bool = False
    reply_to: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutgoingMessage:
    content: str
    session_key: str
    identity_id: str
    platform: Platform
    platform_user_id: str
    message_id: Optional[str] = None
    chunks: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class GatewayV2:
    """
    XiaoMengCore v2 统一网关
    
    核心概念：
    - 平台身份（QQ号、微信号）→ 规范身份→ 统一会话
    - 同一个真实用户，无论从哪个平台发消息，都路由到同一个会话
    """
    
    _instance: Optional["GatewayV2"] = None
    
    def __init__(self, data_dir: str = "data"):
        self._identity_manager = IdentityManager(f"{data_dir}/identities")
        self._message_queue = MessageQueue()
        self._hook_system = HookSystem()
        self._session_store = SessionStore(data_dir)
        
        self._processors: Dict[str, Callable] = {}
        self._response_handlers: Dict[str, Callable] = {}
        
        self._dm_scope: str = "per-identity"
        self._group_activation: str = "mention"
        
        self._message_queue.register_handler("default", self._process_message)
    
    @classmethod
    def get_instance(cls) -> "GatewayV2":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_processor(self, name: str, processor: Callable):
        self._processors[name] = processor
    
    def register_response_handler(self, platform: Platform, handler: Callable):
        self._response_handlers[platform.value] = handler
    
    def _resolve_session_key(
        self,
        identity: Identity,
        platform: Platform,
        chat_id: Optional[str],
        is_group: bool
    ) -> str:
        """
        计算会话键
        
        关键逻辑：
        1. 群组消息：每个群一个会话
        2. 私信消息：根据 dm_scope 配置
           - per-identity: 同一身份共享一个会话（跨平台统一）
           - per-platform: 每个平台一个会话
        """
        if is_group and chat_id:
            return f"agent:main:{platform.value}:group:{chat_id}"
        
        if self._dm_scope == "per-identity":
            return f"agent:main:identity:{identity.identity_id}"
        elif self._dm_scope == "per-platform":
            return f"agent:main:{platform.value}:user:{identity.identity_id}"
        else:
            return f"agent:main:identity:{identity.identity_id}"
    
    async def receive(
        self,
        message: IncomingMessage,
        queue_mode: QueueMode = QueueMode.FOLLOWUP
    ) -> Dict[str, Any]:
        """
        接收消息
        
        这是所有平台消息的统一入口
        """
        hook_ctx = HookContext(
            hook_point=HookPoint.MESSAGE_RECEIVED,
            session_key="",
            metadata={"platform": message.platform.value}
        )
        hook_ctx = await self._hook_system.trigger(hook_ctx)
        
        identity = self._identity_manager.get_or_create_identity(
            platform=message.platform,
            platform_user_id=message.platform_user_id,
            display_name=message.platform_display_name
        )
        
        session_key = self._resolve_session_key(
            identity=identity,
            platform=message.platform,
            chat_id=message.chat_id,
            is_group=message.is_group
        )
        
        session = self._session_store.get_session(session_key)
        if not session:
            self._session_store.create_session(
                session_key=session_key,
                identity_id=identity.identity_id,
                group_id=identity.group_id,
                channel=message.platform.value
            )
        
        message_id = await self._message_queue.enqueue(
            content=message.content,
            platform=message.platform,
            platform_user_id=message.platform_user_id,
            identity=identity,
            session_key=session_key,
            queue_mode=queue_mode,
            metadata={
                "chat_id": message.chat_id,
                "is_group": message.is_group,
                "reply_to": message.reply_to,
                "attachments": message.attachments,
                **message.metadata
            }
        )
        
        return {
            "success": True,
            "message_id": message_id,
            "session_key": session_key,
            "identity_id": identity.identity_id
        }
    
    async def _process_message(self, queued_message: QueuedMessage) -> Any:
        """处理队列中的消息"""
        session_key = queued_message.session_key
        identity = queued_message.identity
        
        hook_ctx = HookContext(
            hook_point=HookPoint.BEFORE_AGENT_START,
            session_key=session_key,
            identity_id=identity.identity_id if identity else None,
            run_id=queued_message.message_id,
            message=queued_message
        )
        hook_ctx = await self._hook_system.trigger(hook_ctx)
        
        self._session_store.append_transcript(
            session_key=session_key,
            role="user",
            content=queued_message.content
        )
        
        processor = self._processors.get("default")
        if not processor:
            response = "未配置处理器"
        else:
            try:
                response = await processor(
                    content=queued_message.content,
                    session_key=session_key,
                    identity=identity,
                    metadata=queued_message.metadata
                )
            except Exception as e:
                response = f"处理失败: {str(e)}"
        
        self._session_store.append_transcript(
            session_key=session_key,
            role="assistant",
            content=response
        )
        
        hook_ctx = HookContext(
            hook_point=HookPoint.AGENT_END,
            session_key=session_key,
            identity_id=identity.identity_id if identity else None,
            run_id=queued_message.message_id,
            response=response
        )
        await self._hook_system.trigger(hook_ctx)
        
        await self._send_response(
            content=response,
            platform=queued_message.platform,
            platform_user_id=queued_message.platform_user_id,
            session_key=session_key,
            identity=identity
        )
        
        return response
    
    async def _send_response(
        self,
        content: str,
        platform: Platform,
        platform_user_id: str,
        session_key: str,
        identity: Optional[Identity]
    ):
        hook_ctx = HookContext(
            hook_point=HookPoint.MESSAGE_SENDING,
            session_key=session_key,
            identity_id=identity.identity_id if identity else None,
            response=content
        )
        hook_ctx = await self._hook_system.trigger(hook_ctx)
        
        handler = self._response_handlers.get(platform.value)
        if handler:
            await handler(
                content=content,
                platform_user_id=platform_user_id,
                session_key=session_key
            )
        
        hook_ctx = HookContext(
            hook_point=HookPoint.MESSAGE_SENT,
            session_key=session_key,
            identity_id=identity.identity_id if identity else None,
            response=content
        )
        await self._hook_system.trigger(hook_ctx)
    
    async def send_to_session(
        self,
        session_key: str,
        content: str,
        from_identity_id: Optional[str] = None
    ) -> bool:
        """
        跨会话通信
        
        允许一个会话向另一个会话发送消息
        参考 OpenClaw 的 sessions_send 工具
        """
        session = self._session_store.get_session(session_key)
        if not session:
            return False
        
        identity = None
        if from_identity_id:
            identity = self._identity_manager.get_identity(from_identity_id)
        
        self._session_store.append_transcript(
            session_key=session_key,
            role="system",
            content=f"[跨会话消息] {content}",
            metadata={"from_identity": from_identity_id}
        )
        
        return True
    
    def get_identity(self, identity_id: str) -> Optional[Identity]:
        return self._identity_manager.get_identity(identity_id)
    
    def resolve_identity(
        self,
        platform: Platform,
        platform_user_id: str
    ) -> Optional[Identity]:
        return self._identity_manager.resolve_identity(platform, platform_user_id)
    
    def link_platform(
        self,
        identity_id: str,
        platform: Platform,
        platform_user_id: str,
        display_name: Optional[str] = None
    ) -> bool:
        return self._identity_manager.link_platform_identity(
            identity_id=identity_id,
            platform=platform,
            platform_user_id=platform_user_id,
            display_name=display_name
        )
    
    def get_session(self, session_key: str) -> Optional[Dict]:
        return self._session_store.get_session(session_key)
    
    def get_session_transcript(
        self,
        session_key: str,
        limit: int = 50
    ) -> List[TranscriptEntry]:
        return self._session_store.get_transcript(session_key, limit)
    
    def list_sessions(
        self,
        identity_id: Optional[str] = None,
        active_within_minutes: Optional[int] = None
    ) -> List[Dict]:
        return self._session_store.list_sessions(
            identity_id=identity_id,
            active_within_minutes=active_within_minutes
        )
    
    def get_queue_status(self, session_key: str) -> Dict:
        return self._message_queue.get_queue_status(session_key)
    
    def register_hook(
        self,
        name: str,
        hook_point: HookPoint,
        handler: Callable,
        priority: int = 100
    ):
        self._hook_system.register(name, hook_point, handler, priority)


def create_simple_processor(llm_client) -> Callable:
    """创建简单的 LLM 处理器"""
    async def processor(
        content: str,
        session_key: str,
        identity: Optional[Identity],
        metadata: Dict[str, Any]
    ) -> str:
        messages = [{"role": "user", "content": content}]
        response = await llm_client.chat(messages)
        return response
    
    return processor
