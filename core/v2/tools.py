"""
XiaoMengCore v2 - 会话工具

参考 OpenClaw 的会话工具：
- sessions_list: 列出活跃会话
- sessions_history: 获取会话历史
- sessions_send: 跨会话通信
- sessions_abort: 中断会话运行
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime

from .gateway import GatewayV2
from .identity import Platform


@dataclass
class ToolResult:
    success: bool
    message: str
    data: Any = None


class SessionTools:
    """会话相关工具"""
    
    def __init__(self, gateway: GatewayV2):
        self._gateway = gateway
    
    async def sessions_list(
        self,
        active_within_minutes: Optional[int] = None,
        identity_id: Optional[str] = None
    ) -> ToolResult:
        """
        列出活跃会话
        
        用法示例：
        sessions_list(active_within_minutes=60)  # 最近1小时活跃的会话
        sessions_list(identity_id="alice")       # alice 的所有会话
        """
        sessions = self._gateway.list_sessions(
            identity_id=identity_id,
            active_within_minutes=active_within_minutes
        )
        
        session_list = []
        for s in sessions:
            session_list.append({
                "session_key": s["session_key"],
                "identity_id": s["identity_id"],
                "channel": s.get("channel"),
                "message_count": s.get("message_count", 0),
                "last_active": s["last_active"]
            })
        
        return ToolResult(
            success=True,
            message=f"找到 {len(session_list)} 个会话",
            data=session_list
        )
    
    async def sessions_history(
        self,
        session_key: str,
        limit: int = 20
    ) -> ToolResult:
        """
        获取会话历史
        
        用法示例：
        sessions_history(session_key="agent:main:identity:alice", limit=50)
        """
        session = self._gateway.get_session(session_key)
        if not session:
            return ToolResult(
                success=False,
                message=f"会话不存在: {session_key}"
            )
        
        transcript = self._gateway.get_session_transcript(session_key, limit)
        
        history = []
        for entry in transcript:
            history.append({
                "role": entry.role,
                "content": entry.content,
                "tool_name": entry.tool_name,
                "created_at": entry.created_at.isoformat()
            })
        
        return ToolResult(
            success=True,
            message=f"获取到 {len(history)} 条记录",
            data={
                "session_key": session_key,
                "identity_id": session.get("identity_id"),
                "history": history
            }
        )
    
    async def sessions_send(
        self,
        session_key: str,
        message: str,
        from_identity_id: Optional[str] = None
    ) -> ToolResult:
        """
        跨会话发送消息
        
        允许 Agent 向其他会话发送消息
        
        用法示例：
        sessions_send(
            session_key="agent:main:identity:bob",
            message="Alice 让我告诉你：明天开会"
        )
        """
        success = await self._gateway.send_to_session(
            session_key=session_key,
            content=message,
            from_identity_id=from_identity_id
        )
        
        if success:
            return ToolResult(
                success=True,
                message=f"消息已发送到会话: {session_key}"
            )
        else:
            return ToolResult(
                success=False,
                message=f"发送失败，会话不存在: {session_key}"
            )
    
    async def sessions_abort(
        self,
        session_key: str,
        run_id: str
    ) -> ToolResult:
        """
        中断会话运行
        
        用法示例：
        sessions_abort(session_key="agent:main:identity:alice", run_id="msg_xxx")
        """
        from .queue import MessageQueue
        queue = MessageQueue.get_instance()
        
        success = await queue.abort_run(session_key, run_id)
        
        if success:
            return ToolResult(
                success=True,
                message=f"已中断运行: {run_id}"
            )
        else:
            return ToolResult(
                success=False,
                message=f"中断失败，运行不存在或已完成: {run_id}"
            )


class IdentityTools:
    """身份相关工具"""
    
    def __init__(self, gateway: GatewayV2):
        self._gateway = gateway
    
    async def identity_info(
        self,
        identity_id: str
    ) -> ToolResult:
        """
        获取身份信息
        
        用法示例：
        identity_info(identity_id="alice")
        """
        identity = self._gateway.get_identity(identity_id)
        
        if not identity:
            return ToolResult(
                success=False,
                message=f"身份不存在: {identity_id}"
            )
        
        return ToolResult(
            success=True,
            message="获取成功",
            data={
                "identity_id": identity.identity_id,
                "display_name": identity.display_name,
                "level": identity.level,
                "group_id": identity.group_id,
                "platforms": [
                    {"platform": pi.platform.value, "user_id": pi.platform_user_id}
                    for pi in identity.platform_identities
                ],
                "last_active": identity.last_active.isoformat()
            }
        )
    
    async def identity_link(
        self,
        identity_id: str,
        platform: str,
        platform_user_id: str,
        display_name: Optional[str] = None
    ) -> ToolResult:
        """
        关联平台身份
        
        用法示例：
        identity_link(
            identity_id="alice",
            platform="wechat",
            platform_user_id="wxid_xxx",
            display_name="Alice Wang"
        )
        """
        try:
            platform_enum = Platform(platform)
        except ValueError:
            return ToolResult(
                success=False,
                message=f"无效的平台: {platform}"
            )
        
        success = self._gateway.link_platform(
            identity_id=identity_id,
            platform=platform_enum,
            platform_user_id=platform_user_id,
            display_name=display_name
        )
        
        if success:
            return ToolResult(
                success=True,
                message=f"已关联 {platform}:{platform_user_id} -> {identity_id}"
            )
        else:
            return ToolResult(
                success=False,
                message=f"关联失败，身份不存在: {identity_id}"
            )
    
    async def identity_resolve(
        self,
        platform: str,
        platform_user_id: str
    ) -> ToolResult:
        """
        解析平台身份
        
        用法示例：
        identity_resolve(platform="qq", platform_user_id="12345")
        """
        try:
            platform_enum = Platform(platform)
        except ValueError:
            return ToolResult(
                success=False,
                message=f"无效的平台: {platform}"
            )
        
        identity = self._gateway.resolve_identity(platform_enum, platform_user_id)
        
        if identity:
            return ToolResult(
                success=True,
                message="解析成功",
                data={
                    "identity_id": identity.identity_id,
                    "display_name": identity.display_name,
                    "level": identity.level
                }
            )
        else:
            return ToolResult(
                success=False,
                message=f"未找到关联的身份: {platform}:{platform_user_id}"
            )


def get_v2_tools(gateway: GatewayV2) -> List[Dict[str, Any]]:
    """获取 v2 工具定义"""
    return [
        {
            "name": "sessions_list",
            "description": "列出活跃会话",
            "parameters": {
                "type": "object",
                "properties": {
                    "active_within_minutes": {
                        "type": "integer",
                        "description": "筛选最近N分钟内活跃的会话"
                    },
                    "identity_id": {
                        "type": "string",
                        "description": "筛选特定身份的会话"
                    }
                }
            }
        },
        {
            "name": "sessions_history",
            "description": "获取会话历史记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_key": {
                        "type": "string",
                        "description": "会话键"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数量，默认20"
                    }
                },
                "required": ["session_key"]
            }
        },
        {
            "name": "sessions_send",
            "description": "跨会话发送消息，可以向其他会话发送消息",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_key": {
                        "type": "string",
                        "description": "目标会话键"
                    },
                    "message": {
                        "type": "string",
                        "description": "要发送的消息内容"
                    }
                },
                "required": ["session_key", "message"]
            }
        },
        {
            "name": "identity_info",
            "description": "获取身份信息，包括关联的平台账号",
            "parameters": {
                "type": "object",
                "properties": {
                    "identity_id": {
                        "type": "string",
                        "description": "身份ID"
                    }
                },
                "required": ["identity_id"]
            }
        },
        {
            "name": "identity_link",
            "description": "关联平台身份，将平台账号关联到规范身份，实现跨平台统一",
            "parameters": {
                "type": "object",
                "properties": {
                    "identity_id": {
                        "type": "string",
                        "description": "规范身份ID"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["qq", "wechat", "telegram", "discord", "websocket", "http", "cli", "webchat", "plugin"],
                        "description": "平台名称"
                    },
                    "platform_user_id": {
                        "type": "string",
                        "description": "平台用户ID"
                    },
                    "display_name": {
                        "type": "string",
                        "description": "显示名称"
                    }
                },
                "required": ["identity_id", "platform", "platform_user_id"]
            }
        }
    ]
