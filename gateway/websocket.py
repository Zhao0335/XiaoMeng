"""
WebSocket Gateway - WebSocket 网关
"""

from .base import Gateway
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import json
from typing import Dict, Set


class WebSocketGateway(Gateway):
    """WebSocket 网关"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        super().__init__()
        self._host = host
        self._port = port
        self._app = FastAPI(title="XiaoMengCore WebSocket")
        self._server = None
        self._connections: Set[WebSocket] = set()
        
        self._setup_routes()
    
    def _setup_routes(self):
        """设置路由"""
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @self._app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self._connections.add(websocket)
            
            try:
                while self._running:
                    data = await websocket.receive_text()
                    
                    try:
                        msg = json.loads(data)
                        message = msg.get("message", "")
                        user_id = msg.get("user_id", "anonymous")
                        
                        if self._message_handler:
                            from models import Message, User, UserLevel, Source
                            
                            user = User(
                                user_id=user_id,
                                level=UserLevel.STRANGER,
                                source=Source.WEB
                            )
                            
                            m = Message(
                                content=message,
                                user=user,
                                source=Source.WEB
                            )
                            
                            response = await self._message_handler(m)
                            
                            await websocket.send_json({
                                "type": "response",
                                "content": response.content if response else "",
                                "emotion": response.emotion.value if response and response.emotion else "neutral"
                            })
                    
                    except json.JSONDecodeError:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Invalid JSON"
                        })
            
            except WebSocketDisconnect:
                pass
            finally:
                self._connections.discard(websocket)
        
        @self._app.get("/health")
        async def health():
            return {"status": "ok", "connections": len(self._connections)}
    
    async def start(self):
        """启动 WebSocket 网关"""
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning"
        )
        self._server = uvicorn.Server(config)
        
        asyncio.create_task(self._server.serve())
    
    async def stop(self):
        """停止 WebSocket 网关"""
        if self._server:
            self._server.should_exit = True
        
        for ws in list(self._connections):
            try:
                await ws.close()
            except Exception:
                pass
        
        self._running = False
    
    async def send(self, target: str, message: str):
        """广播消息到所有连接"""
        for ws in list(self._connections):
            try:
                await ws.send_json({
                    "type": "broadcast",
                    "content": message
                })
            except Exception:
                self._connections.discard(ws)
    
    async def broadcast(self, message: str):
        """广播消息"""
        await self.send("", message)
