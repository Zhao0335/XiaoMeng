"""
Gateway 基础模块
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable, Dict, Any
import asyncio


class Gateway(ABC):
    """网关基类"""
    
    def __init__(self):
        self._message_handler: Optional[Callable] = None
        self._running = False
    
    def set_message_handler(self, handler: Callable):
        """设置消息处理器"""
        self._message_handler = handler
    
    @abstractmethod
    async def start(self):
        """启动网关"""
        pass
    
    @abstractmethod
    async def stop(self):
        """停止网关"""
        pass
    
    @abstractmethod
    async def send(self, target: str, message: str):
        """发送消息"""
        pass


class GatewayManager:
    """网关管理器"""
    
    _instance: Optional["GatewayManager"] = None
    
    def __init__(self):
        self._gateways: Dict[str, Gateway] = {}
    
    @classmethod
    def get_instance(cls) -> "GatewayManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, name: str, gateway: Gateway):
        """注册网关"""
        self._gateways[name] = gateway
    
    def get(self, name: str) -> Optional[Gateway]:
        """获取网关"""
        return self._gateways.get(name)
    
    async def start_all(self):
        """启动所有网关"""
        for name, gateway in self._gateways.items():
            try:
                await gateway.start()
                print(f"  网关 {name} 已启动")
            except Exception as e:
                print(f"  网关 {name} 启动失败: {e}")
    
    async def stop_all(self):
        """停止所有网关"""
        for name, gateway in self._gateways.items():
            try:
                await gateway.stop()
            except Exception as e:
                print(f"  网关 {name} 停止失败: {e}")
    
    async def broadcast(self, message: str):
        """广播消息到所有网关"""
        for gateway in self._gateways.values():
            try:
                await gateway.send("", message)
            except Exception:
                pass
