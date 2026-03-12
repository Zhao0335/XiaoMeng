"""
XiaoMengCore 子Agent系统

基于三层模型架构设计：
- Basic层：主Agent，快速响应用户
- Brain层：思考子Agent，深度处理复杂任务
- Special层：专家子Agent，专人专事（代码、多模态等）

特点：
1. 不阻塞主对话
2. 自动汇报完成
3. 支持多模态扩展
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any, Callable, Awaitable
from enum import Enum
import json


class SubagentStatus(Enum):
    """子Agent状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class SubagentType(Enum):
    """子Agent类型 - 对应模型层"""
    THINKER = "thinker"      # Brain层 - 深度思考
    CODER = "coder"          # Special层 - 代码专家
    VISION = "vision"        # Special层 - 视觉专家
    REASONING = "reasoning"  # Special层 - 推理专家
    CUSTOM = "custom"        # 自定义 - 多模态插件


@dataclass
class SubagentRun:
    """子Agent运行实例"""
    run_id: str
    agent_type: SubagentType
    task: str
    status: SubagentStatus = SubagentStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    parent_session_key: Optional[str] = None
    child_session_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "agent_type": self.agent_type.value,
            "task": self.task[:100] + "..." if len(self.task) > 100 else self.task,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_preview": self.result[:200] + "..." if self.result and len(self.result) > 200 else self.result,
            "error": self.error
        }


@dataclass
class SubagentConfig:
    """子Agent配置"""
    agent_type: SubagentType
    model_layer: str  # basic, brain, special
    model_role: Optional[str] = None  # code, vision, reasoning
    max_tokens: int = 4096
    timeout_seconds: int = 300
    tools: List[str] = field(default_factory=list)
    system_prompt_suffix: str = ""


SUBAGENT_CONFIGS: Dict[SubagentType, SubagentConfig] = {
    SubagentType.THINKER: SubagentConfig(
        agent_type=SubagentType.THINKER,
        model_layer="brain",
        max_tokens=8192,
        timeout_seconds=600,
        tools=["read", "write", "grep", "find", "web_search"],
        system_prompt_suffix="You are a deep thinking agent. Take your time to analyze thoroughly."
    ),
    SubagentType.CODER: SubagentConfig(
        agent_type=SubagentType.CODER,
        model_layer="special",
        model_role="code",
        max_tokens=4096,
        timeout_seconds=300,
        tools=["read", "write", "edit", "exec", "grep", "find"],
        system_prompt_suffix="You are a code expert. Focus on writing clean, efficient code."
    ),
    SubagentType.VISION: SubagentConfig(
        agent_type=SubagentType.VISION,
        model_layer="special",
        model_role="vision",
        max_tokens=2048,
        timeout_seconds=120,
        tools=["image", "read"],
        system_prompt_suffix="You are a vision expert. Analyze images thoroughly."
    ),
    SubagentType.REASONING: SubagentConfig(
        agent_type=SubagentType.REASONING,
        model_layer="special",
        model_role="reasoning",
        max_tokens=4096,
        timeout_seconds=300,
        tools=["read", "web_search", "web_fetch"],
        system_prompt_suffix="You are a reasoning expert. Think step by step."
    ),
}


