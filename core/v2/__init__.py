"""
XiaoMengCore v2 - 统一网关架构

核心特性：
1. 跨平台身份统一 - 同一用户在不同平台共享身份
2. 统一会话管理 - 跨平台对话连续性
3. 消息队列系统 - 支持 STEER/FOLLOWUP/COLLECT 模式
4. 钩子系统 - Agent 生命周期注入
5. 双层持久化 - sessions.json + .jsonl 记录

使用示例：

    from core.v2 import GatewayV2, Platform, IncomingMessage
    
    # 初始化网关
    gateway = GatewayV2.get_instance()
    
    # 注册处理器
    async def my_processor(content, session_key, identity, metadata):
        return f"收到: {content}"
    
    gateway.register_processor("default", my_processor)
    
    # 关联平台身份（跨平台统一）
    gateway.link_platform("alice", Platform.QQ, "12345")
    gateway.link_platform("alice", Platform.WECHAT, "wxid_xxx")
    
    # 接收消息
    await gateway.receive(IncomingMessage(
        content="你好",
        platform=Platform.QQ,
        platform_user_id="12345"
    ))
    
    # 无论从 QQ 还是微信发消息，都会路由到同一个会话
"""

from .identity import (
    Identity,
    IdentityManager,
    Platform,
    PlatformIdentity
)

from core.router import UnifiedIdentity

from .queue import (
    MessageQueue,
    QueueMode,
    QueuedMessage
)

from .hooks import (
    HookSystem,
    HookPoint,
    HookContext,
    hook
)

from .session import (
    SessionStore,
    TranscriptEntry,
    TranscriptStore
)

from .gateway import (
    GatewayV2,
    IncomingMessage,
    OutgoingMessage,
    create_simple_processor
)

from .adapters import (
    ChannelAdapter,
    AdapterManager,
    CLIAdapter,
    HTTPAdapter,
    WebSocketAdapter,
    QQAdapter,
    WeChatAdapter,
    TelegramAdapter,
    DiscordAdapter
)

from .tools import (
    SessionTools,
    IdentityTools,
    ToolResult,
    get_v2_tools
)

from .compaction import (
    Compactor,
    AutoCompactor,
    CompactionConfig,
    CompactionResult
)

__all__ = [
    "Identity",
    "IdentityManager",
    "Platform",
    "PlatformIdentity",
    "UnifiedIdentity",
    "MessageQueue",
    "QueueMode",
    "QueuedMessage",
    "HookSystem",
    "HookPoint",
    "HookContext",
    "hook",
    "SessionStore",
    "TranscriptEntry",
    "TranscriptStore",
    "GatewayV2",
    "IncomingMessage",
    "OutgoingMessage",
    "create_simple_processor",
    "ChannelAdapter",
    "AdapterManager",
    "CLIAdapter",
    "HTTPAdapter",
    "WebSocketAdapter",
    "QQAdapter",
    "WeChatAdapter",
    "TelegramAdapter",
    "DiscordAdapter",
    "SessionTools",
    "IdentityTools",
    "ToolResult",
    "get_v2_tools",
    "Compactor",
    "AutoCompactor",
    "CompactionConfig",
    "CompactionResult"
]
