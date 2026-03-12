"""
XiaoMengCore v2 - 钩子系统

参考 OpenClaw 的钩子机制，在 Agent 生命周期的关键点注入自定义逻辑

钩子点：
- before_agent_start: 运行开始前
- agent_end: 运行结束后
- before_tool_call: 工具调用前
- after_tool_call: 工具调用后
- message_received: 收到消息时
- message_sending: 发送消息前
- message_sent: 发送消息后
- session_start: 会话开始
- session_end: 会话结束
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable, Union
from datetime import datetime
from pathlib import Path
import asyncio
import json


class HookPoint(Enum):
    BEFORE_AGENT_START = "before_agent_start"
    AGENT_END = "agent_end"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    TOOL_RESULT_PERSIST = "tool_result_persist"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"


@dataclass
class HookContext:
    hook_point: HookPoint
    session_key: str
    identity_id: Optional[str] = None
    run_id: Optional[str] = None
    message: Optional[Any] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    tool_result: Optional[Any] = None
    response: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hook_point": self.hook_point.value,
            "session_key": self.session_key,
            "identity_id": self.identity_id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "metadata": self.metadata
        }


HookHandler = Callable[[HookContext], Awaitable[Optional[HookContext]]]


@dataclass
class HookEntry:
    name: str
    hook_point: HookPoint
    handler: HookHandler
    priority: int = 100
    enabled: bool = True
    
    def __lt__(self, other):
        return self.priority < other.priority


class HookSystem:
    """
    钩子系统
    
    允许在 Agent 生命周期的关键点注入自定义逻辑
    """
    
    _instance: Optional["HookSystem"] = None
    
    def __init__(self):
        self._hooks: Dict[HookPoint, List[HookEntry]] = {
            point: [] for point in HookPoint
        }
        self._hook_results: Dict[str, List[Dict]] = {}
    
    @classmethod
    def get_instance(cls) -> "HookSystem":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(
        self,
        name: str,
        hook_point: HookPoint,
        handler: HookHandler,
        priority: int = 100
    ) -> str:
        """
        注册钩子
        
        Args:
            name: 钩子名称
            hook_point: 钩子点
            handler: 处理函数
            priority: 优先级（数字越小越先执行）
        
        Returns:
            钩子名称
        """
        entry = HookEntry(
            name=name,
            hook_point=hook_point,
            handler=handler,
            priority=priority
        )
        
        self._hooks[hook_point].append(entry)
        self._hooks[hook_point].sort()
        
        return name
    
    def unregister(self, name: str, hook_point: Optional[HookPoint] = None):
        """注销钩子"""
        if hook_point:
            self._hooks[hook_point] = [
                h for h in self._hooks[hook_point] if h.name != name
            ]
        else:
            for point in HookPoint:
                self._hooks[point] = [
                    h for h in self._hooks[point] if h.name != name
                ]
    
    def enable_hook(self, name: str, hook_point: HookPoint):
        for hook in self._hooks[hook_point]:
            if hook.name == name:
                hook.enabled = True
    
    def disable_hook(self, name: str, hook_point: HookPoint):
        for hook in self._hooks[hook_point]:
            if hook.name == name:
                hook.enabled = False
    
    async def trigger(self, context: HookContext) -> HookContext:
        """
        触发钩子
        
        按优先级顺序执行所有注册的钩子
        钩子可以修改 context 并返回，或返回 None 终止链
        """
        hooks = self._hooks.get(context.hook_point, [])
        
        for hook in hooks:
            if not hook.enabled:
                continue
            
            try:
                result = await hook.handler(context)
                
                if result is None:
                    return context
                
                context = result
                
            except Exception as e:
                print(f"钩子 {hook.name} 执行失败: {e}")
        
        return context
    
    def list_hooks(self, hook_point: Optional[HookPoint] = None) -> List[Dict]:
        if hook_point:
            hooks = self._hooks.get(hook_point, [])
            return [{"name": h.name, "priority": h.priority, "enabled": h.enabled} for h in hooks]
        
        result = []
        for point, hooks in self._hooks.items():
            for h in hooks:
                result.append({
                    "name": h.name,
                    "hook_point": point.value,
                    "priority": h.priority,
                    "enabled": h.enabled
                })
        return result


def hook(name: str, hook_point: HookPoint, priority: int = 100):
    """
    钩子装饰器
    
    用法：
    @hook("my_hook", HookPoint.BEFORE_TOOL_CALL)
    async def my_handler(context: HookContext) -> Optional[HookContext]:
        # 处理逻辑
        return context
    """
    def decorator(func: HookHandler) -> HookHandler:
        HookSystem.get_instance().register(name, hook_point, func, priority)
        return func
    return decorator


class BuiltinHooks:
    """内置钩子"""
    
    @staticmethod
    @hook("logging", HookPoint.MESSAGE_RECEIVED, priority=1000)
    async def log_message_received(context: HookContext) -> HookContext:
        print(f"[{context.hook_point.value}] session={context.session_key}")
        return context
    
    @staticmethod
    @hook("logging", HookPoint.BEFORE_TOOL_CALL, priority=1000)
    async def log_tool_call(context: HookContext) -> HookContext:
        print(f"[TOOL] {context.tool_name}({context.tool_args})")
        return context
    
    @staticmethod
    @hook("rate_limit", HookPoint.BEFORE_TOOL_CALL, priority=50)
    async def rate_limit_check(context: HookContext) -> Optional[HookContext]:
        dangerous_tools = ["exec", "system.run", "bash"]
        if context.tool_name in dangerous_tools:
            context.metadata["requires_approval"] = True
        return context
    
    @staticmethod
    @hook("filter_sensitive", HookPoint.AFTER_TOOL_CALL, priority=50)
    async def filter_sensitive_data(context: HookContext) -> HookContext:
        if context.tool_result:
            result_str = str(context.tool_result)
            import re
            result_str = re.sub(r'api[_-]?key["\s:=]+[\w-]+', 'api_key=***', result_str, flags=re.I)
            result_str = re.sub(r'password["\s:=]+[\w-]+', 'password=***', result_str, flags=re.I)
            context.tool_result = result_str
        return context