class SubagentRegistry:
    """子Agent注册表 - 管理所有子Agent运行"""
    
    _instance: Optional["SubagentRegistry"] = None
    
    def __init__(self, max_children_per_agent: int = 5, max_spawn_depth: int = 2):
        self._runs: Dict[str, SubagentRun] = {}
        self._max_children = max_children_per_agent
        self._max_depth = max_spawn_depth
        self._spawn_depths: Dict[str, int] = {}
        self._completion_handlers: List[Callable[[SubagentRun], Awaitable[None]]] = []
    
    @classmethod
    def get_instance(cls) -> "SubagentRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_completion_handler(self, handler: Callable[[SubagentRun], Awaitable[None]]):
        """注册完成回调"""
        self._completion_handlers.append(handler)
    
    async def _notify_completion(self, run: SubagentRun):
        """通知完成"""
        for handler in self._completion_handlers:
            try:
                await handler(run)
            except Exception as e:
                print(f"Completion handler error: {e}")
    
    def spawn(
        self,
        agent_type: SubagentType,
        task: str,
        parent_session_key: str,
        context: Optional[Dict[str, Any]] = None
    ) -> SubagentRun:
        """创建子Agent"""
        parent_depth = self._spawn_depths.get(parent_session_key, 0)
        
        if parent_depth >= self._max_depth:
            raise ValueError(f"Max spawn depth reached ({self._max_depth})")
        
        active_children = sum(
            1 for r in self._runs.values()
            if r.parent_session_key == parent_session_key and r.status == SubagentStatus.RUNNING
        )
        
        if active_children >= self._max_children:
            raise ValueError(f"Max children reached ({self._max_children})")
        
        run_id = f"sub_{uuid.uuid4().hex[:12]}"
        child_session_key = f"subagent:{run_id}"
        
        run = SubagentRun(
            run_id=run_id,
            agent_type=agent_type,
            task=task,
            parent_session_key=parent_session_key,
            child_session_key=child_session_key,
            metadata={"context": context or {}, "depth": parent_depth + 1}
        )
        
        self._runs[run_id] = run
        self._spawn_depths[child_session_key] = parent_depth + 1
        
        return run
    
    def get(self, run_id: str) -> Optional[SubagentRun]:
        """获取子Agent运行"""
        return self._runs.get(run_id)
    
    def list_runs(
        self,
        parent_session_key: Optional[str] = None,
        status: Optional[SubagentStatus] = None
    ) -> List[SubagentRun]:
        """列出子Agent运行"""
        runs = list(self._runs.values())
        
        if parent_session_key:
            runs = [r for r in runs if r.parent_session_key == parent_session_key]
        
        if status:
            runs = [r for r in runs if r.status == status]
        
        return sorted(runs, key=lambda r: r.created_at, reverse=True)
    
    def update_status(self, run_id: str, status: SubagentStatus, **kwargs):
        """更新状态"""
        run = self._runs.get(run_id)
        if not run:
            return
        
        run.status = status
        
        if status == SubagentStatus.RUNNING:
            run.started_at = datetime.now()
        elif status in (SubagentStatus.COMPLETED, SubagentStatus.FAILED, SubagentStatus.KILLED):
            run.completed_at = datetime.now()
        
        for key, value in kwargs.items():
            if hasattr(run, key):
                setattr(run, key, value)
    
    async def complete(self, run_id: str, result: str):
        """标记完成"""
        self.update_status(run_id, SubagentStatus.COMPLETED, result=result)
        run = self._runs.get(run_id)
        if run:
            await self._notify_completion(run)
    
    async def fail(self, run_id: str, error: str):
        """标记失败"""
        self.update_status(run_id, SubagentStatus.FAILED, error=error)
        run = self._runs.get(run_id)
        if run:
            await self._notify_completion(run)
    
    def kill(self, run_id: str) -> bool:
        """终止子Agent"""
        run = self._runs.get(run_id)
        if not run or run.status not in (SubagentStatus.PENDING, SubagentStatus.RUNNING):
            return False
        
        self.update_status(run_id, SubagentStatus.KILLED)
        return True
    
    def clear_completed(self, max_age_hours: int = 24):
        """清理已完成的运行"""
        cutoff = datetime.now()
        to_remove = []
        
        for run_id, run in self._runs.items():
            if run.status in (SubagentStatus.COMPLETED, SubagentStatus.FAILED, SubagentStatus.KILLED):
                if run.completed_at:
                    age_hours = (cutoff - run.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(run_id)
        
        for run_id in to_remove:
            del self._runs[run_id]
        
        return len(to_remove)


class SubagentExecutor:
    """子Agent执行器 - 实际运行子Agent"""
    
    def __init__(self, registry: SubagentRegistry):
        self._registry = registry
        self._tasks: Dict[str, asyncio.Task] = {}
    
    async def execute(self, run: SubagentRun, context: Dict[str, Any]) -> str:
        """执行子Agent任务"""
        config = SUBAGENT_CONFIGS.get(run.agent_type)
        if not config:
            raise ValueError(f"Unknown agent type: {run.agent_type}")
        
        self._registry.update_status(run.run_id, SubagentStatus.RUNNING)
        
        try:
            from core.model_layer import ModelLayerRouter, ModelLayer, ModelRole
            from core.system_prompt import build_subagent_system_prompt
            
            router = ModelLayerRouter.get_instance()
            
            layer = ModelLayer.BRAIN if config.model_layer == "brain" else ModelLayer.SPECIAL
            role = None
            if config.model_role:
                for r in ModelRole:
                    if r.value == config.model_role:
                        role = r
                        break
            
            adapter = router.get_available_adapter(layer, role)
            if not adapter:
                raise ValueError(f"No available adapter for {layer}/{role}")
            
            tools_str = ", ".join(config.tools)
            system_prompt = f"""You are a sub-agent of type {run.agent_type.value}.
{config.system_prompt_suffix}

Available tools: {tools_str}

Task: {run.task}

Complete this task and report your findings. Be thorough and accurate."""
            
            messages = [{
                "role": "user",
                "content": f"Please complete the following task:\n\n{run.task}"
            }]
            
            if context.get("files"):
                files_context = "\n\nRelevant files:\n"
                for path, content in context["files"].items():
                    files_context += f"\n--- {path} ---\n{content[:2000]}\n"
                messages[0]["content"] += files_context
            
            tools_schema = None
            tool_registry = None
            if config.tools:
                from core.tools import ToolRegistry
                tool_registry = ToolRegistry.get_instance()
                tools_schema = tool_registry.get_tools_schema_by_names(config.tools)
            
            max_iterations = 10
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                
                response = await asyncio.wait_for(
                    adapter.chat(messages, system_prompt, tools=tools_schema),
                    timeout=config.timeout_seconds
                )
                
                if not response.tool_calls:
                    result = response.content
                    await self._registry.complete(run.run_id, result)
                    return result
                
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("arguments", {})) if isinstance(tc.get("arguments"), dict) else tc.get("arguments", "{}")
                            }
                        } for tc in response.tool_calls
                    ]
                })
                
                for tool_call in response.tool_calls:
                    if tool_registry:
                        try:
                            args = tool_call.get("arguments", {})
                            if isinstance(args, str):
                                args = json.loads(args)
                            
                            from models import User, UserLevel
                            system_user = User(user_id="subagent", level=UserLevel.OWNER)
                            
                            tool_result = await tool_registry.execute(
                                tool_call.get("name", ""),
                                system_user,
                                **args
                            )
                            
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "content": tool_result.content if tool_result.success else f"Error: {tool_result.error}"
                            })
                        except Exception as e:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "content": f"Error: {str(e)}"
                            })
            
            result = response.content if response else "Max iterations reached"
            await self._registry.complete(run.run_id, result)
            return result
            
        except asyncio.TimeoutError:
            error = f"Subagent timed out after {config.timeout_seconds}s"
            await self._registry.fail(run.run_id, error)
            raise
        except Exception as e:
            await self._registry.fail(run.run_id, str(e))
            raise
    
    async def spawn_and_execute(
        self,
        agent_type: SubagentType,
        task: str,
        parent_session_key: str,
        context: Optional[Dict[str, Any]] = None
    ) -> SubagentRun:
        """创建并执行子Agent"""
        run = self._registry.spawn(agent_type, task, parent_session_key, context)
        
        async def _run():
            try:
                await self.execute(run, context or {})
            except Exception as e:
                pass
        
        task = asyncio.create_task(_run())
        self._tasks[run.run_id] = task
        
        return run
    
    def cancel(self, run_id: str) -> bool:
        """取消执行"""
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            return True
        return False


