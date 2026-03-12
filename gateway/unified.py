"""
XiaoMengCore 统一网关入口
整合 Gateway 消息系统，提供统一的消息接收接口
"""

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
import json
import asyncio

from core.gateway import Gateway, Channel, UserLevel
from core.adapters import AdapterManager


def create_gateway_app() -> FastAPI:
    """创建统一网关应用"""
    app = FastAPI(title="XiaoMengCore Gateway")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    gateway = Gateway.get_instance()
    adapter_manager = AdapterManager.get_instance()
    
    @app.get("/")
    async def index():
        return {
            "name": "XiaoMengCore Gateway",
            "status": "running",
            "channels": ["cli", "http", "websocket", "webchat", "plugin"]
        }
    
    @app.get("/api/status")
    async def get_status():
        sessions = gateway._session_manager.list_sessions()
        return {
            "sessions_count": len(sessions),
            "sessions": [s.to_dict() for s in sessions[:10]]
        }
    
    @app.post("/api/message")
    async def receive_message(request: Request):
        """
        统一消息接收入口
        
        请求体:
        {
            "content": "消息内容",
            "user_id": "用户ID",
            "user_level": "normal|owner|admin|whitelist|guest",
            "group_id": "用户组ID (可选)",
            "channel": "http|cli|websocket|webchat|plugin",
            "chat_id": "聊天ID (可选)",
            "is_group": false,
            "metadata": {}
        }
        """
        try:
            data = await request.json()
            
            content = data.get("content", "")
            user_id = data.get("user_id", "anonymous")
            user_level = UserLevel(data.get("user_level", "normal"))
            group_id = data.get("group_id")
            channel = Channel(data.get("channel", "http"))
            chat_id = data.get("chat_id")
            is_group = data.get("is_group", False)
            metadata = data.get("metadata", {})
            
            result = await gateway.receive(
                content=content,
                channel=channel,
                user_id=user_id,
                user_level=user_level,
                group_id=group_id,
                chat_id=chat_id,
                is_group=is_group,
                metadata=metadata
            )
            
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    
    @app.get("/api/session/{session_key}")
    async def get_session(session_key: str):
        session = gateway.get_session_context(session_key)
        return {"session_key": session_key, "context": session}
    
    @app.delete("/api/session/{session_key}")
    async def clear_session(session_key: str):
        gateway._session_manager.clear_context(session_key)
        return {"success": True}
    
    @app.get("/api/sessions")
    async def list_sessions():
        sessions = gateway._session_manager.list_sessions()
        return {"sessions": [s.to_dict() for s in sessions]}
    
    @app.get("/api/sessions/user/{user_id}")
    async def get_user_sessions(user_id: str):
        sessions = gateway.get_user_sessions(user_id)
        return {"sessions": [s.to_dict() for s in sessions]}
    
    @app.get("/api/sessions/group/{group_id}")
    async def get_group_sessions(group_id: str):
        sessions = gateway.get_group_sessions(group_id)
        return {"sessions": [s.to_dict() for s in sessions]}
    
    @app.websocket("/ws/{user_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: str):
        await websocket.accept()
        
        ws_adapter = adapter_manager.get_websocket_adapter()
        ws_adapter.register_connection(user_id, websocket)
        
        try:
            while True:
                data = await websocket.receive_text()
                
                try:
                    msg = json.loads(data)
                    content = msg.get("content", data)
                    user_level = UserLevel(msg.get("user_level", "normal"))
                    group_id = msg.get("group_id")
                except:
                    content = data
                    user_level = UserLevel.NORMAL
                    group_id = None
                
                result = await gateway.receive(
                    content=content,
                    channel=Channel.WEBSOCKET,
                    user_id=user_id,
                    user_level=user_level,
                    group_id=group_id
                )
                
                await websocket.send_json(result)
        except WebSocketDisconnect:
            ws_adapter.unregister_connection(user_id)
    
    @app.websocket("/webchat/{session_id}")
    async def webchat_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        
        webchat_adapter = adapter_manager.get_webchat_adapter()
        
        try:
            while True:
                data = await websocket.receive_text()
                
                try:
                    msg = json.loads(data)
                    content = msg.get("content", data)
                    user_id = msg.get("user_id", session_id)
                    user_level = UserLevel(msg.get("user_level", "normal"))
                    group_id = msg.get("group_id")
                except:
                    content = data
                    user_id = session_id
                    user_level = UserLevel.NORMAL
                    group_id = None
                
                result = await gateway.receive(
                    content=content,
                    channel=Channel.WEBCHAT,
                    user_id=user_id,
                    user_level=user_level,
                    group_id=group_id,
                    chat_id=session_id
                )
                
                await websocket.send_json(result)
        except WebSocketDisconnect:
            webchat_adapter.clear_session(session_id)
    
    return app


app = create_gateway_app()


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("XiaoMengCore Gateway")
    print("=" * 60)
    print("API: http://127.0.0.1:8080")
    print("WebSocket: ws://127.0.0.1:8080/ws/{user_id}")
    print("WebChat: ws://127.0.0.1:8080/webchat/{session_id}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8080)
