"""
XiaoMengCore Gateway 模块
提供多种消息渠道的网关实现
"""

from .base import Gateway, GatewayManager
from .cli import CLIGateway
from .http import HTTPGateway
from .websocket import WebSocketGateway
from .unified import create_gateway_app, app as unified_app

__all__ = [
    "Gateway",
    "GatewayManager",
    "CLIGateway",
    "HTTPGateway",
    "WebSocketGateway",
    "create_gateway_app",
    "unified_app"
]