class MultimodalSubagentExtension:
    """多模态子Agent扩展接口"""
    
    def __init__(self):
        self._plugins: Dict[str, SubagentConfig] = {}
    
    def register(
        self,
        name: str,
        model_role: str,
        tools: List[str],
        system_prompt_suffix: str,
        max_tokens: int = 2048,
        timeout_seconds: int = 120
    ):
        """注册多模态子Agent类型"""
        config = SubagentConfig(
            agent_type=SubagentType.CUSTOM,
            model_layer="special",
            model_role=model_role,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            tools=tools,
            system_prompt_suffix=system_prompt_suffix
        )
        self._plugins[name] = config
        
        global SUBAGENT_CONFIGS
        custom_type = SubagentType.CUSTOM
        SUBAGENT_CONFIGS[f"custom_{name}"] = config
    
    def list_plugins(self) -> List[str]:
        """列出已注册的多模态插件"""
        return list(self._plugins.keys())


def create_default_multimodal_extensions() -> MultimodalSubagentExtension:
    """创建默认的多模态扩展"""
    ext = MultimodalSubagentExtension()
    
    ext.register(
        name="audio",
        model_role="audio",
        tools=["read"],
        system_prompt_suffix="You are an audio analysis expert. Transcribe and analyze audio content.",
        max_tokens=2048,
        timeout_seconds=180
    )
    
    ext.register(
        name="video",
        model_role="vision",
        tools=["image", "read"],
        system_prompt_suffix="You are a video analysis expert. Analyze video frames and content.",
        max_tokens=4096,
        timeout_seconds=300
    )
    
    ext.register(
        name="document",
        model_role="vision",
        tools=["read", "image"],
        system_prompt_suffix="You are a document analysis expert. Extract and analyze document content.",
        max_tokens=4096,
        timeout_seconds=180
    )
    
    return ext
