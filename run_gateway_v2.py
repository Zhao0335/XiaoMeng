"""
XiaoMengCore v2 - 统一网关 API

提供 HTTP/WebSocket 接口访问 v2 网关
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.v2 import (
    GatewayV2,
    Platform,
    IncomingMessage,
    QueueMode,
    HookPoint,
    HookContext,
    AdapterManager
)


class MessageRequest(BaseModel):
    content: str
    user_id: str
    platform: str = "http"
    display_name: Optional[str] = None
    chat_id: Optional[str] = None
    is_group: bool = False
    reply_to: Optional[str] = None
    queue_mode: str = "followup"
    metadata: Dict[str, Any] = {}


class LinkIdentityRequest(BaseModel):
    identity_id: str
    platform: str
    platform_user_id: str
    display_name: Optional[str] = None


app = FastAPI(
    title="XiaoMengCore v2 Gateway",
    description="统一网关 API - 支持跨平台身份统一",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

gateway: Optional[GatewayV2] = None
adapter_manager: Optional[AdapterManager] = None


@app.on_event("startup")
async def startup():
    global gateway, adapter_manager
    
    gateway = GatewayV2.get_instance()
    adapter_manager = AdapterManager(gateway)
    
    identity_links_file = Path(__file__).parent / "data" / "identity_links.json"
    if identity_links_file.exists():
        try:
            import json
            with open(identity_links_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            from core.v2.identity import IdentityManager
            im = IdentityManager.get_instance()
            
            identity_links = config.get("identity_links", {})
            for identity_id, platform_keys in identity_links.items():
                display_name = config.get("identity_profiles", {}).get(identity_id, {}).get("display_name")
                level = config.get("identity_profiles", {}).get(identity_id, {}).get("level", "normal")
                group_id = config.get("identity_profiles", {}).get(identity_id, {}).get("group_id")
                
                if identity_id not in [i.identity_id for i in im.list_identities()]:
                    im.create_identity(identity_id, display_name, level, group_id)
                
                for platform_key in platform_keys:
                    try:
                        parts = platform_key.split(":", 1)
                        if len(parts) == 2:
                            platform = Platform(parts[0])
                            platform_user_id = parts[1]
                            im.link_platform_identity(identity_id, platform, platform_user_id)
                    except ValueError as e:
                        print(f"无效的平台键: {platform_key}")
            
            print(f"✅ 已加载 {len(identity_links)} 个身份映射")
        except Exception as e:
            print(f"⚠️ 加载身份映射失败: {e}")
    
    try:
        from core.processor import MessageProcessor
        from config import ConfigManager
        
        cm = ConfigManager.get_instance()
        config_path = Path(__file__).parent / "data" / "config.json"
        if config_path.exists():
            cm.load(str(config_path))
        
        processor = MessageProcessor()
        
        async def llm_processor(content, session_key, identity, metadata):
            try:
                result = await processor.process(content)
                if isinstance(result, dict):
                    return result.get("response", str(result))
                return str(result)
            except Exception as e:
                return f"处理失败: {str(e)}"
        
        gateway.register_processor("default", llm_processor)
        print("✅ 已加载 LLM 处理器")
    except Exception as e:
        print(f"⚠️ 加载 LLM 处理器失败，使用默认处理器: {e}")
        
        async def default_processor(content, session_key, identity, metadata):
            return f"[v2] 收到消息: {content[:50]}..."
        
        gateway.register_processor("default", default_processor)
    
    print("✅ XiaoMengCore v2 Gateway 启动完成")


@app.get("/")
async def root():
    return {
        "name": "XiaoMengCore v2 Gateway",
        "version": "2.0.0",
        "features": [
            "跨平台身份统一",
            "统一会话管理",
            "消息队列系统",
            "钩子系统",
            "双层持久化"
        ]
    }


@app.post("/api/message")
async def receive_message(request: MessageRequest):
    """
    统一消息接收入口
    
    支持多种平台，通过 platform 参数指定
    """
    try:
        platform = Platform(request.platform)
    except ValueError:
        return JSONResponse(
            {"success": False, "error": f"无效的平台: {request.platform}"},
            status_code=400
        )
    
    try:
        queue_mode = QueueMode(request.queue_mode)
    except ValueError:
        queue_mode = QueueMode.FOLLOWUP
    
    message = IncomingMessage(
        content=request.content,
        platform=platform,
        platform_user_id=request.user_id,
        platform_display_name=request.display_name,
        chat_id=request.chat_id,
        is_group=request.is_group,
        reply_to=request.reply_to,
        metadata=request.metadata
    )
    
    result = await gateway.receive(message, queue_mode)
    
    return JSONResponse(result)


@app.post("/api/identity/link")
async def link_identity(request: LinkIdentityRequest):
    """
    关联平台身份
    
    将平台账号关联到规范身份，实现跨平台统一
    例如：将 QQ:12345 和 微信:wxid_xxx 都关联到 identity:alice
    """
    try:
        platform = Platform(request.platform)
    except ValueError:
        return JSONResponse(
            {"success": False, "error": f"无效的平台: {request.platform}"},
            status_code=400
        )
    
    success = gateway.link_platform(
        identity_id=request.identity_id,
        platform=platform,
        platform_user_id=request.platform_user_id,
        display_name=request.display_name
    )
    
    if success:
        return JSONResponse({
            "success": True,
            "message": f"已关联 {request.platform}:{request.platform_user_id} -> {request.identity_id}"
        })
    else:
        return JSONResponse(
            {"success": False, "error": f"关联失败，身份不存在: {request.identity_id}"},
            status_code=400
        )


@app.get("/api/identity/{identity_id}")
async def get_identity(identity_id: str):
    """获取身份信息"""
    identity = gateway.get_identity(identity_id)
    
    if not identity:
        return JSONResponse(
            {"success": False, "error": f"身份不存在: {identity_id}"},
            status_code=404
        )
    
    return JSONResponse({
        "success": True,
        "data": {
            "identity_id": identity.identity_id,
            "display_name": identity.display_name,
            "level": identity.level,
            "group_id": identity.group_id,
            "platforms": [
                {
                    "platform": pi.platform.value,
                    "user_id": pi.platform_user_id,
                    "display_name": pi.display_name
                }
                for pi in identity.platform_identities
            ],
            "last_active": identity.last_active.isoformat()
        }
    })


@app.get("/api/sessions")
async def list_sessions(
    active_within_minutes: Optional[int] = None,
    identity_id: Optional[str] = None
):
    """列出活跃会话"""
    sessions = gateway.list_sessions(
        identity_id=identity_id,
        active_within_minutes=active_within_minutes
    )
    
    return JSONResponse({
        "success": True,
        "data": sessions
    })


@app.get("/api/session/{session_key:path}")
async def get_session(session_key: str):
    """获取会话信息"""
    session = gateway.get_session(session_key)
    
    if not session:
        return JSONResponse(
            {"success": False, "error": f"会话不存在: {session_key}"},
            status_code=404
        )
    
    return JSONResponse({
        "success": True,
        "data": session
    })


@app.get("/api/session/{session_key:path}/history")
async def get_session_history(session_key: str, limit: int = 20):
    """获取会话历史"""
    transcript = gateway.get_session_transcript(session_key, limit)
    
    history = [
        {
            "id": entry.id,
            "role": entry.role,
            "content": entry.content,
            "tool_name": entry.tool_name,
            "created_at": entry.created_at.isoformat()
        }
        for entry in transcript
    ]
    
    return JSONResponse({
        "success": True,
        "data": history
    })


@app.get("/api/queue/{session_key:path}")
async def get_queue_status(session_key: str):
    """获取队列状态"""
    status = gateway.get_queue_status(session_key)
    return JSONResponse(status)


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket 接口
    
    实时双向通信
    """
    await websocket.accept()
    
    ws_adapter = adapter_manager.get_adapter(Platform.WEBSOCKET)
    if isinstance(ws_adapter, type(adapter_manager.get_adapter(Platform.WEBSOCKET))):
        ws_adapter.register_connection(user_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            
            result = await adapter_manager.receive(
                platform=Platform.WEBSOCKET,
                content=data,
                user_id=user_id
            )
            
            await websocket.send_json(result)
            
    except WebSocketDisconnect:
        pass
    finally:
        if isinstance(ws_adapter, type(adapter_manager.get_adapter(Platform.WEBSOCKET))):
            ws_adapter.unregister_connection(user_id)


@app.get("/api/tools")
async def list_tools():
    """列出可用工具"""
    from core.v2 import get_v2_tools
    return JSONResponse(get_v2_tools(gateway))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """管理面板"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>XiaoMengCore v2 Dashboard</title>
        <meta charset="utf-8">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            h1 { text-align: center; margin-bottom: 30px; color: #00d9ff; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
            .card { background: #16213e; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
            .card h2 { color: #00d9ff; margin-bottom: 15px; font-size: 18px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; color: #888; font-size: 14px; }
            input, select, textarea { width: 100%; padding: 10px; border: 1px solid #333; border-radius: 6px; background: #0f0f23; color: #fff; font-size: 14px; }
            button { background: linear-gradient(135deg, #00d9ff, #0099cc); color: #fff; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; width: 100%; }
            button:hover { opacity: 0.9; }
            .result { margin-top: 15px; padding: 15px; background: #0f0f23; border-radius: 6px; font-family: monospace; font-size: 13px; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
            .status { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
            .status-dot { width: 12px; height: 12px; border-radius: 50%; background: #00ff00; animation: pulse 2s infinite; }
            @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
            .nav { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
            .nav button { width: auto; flex: 1; min-width: 120px; }
            .nav button.active { background: linear-gradient(135deg, #ff6b6b, #cc5555); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 XiaoMengCore v2 Dashboard</h1>
            
            <div class="status">
                <div class="status-dot"></div>
                <span>网关运行中</span>
            </div>
            
            <div class="nav">
                <button onclick="showPanel('message')" id="nav-message">发送消息</button>
                <button onclick="showPanel('identity')" id="nav-identity">身份管理</button>
                <button onclick="showPanel('sessions')" id="nav-sessions">会话列表</button>
            </div>
            
            <div class="grid">
                <div class="card" id="panel-message">
                    <h2>📨 发送消息</h2>
                    <div class="form-group">
                        <label>平台</label>
                        <select id="platform">
                            <option value="http">HTTP</option>
                            <option value="cli">CLI</option>
                            <option value="websocket">WebSocket</option>
                            <option value="qq">QQ</option>
                            <option value="wechat">微信</option>
                            <option value="telegram">Telegram</option>
                            <option value="discord">Discord</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>用户ID</label>
                        <input type="text" id="user_id" placeholder="user_001">
                    </div>
                    <div class="form-group">
                        <label>消息内容</label>
                        <textarea id="content" rows="3" placeholder="输入消息..."></textarea>
                    </div>
                    <button onclick="sendMessage()">发送</button>
                    <div class="result" id="message-result"></div>
                </div>
                
                <div class="card" id="panel-identity" style="display:none;">
                    <h2>🔗 身份关联</h2>
                    <div class="form-group">
                        <label>规范身份ID</label>
                        <input type="text" id="identity_id" placeholder="alice">
                    </div>
                    <div class="form-group">
                        <label>平台</label>
                        <select id="link_platform">
                            <option value="qq">QQ</option>
                            <option value="wechat">微信</option>
                            <option value="telegram">Telegram</option>
                            <option value="discord">Discord</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>平台用户ID</label>
                        <input type="text" id="platform_user_id" placeholder="12345">
                    </div>
                    <div class="form-group">
                        <label>显示名称</label>
                        <input type="text" id="display_name" placeholder="Alice">
                    </div>
                    <button onclick="linkIdentity()">关联</button>
                    <div class="result" id="identity-result"></div>
                </div>
                
                <div class="card" id="panel-sessions" style="display:none;">
                    <h2>📋 活跃会话</h2>
                    <button onclick="loadSessions()">刷新</button>
                    <div class="result" id="sessions-result"></div>
                </div>
            </div>
        </div>
        
        <script>
            function showPanel(name) {
                document.querySelectorAll('[id^="panel-"]').forEach(p => p.style.display = 'none');
                document.getElementById('panel-' + name).style.display = 'block';
                document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
                document.getElementById('nav-' + name).classList.add('active');
            }
            
            async function sendMessage() {
                const platform = document.getElementById('platform').value;
                const user_id = document.getElementById('user_id').value || 'test_user';
                const content = document.getElementById('content').value;
                
                const res = await fetch('/api/message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content, user_id, platform})
                });
                
                const data = await res.json();
                document.getElementById('message-result').textContent = JSON.stringify(data, null, 2);
            }
            
            async function linkIdentity() {
                const identity_id = document.getElementById('identity_id').value;
                const platform = document.getElementById('link_platform').value;
                const platform_user_id = document.getElementById('platform_user_id').value;
                const display_name = document.getElementById('display_name').value;
                
                const res = await fetch('/api/identity/link', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({identity_id, platform, platform_user_id, display_name})
                });
                
                const data = await res.json();
                document.getElementById('identity-result').textContent = JSON.stringify(data, null, 2);
            }
            
            async function loadSessions() {
                const res = await fetch('/api/sessions');
                const data = await res.json();
                document.getElementById('sessions-result').textContent = JSON.stringify(data, null, 2);
            }
        </script>
    </body>
    </html>
    """


async def main():
    print("=" * 60)
    print("XiaoMengCore v2 统一网关")
    print("=" * 60)
    print("\n核心特性:")
    print("  ✓ 跨平台身份统一 (QQ/微信/Telegram等)")
    print("  ✓ 统一会话管理 (同一用户跨平台共享会话)")
    print("  ✓ 消息队列系统 (STEER/FOLLOWUP/COLLECT)")
    print("  ✓ 钩子系统 (Agent生命周期注入)")
    print("  ✓ 双层持久化 (sessions.json + .jsonl)")
    print("\nAPI 端点:")
    print("  POST /api/message       - 统一消息入口")
    print("  POST /api/identity/link - 关联平台身份")
    print("  GET  /api/sessions      - 列出活跃会话")
    print("  GET  /dashboard         - 管理面板")
    print("  WS   /ws/{user_id}      - WebSocket")
    print("\n" + "=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
