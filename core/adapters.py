"""
XiaoMengCore 渠道适配器
将不同渠道的消息转换为统一格式，通过 Gateway 处理
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable, Awaitable
from pathlib import Path
import json
import asyncio

from core.gateway import (
    Gateway, Message, MessageSource, UserInfo, UserLevel,
    Channel, SessionEntry
)


class ChannelAdapter(ABC):
    """渠道适配器基类"""
    
    def __init__(self, gateway: Gateway):
        self._gateway = gateway
        self._response_handler: Optional[Callable] = None
    
    def set_response_handler(self, handler: Callable[[Dict[str, Any]], Awaitable[None]]):
        """设置响应处理器"""
        self._response_handler = handler
    
    async def _send_response(self, response: Dict[str, Any]):
        """发送响应"""
        if self._response_handler:
            await self._response_handler(response)
    
    @abstractmethod
    async def receive(
        self,
        content: str,
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """接收消息"""
        pass


class CLIAdapter(ChannelAdapter):
    """命令行适配器"""
    
    async def receive(
        self,
        content: str,
        user_id: str = "owner",
        user_level: UserLevel = UserLevel.OWNER,
        **kwargs
    ) -> Dict[str, Any]:
        return await self._gateway.receive(
            content=content,
            channel=Channel.CLI,
            user_id=user_id,
            user_level=user_level,
            **kwargs
        )


class HTTPAdapter(ChannelAdapter):
    """HTTP API 适配器"""
    
    async def receive(
        self,
        content: str,
        user_id: str,
        user_level: UserLevel = UserLevel.NORMAL,
        group_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return await self._gateway.receive(
            content=content,
            channel=Channel.HTTP,
            user_id=user_id,
            user_level=user_level,
            group_id=group_id,
            **kwargs
        )


class WebSocketAdapter(ChannelAdapter):
    """WebSocket 适配器"""
    
    def __init__(self, gateway: Gateway):
        super().__init__(gateway)
        self._connections: Dict[str, Any] = {}
    
    def register_connection(self, user_id: str, connection: Any):
        self._connections[user_id] = connection
    
    def unregister_connection(self, user_id: str):
        self._connections.pop(user_id, None)
    
    async def receive(
        self,
        content: str,
        user_id: str,
        user_level: UserLevel = UserLevel.NORMAL,
        **kwargs
    ) -> Dict[str, Any]:
        result = await self._gateway.receive(
            content=content,
            channel=Channel.WEBSOCKET,
            user_id=user_id,
            user_level=user_level,
            **kwargs
        )
        
        if result.get("success") and user_id in self._connections:
            conn = self._connections[user_id]
            if hasattr(conn, 'send_json'):
                await conn.send_json(result)
            elif hasattr(conn, 'send'):
                await conn.send(json.dumps(result, ensure_ascii=False))
        
        return result


class WebChatAdapter(ChannelAdapter):
    """WebChat 适配器（类似 OpenClaw 的 WebChat）"""
    
    def __init__(self, gateway: Gateway):
        super().__init__(gateway)
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    async def receive(
        self,
        content: str,
        user_id: str,
        user_level: UserLevel = UserLevel.NORMAL,
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        if session_id:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "user_id": user_id,
                    "created_at": asyncio.get_event_loop().time()
                }
            kwargs["chat_id"] = session_id
        
        return await self._gateway.receive(
            content=content,
            channel=Channel.WEBCHAT,
            user_id=user_id,
            user_level=user_level,
            **kwargs
        )
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)
    
    def clear_session(self, session_id: str):
        self._sessions.pop(session_id, None)


class PluginAdapter(ChannelAdapter):
    """插件适配器"""
    
    async def receive(
        self,
        content: str,
        user_id: str,
        plugin_name: str,
        user_level: UserLevel = UserLevel.NORMAL,
        **kwargs
    ) -> Dict[str, Any]:
        kwargs["metadata"] = kwargs.get("metadata", {})
        kwargs["metadata"]["plugin"] = plugin_name
        
        return await self._gateway.receive(
            content=content,
            channel=Channel.PLUGIN,
            user_id=user_id,
            user_level=user_level,
            **kwargs
        )


class AdapterManager:
    """适配器管理器"""
    
    _instance: Optional["AdapterManager"] = None
    
    def __init__(self, gateway: Gateway = None):
        self._gateway = gateway or Gateway.get_instance()
        self._adapters: Dict[Channel, ChannelAdapter] = {}
        self._setup_adapters()
    
    @classmethod
    def get_instance(cls) -> "AdapterManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _setup_adapters(self):
        self._adapters[Channel.CLI] = CLIAdapter(self._gateway)
        self._adapters[Channel.HTTP] = HTTPAdapter(self._gateway)
        self._adapters[Channel.WEBSOCKET] = WebSocketAdapter(self._gateway)
        self._adapters[Channel.WEBCHAT] = WebChatAdapter(self._gateway)
        self._adapters[Channel.PLUGIN] = PluginAdapter(self._gateway)
    
    def get_adapter(self, channel: Channel) -> Optional[ChannelAdapter]:
        return self._adapters.get(channel)
    
    def get_websocket_adapter(self) -> WebSocketAdapter:
        return self._adapters[Channel.WEBSOCKET]
    
    def get_webchat_adapter(self) -> WebChatAdapter:
        return self._adapters[Channel.WEBCHAT]
    
    async def receive_from(
        self,
        channel: Channel,
        content: str,
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        adapter = self.get_adapter(channel)
        if adapter:
            return await adapter.receive(content, user_id, **kwargs)
        return {"success": False, "error": f"未找到适配器: {channel.value}"}
