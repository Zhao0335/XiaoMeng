"""
CLI Gateway - 命令行网关
"""

from .base import Gateway
from typing import Optional
import asyncio
import sys


class CLIGateway(Gateway):
    """命令行网关"""
    
    def __init__(self):
        super().__init__()
        self._reader = None
        self._writer = None
    
    async def start(self):
        """启动 CLI 网关"""
        self._running = True
        
        asyncio.create_task(self._read_loop())
    
    async def stop(self):
        """停止 CLI 网关"""
        self._running = False
    
    async def _read_loop(self):
        """读取输入循环"""
        while self._running:
            try:
                loop = asyncio.get_event_loop()
                line = await loop.run_in_executor(None, input, "你: ")
                
                if not line.strip():
                    continue
                
                if self._message_handler:
                    from models import Message, User, UserLevel, Source
                    
                    user = User(
                        user_id="cli_user",
                        level=UserLevel.OWNER,
                        source=Source.CLI
                    )
                    
                    message = Message(
                        content=line.strip(),
                        user=user,
                        source=Source.CLI
                    )
                    
                    response = await self._message_handler(message)
                    
                    if response:
                        print(f"小萌: {response.content}")
            
            except EOFError:
                self._running = False
                break
            except Exception as e:
                print(f"CLI 错误: {e}")
    
    async def send(self, target: str, message: str):
        """发送消息"""
        print(f"小萌: {message}")


class QQGateway(Gateway):
    """QQ 网关（占位实现）"""
    
    def __init__(self):
        super().__init__()
    
    async def start(self):
        self._running = True
        print("  QQ Gateway: 占位实现，需要配置 go-cqhttp")
    
    async def stop(self):
        self._running = False
    
    async def send(self, target: str, message: str):
        pass
