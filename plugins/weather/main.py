"""
天气插件示例

展示如何创建 XiaoMengCore 插件
"""

import asyncio
from typing import Dict, Any, Optional

HANDLERS = {}
TOOLS = []


async def on_load():
    """插件加载时调用"""
    print("🌤️ 天气插件已加载")


async def on_unload():
    """插件卸载时调用"""
    print("🌤️ 天气插件已卸载")


async def on_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """消息处理器"""
    content = message.get("content", "")
    
    if "天气" in content:
        return {
            "type": "response",
            "content": "我可以帮你查询天气，请告诉我你想查询哪个城市的天气？"
        }
    
    return None


async def query_weather(city: str) -> Dict[str, Any]:
    """查询天气（示例）"""
    return {
        "success": True,
        "city": city,
        "weather": "晴",
        "temperature": "25°C",
        "humidity": "60%",
        "wind": "东南风 3级"
    }


HANDLERS["on_message"] = on_message
HANDLERS["on_load"] = on_load
HANDLERS["on_unload"] = on_unload

TOOLS.append({
    "name": "query_weather",
    "description": "查询指定城市的天气",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称"
            }
        },
        "required": ["city"]
    },
    "handler": query_weather
})
