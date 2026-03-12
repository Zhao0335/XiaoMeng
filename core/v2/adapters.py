"""
XiaoMengCore v2 - 渠道适配器

为不同平台提供统一的适配接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Awaitable, List
from datetime import datetime
import asyncio

from .gateway import GatewayV2, IncomingMessage, OutgoingMessage
from .identity import Platform


class ChannelAdapter(ABC):
    """渠道适配器基类"""
    
    def __init__(self, gateway: GatewayV2, platform: Platform):
        self._gateway = gateway
        self._platform = platform
        self._response_handler: Optional[Callable] = None
    
    def set_response_handler(self, handler: Callable[[OutgoingMessage], Awaitable[None]]):
        self._response_handler = handler
    
    async def _send_response(self, message: OutgoingMessage):
        if self._response_handler:
            await self._response_handler(message)
    
    @abstractmethod
    async def receive(
        self,
        content: str,
        user_id: str,
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        pass


class CLIAdapter(ChannelAdapter):
    """命令行适配器"""
    
    def __init__(self, gateway: GatewayV2):
        super().__init__(gateway, Platform.CLI)
    
    async def receive(
        self,
        content: str,
        user_id: str = "cli_user",
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id,
            platform_display_name=display_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        return await self._gateway.receive(message)


class HTTPAdapter(ChannelAdapter):
    """HTTP API 适配器"""
    
    def __init__(self, gateway: GatewayV2):
        super().__init__(gateway, Platform.HTTP)
    
    async def receive(
        self,
        content: str,
        user_id: str,
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id,
            platform_display_name=display_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        return await self._gateway.receive(message)


class WebSocketAdapter(ChannelAdapter):
    """WebSocket 适配器"""
    
    def __init__(self, gateway: GatewayV2):
        super().__init__(gateway, Platform.WEBSOCKET)
        self._connections: Dict[str, Any] = {}
    
    def register_connection(self, user_id: str, websocket):
        self._connections[user_id] = websocket
    
    def unregister_connection(self, user_id: str):
        self._connections.pop(user_id, None)
    
    async def receive(
        self,
        content: str,
        user_id: str,
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id,
            platform_display_name=display_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        return await self._gateway.receive(message)
    
    async def send_to_user(self, user_id: str, content: str):
        ws = self._connections.get(user_id)
        if ws:
            await ws.send_text(content)


class QQAdapter(ChannelAdapter):
    """QQ 适配器（支持 go-cqhttp 等）"""
    
    def __init__(self, gateway: GatewayV2):
        super().__init__(gateway, Platform.QQ)
    
    async def receive(
        self,
        content: str,
        user_id: str,
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id,
            platform_display_name=display_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        return await self._gateway.receive(message)


class WeChatAdapter(ChannelAdapter):
    """微信适配器"""
    
    def __init__(self, gateway: GatewayV2):
        super().__init__(gateway, Platform.WECHAT)
    
    async def receive(
        self,
        content: str,
        user_id: str,
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id,
            platform_display_name=display_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        return await self._gateway.receive(message)


class TelegramAdapter(ChannelAdapter):
    """Telegram 适配器"""
    
    def __init__(self, gateway: GatewayV2):
        super().__init__(gateway, Platform.TELEGRAM)
    
    async def receive(
        self,
        content: str,
        user_id: str,
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id,
            platform_display_name=display_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        return await self._gateway.receive(message)


class DiscordAdapter(ChannelAdapter):
    """Discord 适配器"""
    
    def __init__(self, gateway: GatewayV2):
        super().__init__(gateway, Platform.DISCORD)
    
    async def receive(
        self,
        content: str,
        user_id: str,
        display_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        is_group: bool = False,
        reply_to: Optional[str] = None,
        attachments: List[Dict] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        message = IncomingMessage(
            content=content,
            platform=self._platform,
            platform_user_id=user_id,
            platform_display_name=display_name,
            chat_id=chat_id,
            is_group=is_group,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {}
        )
        
        return await self._gateway.receive(message)


class AdapterManager:
    """适配器管理器"""
    
    def __init__(self, gateway: GatewayV2):
        self._gateway = gateway
        self._adapters: Dict[Platform, ChannelAdapter] = {}
        
        self._adapters[Platform.CLI] = CLIAdapter(gateway)
        self._adapters[Platform.HTTP] = HTTPAdapter(gateway)
        self._adapters[Platform.WEBSOCKET] = WebSocketAdapter(gateway)
        self._adapters[Platform.QQ] = QQAdapter(gateway)
        self._adapters[Platform.WECHAT] = WeChatAdapter(gateway)
        self._adapters[Platform.TELEGRAM] = TelegramAdapter(gateway)
        self._adapters[Platform.DISCORD] = DiscordAdapter(gateway)
    
    def get_adapter(self, platform: Platform) -> Optional[ChannelAdapter]:
        return self._adapters.get(platform)
    
    async def receive(
        self,
        platform: Platform,
        content: str,
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        adapter = self._adapters.get(platform)
        if not adapter:
            return {"success": False, "error": f"不支持的渠道: {platform}"}
        
        return await adapter.receive(content, user_id, **kwargs)
