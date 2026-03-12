"""
启动统一网关
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ConfigManager


async def main():
    print("=" * 60)
    print("XiaoMengCore 统一网关")
    print("=" * 60)
    
    cm = ConfigManager.get_instance()
    config_path = os.path.join(os.path.dirname(__file__), "..", "data", "config.json")
    if os.path.exists(config_path):
        cm.load(config_path)
    
    from core.gateway import Gateway, default_processor
    
    gateway = Gateway.get_instance()
    gateway.register_processor("default", default_processor)
    
    print("\n✅ Gateway 初始化完成")
    print("\n消息入口:")
    print("  - HTTP POST /api/message")
    print("  - WebSocket /ws/{user_id}")
    print("  - WebChat /webchat/{session_id}")
    print("\n会话管理:")
    print("  - GET /api/sessions")
    print("  - GET /api/session/{session_key}")
    print("  - DELETE /api/session/{session_key}")
    print("=" * 60)
    
    import uvicorn
    from gateway.unified import app
    
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
