"""
HTTP Gateway - HTTP API 网关
"""

from .base import Gateway
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio


class HTTPGateway(Gateway):
    """HTTP API 网关"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        super().__init__()
        self._host = host
        self._port = port
        self._app = FastAPI(title="XiaoMengCore API")
        self._server = None
        
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
        
        @self._app.post("/chat")
        async def chat(request: Request):
            data = await request.json()
            message = data.get("message", "")
            user_id = data.get("user_id", "anonymous")
            
            if self._message_handler:
                from models import Message, User, UserLevel, Source
                
                user = User(
                    user_id=user_id,
                    level=UserLevel.STRANGER,
                    source=Source.WEB
                )
                
                msg = Message(
                    content=message,
                    user=user,
                    source=Source.WEB
                )
                
                response = await self._message_handler(msg)
                
                return JSONResponse({
                    "success": True,
                    "response": response.content if response else "",
                    "emotion": response.emotion.value if response and response.emotion else "neutral"
                })
            
            return JSONResponse({"success": False, "error": "No handler"})
        
        @self._app.get("/health")
        async def health():
            return {"status": "ok"}
    
    async def start(self):
        """启动 HTTP 网关"""
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning"
        )
        self._server = uvicorn.Server(config)
        
        asyncio.create_task(self._server.serve())
    
    async def stop(self):
        """停止 HTTP 网关"""
        if self._server:
            self._server.should_exit = True
        self._running = False
    
    async def send(self, target: str, message: str):
        """发送消息（HTTP 不支持主动发送）"""
        pass
