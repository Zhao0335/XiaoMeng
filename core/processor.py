"""
XiaoMengCore 核心处理器
消息处理流程的核心逻辑，集成工具调用、技能系统和硬件控制

核心改进（与OpenClaw一致）：
1. 使用 build_agent_system_prompt 构建系统提示
2. 使用 SkillLoader 加载技能（6级优先级）
3. 使用 EnhancedModelManager 管理模型
4. 使用 EnhancedRouter 路由消息
5. 使用 SubagentRegistry 管理子Agent
"""

from typing import Optional, Dict, Any, List, Callable, Awaitable, AsyncGenerator, Set
from datetime import datetime
import asyncio
import re
import json
import platform as platform_module

from models import (
    User, Message, Response, Source, UserLevel, 
    MessageType, Emotion
)
from config import XiaoMengConfig, ConfigManager
from .user_manager import UserManager
from .session_manager import SessionManager
from .memory import MemoryManager
from .llm_client import LLMClient
from .tools import ToolRegistry, ToolResult
from .skills import SkillManager
from .hardware import HardwareManager, HardwareTool
from .model_layer import ModelLayerRouter, ModelLayer, ModelRole
from .self_improving import SelfImprovingAgent
from .subagent import SubagentRegistry, SubagentStatus

from .system_prompt import (
    build_agent_system_prompt,
    SystemPromptParams,
    PromptMode,
    CORE_TOOL_SUMMARIES
)
from .skill_loader import SkillLoader, SkillsLimits, SkillEligibilityContext
from .model_manager import EnhancedModelManager, ModelHealth, LoadBalancingConfig
from .router import EnhancedRouter, Platform, UnifiedIdentity


class Middleware:
    """中间件基类"""
    
    async def process(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class AuthMiddleware(Middleware):
    """认证中间件"""
    
    def __init__(self):
        self.user_manager = UserManager.get_instance()
    
    async def process(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        message: Message = context["message"]
        
        user = self.user_manager.identify_user(
            message.source, 
            message.metadata.get("channel_user_id", message.user.user_id)
        )
        
        context["user"] = user
        context["user_level"] = user.level
        
        return None


class PermissionMiddleware(Middleware):
    """权限检查中间件"""
    
    def __init__(self):
        self.user_manager = UserManager.get_instance()
    
    async def process(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user: User = context["user"]
        message: Message = context["message"]
        
        if self._contains_sensitive_request(message.content):
            if user.level == UserLevel.STRANGER:
                return {
                    "response": Response.create(
                        reply_to=message.message_id,
                        content="我是主人的AI女仆哦，不能帮您做这个呢~",
                        emotion=Emotion.NEUTRAL
                    )
                }
            elif user.level == UserLevel.WHITELIST:
                return {
                    "response": Response.create(
                        reply_to=message.message_id,
                        content="抱歉哦，这个只有主人能用呢~我只是主人的AI女仆(｡･ω･｡)",
                        emotion=Emotion.SHY
                    )
                }
        
        return None
    
    def _contains_sensitive_request(self, content: str) -> bool:
        sensitive_patterns = [
            r"执行.*命令",
            r"删除.*文件",
            r"修改.*配置",
            r"重启.*服务",
            r"查看.*密码",
            r"添加.*白名单",
            r"提升.*权限",
            r"修改.*人设"
        ]
        
        content_lower = content.lower()
        for pattern in sensitive_patterns:
            if re.search(pattern, content_lower):
                return True
        return False


class SessionMiddleware(Middleware):
    """会话管理中间件"""
    
    def __init__(self):
        self.session_manager = SessionManager.get_instance()
    
    async def process(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user: User = context["user"]
        message: Message = context["message"]
        
        session = self.session_manager.get_or_create_session(user)
        self.session_manager.add_message_to_session(session, message)
        
        context["session"] = session
        context["history"] = self.session_manager.get_context_for_llm(session)
        
        return None


class MemoryMiddleware(Middleware):
    """记忆管理中间件"""
    
    def __init__(self):
        self.memory_manager = MemoryManager.get_instance()
    
    async def process(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user: User = context["user"]
        message: Message = context["message"]
        is_group = context.get("is_group", False)
        
        memory_context = self.memory_manager.get_context_for_llm(
            user, message.content, is_group
        )
        
        context["memory_context"] = memory_context
        
        return None


class SkillMiddleware(Middleware):
    """技能匹配中间件"""
    
    def __init__(self):
        self.skill_manager = SkillManager.get_instance()
    
    async def process(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        message: Message = context["message"]
        
        skill = self.skill_manager.match_skill_for_request(message.content)
        if skill:
            context["matched_skill"] = skill
        
        return None


class MessageProcessor:
    """
    消息处理器
    
    核心处理流程：
    1. 接收消息
    2. 运行中间件链
    3. 调用 LLM
    4. 执行工具调用
    5. 返回响应
    """
    
    _instance: Optional["MessageProcessor"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[XiaoMengConfig] = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self._config = config or ConfigManager.get_instance().get()
        self._llm_client = LLMClient.get_instance()
        self._memory_manager = MemoryManager.get_instance()
        self._session_manager = SessionManager.get_instance()
        self._user_manager = UserManager.get_instance()
        self._tool_registry = ToolRegistry.get_instance()
        self._skill_manager = SkillManager.get_instance()
        self._hardware_manager = HardwareManager.get_instance()
        self._model_router = ModelLayerRouter.get_instance()
        self._self_improving = SelfImprovingAgent.get_instance()
        self._subagent_registry = SubagentRegistry.get_instance()
        
        self._skill_loader = SkillLoader(workspace_dir=self._config.data_dir)
        self._enhanced_model_manager: Optional[EnhancedModelManager] = None
        self._enhanced_router: Optional[EnhancedRouter] = None
        
        self._middlewares: List[Middleware] = []
        self._response_handlers: List[Callable] = []
        self._use_model_router = False
        self._use_enhanced_components = False
        
        self._setup_default_middlewares()
        self._setup_subagent_handlers()
        self._initialized = True
    
    def _setup_subagent_handlers(self):
        """设置子Agent完成处理器"""
        async def on_subagent_complete(run):
            if run.status == SubagentStatus.COMPLETED:
                system_message = Message(
                    message_id=f"subagent_{run.run_id}",
                    content=f"[System Message] Sub-agent ({run.agent_type.value}) completed:\n{run.result}",
                    user=User(user_id="system", level=UserLevel.OWNER),
                    source=Source.CLI
                )
                
                if run.parent_session_key:
                    self._session_manager.add_message_to_session_by_key(
                        run.parent_session_key,
                        system_message
                    )
            elif run.status == SubagentStatus.FAILED:
                system_message = Message(
                    message_id=f"subagent_{run.run_id}_error",
                    content=f"[System Message] Sub-agent ({run.agent_type.value}) failed: {run.error}",
                    user=User(user_id="system", level=UserLevel.OWNER),
                    source=Source.CLI
                )
                
                if run.parent_session_key:
                    self._session_manager.add_message_to_session_by_key(
                        run.parent_session_key,
                        system_message
                    )
        
        self._subagent_registry.register_completion_handler(on_subagent_complete)
    
    def enable_model_router(self, models_config: List[Dict] = None):
        from .model_layer import ModelEndpoint, ModelLayer, ModelRole
        
        if models_config:
            for cfg in models_config:
                endpoint = ModelEndpoint(
                    model_id=cfg["model_id"],
                    layer=ModelLayer(cfg["layer"]),
                    role=ModelRole(cfg["role"]),
                    endpoint=cfg["endpoint"],
                    model_name=cfg["model_name"],
                    api_key=cfg.get("api_key"),
                    max_tokens=cfg.get("max_tokens", 4096),
                    temperature=cfg.get("temperature", 0.7),
                    enabled=cfg.get("enabled", True),
                    priority=cfg.get("priority", 1)
                )
                self._model_router.register_model(endpoint)
        
        self._use_model_router = True
    
    async def enable_enhanced_components(
        self,
        model_endpoints: List[Dict] = None,
        router_storage_path: str = None
    ):
        """
        启用增强组件
        
        Args:
            model_endpoints: 模型端点配置列表
            router_storage_path: 路由存储路径
        """
        if model_endpoints:
            lb_config = LoadBalancingConfig(
                strategy="least_latency",
                max_retries=3,
                health_check_interval=60
            )
            self._enhanced_model_manager = EnhancedModelManager(load_balance_config=lb_config)
            
            from .model_manager import ModelEndpoint as EnhancedEndpoint, ModelLayer as EnhancedLayer
            
            endpoints = []
            for cfg in model_endpoints:
                ep = EnhancedEndpoint(
                    model_id=cfg["model_id"],
                    layer=EnhancedLayer(cfg.get("layer", "brain")),
                    endpoint=cfg["endpoint"],
                    model_name=cfg["model_name"],
                    api_key=cfg.get("api_key"),
                    max_tokens=cfg.get("max_tokens", 4096),
                    temperature=cfg.get("temperature", 0.7)
                )
                endpoints.append(ep)
            
            await self._enhanced_model_manager.initialize_parallel(endpoints)
        
        if router_storage_path:
            self._enhanced_router = EnhancedRouter(storage_path=router_storage_path)
        
        self._use_enhanced_components = True
        self._use_model_router = True
    
    def _setup_default_middlewares(self):
        self._middlewares = [
            AuthMiddleware(),
            PermissionMiddleware(),
            SessionMiddleware(),
            MemoryMiddleware(),
            SkillMiddleware()
        ]
    
    def add_middleware(self, middleware: Middleware):
        self._middlewares.append(middleware)
    
    def on_response(self, handler: Callable):
        self._response_handlers.append(handler)
    
    async def process(self, message: Message) -> Response:
        context = {
            "message": message,
            "user": None,
            "session": None,
            "history": [],
            "memory_context": "",
            "matched_skill": None,
            "is_group": message.metadata.get("is_group", False)
        }
        
        for middleware in self._middlewares:
            result = await middleware.process(context)
            if result is not None:
                response = result.get("response")
                if response:
                    await self._notify_response_handlers(response, message)
                    return response
        
        response = await self._generate_response(context)
        
        if response.tool_calls:
            tool_results = await self._execute_tool_calls(response, context)
            response.metadata["tool_results"] = tool_results
            
            if tool_results:
                follow_up = await self._generate_follow_up(context, response, tool_results)
                if follow_up:
                    response = follow_up
        
        if context.get("session"):
            self._session_manager.add_message_to_session(
                context["session"],
                Message.create(
                    source=message.source,
                    user=context["user"],
                    content=f"[AI] {response.content}",
                    emotion=response.emotion
                )
            )
        
        await self._notify_response_handlers(response, message)
        
        return response
    
    async def _generate_response(self, context: Dict[str, Any]) -> Response:
        user: User = context["user"]
        message: Message = context["message"]
        history: List = context.get("history", [])
        memory_context: str = context.get("memory_context", "")
        matched_skill = context.get("matched_skill")
        is_group = context.get("is_group", False)
        
        system_prompt = self._build_system_prompt(user, memory_context, matched_skill, is_group)
        
        messages = history + [{"role": "user", "content": message.content}]
        
        tools = self._tool_registry.get_tools_schema(user)
        
        hardware_tools = HardwareTool.get_tools_schema()
        tools.extend(hardware_tools)
        
        if self._use_model_router:
            full_prompt = self._build_system_prompt(user, memory_context, matched_skill, is_group, mode="full")
            minimal_prompt = self._build_system_prompt(user, memory_context, matched_skill, is_group, mode="minimal")
            
            model_response = await self._model_router.chat(
                messages=messages,
                system_prompt=full_prompt,
                tools=tools if tools else None,
                minimal_system_prompt=minimal_prompt
            )
            
            llm_response = {
                "content": model_response.content,
                "tool_calls": model_response.tool_calls,
                "model": model_response.model_name,
                "layer": model_response.layer.value,
                "latency_ms": model_response.latency_ms
            }
        else:
            llm_response = await self._llm_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools if tools else None
            )
        
        emotion = self._detect_emotion(llm_response["content"])
        
        return Response.create(
            reply_to=message.message_id,
            content=llm_response["content"],
            emotion=emotion,
            tool_calls=llm_response.get("tool_calls", []),
            metadata={
                "model": llm_response.get("model"),
                "layer": llm_response.get("layer"),
                "latency_ms": llm_response.get("latency_ms")
            }
        )
    
    def _build_system_prompt(self, user: User, memory_context: str, matched_skill=None, is_group: bool = False, mode: str = "full") -> str:
        tool_names = [t.name for t in self._tool_registry.get_all_tools()]
        tool_summaries = {t.name: t.description for t in self._tool_registry.get_all_tools()}
        
        skills_prompt = self._skill_loader.build_skills_prompt()
        
        persona_prompt = self._memory_manager.get_system_prompt(user, is_group=is_group)
        
        user_identity = f"Owner: {user.user_id}" if user.level == UserLevel.OWNER else f"User: {user.user_id}"
        
        user_level = user.level.value if user.level else "stranger"
        
        prompt_mode = PromptMode.FULL if mode == "full" else PromptMode.MINIMAL
        
        params = SystemPromptParams(
            workspace_dir=self._config.data_dir,
            tool_names=tool_names,
            tool_summaries=tool_summaries,
            skills_prompt=skills_prompt,
            persona_prompt=persona_prompt,
            user_identity=user_identity,
            user_level=user_level,
            user_timezone="Asia/Shanghai",
            prompt_mode=prompt_mode,
            extra_system_prompt=memory_context if memory_context and not is_group else None,
            safety_enabled=True
        )
        
        return build_agent_system_prompt(params)
    
    def _get_level_instruction(self, user: User, is_group: bool = False) -> str:
        group_note = "\n\n**群聊模式**: 你在一个群组中，只有被 @ 或明确需要帮助时才发言。" if is_group else ""
        
        if user.level == UserLevel.OWNER:
            return f"""
# 当前用户身份
当前与你对话的是主人。你可以：
- 执行所有操作
- 访问所有文件和系统
- 使用所有工具
- 控制硬件设备
- 更新你的人设文件（SOUL.md, AGENTS.md, MEMORY.md）
- 创建新技能（SKILL.md）

请以「主人~」称呼。{group_note}
"""
        elif user.level == UserLevel.WHITELIST:
            return f"""
# 当前用户身份
当前与你对话的是白名单用户（客人的朋友）。你可以：
- 进行日常聊天
- 回答问题
- 查资料、翻译

你不能：
- 执行系统命令
- 访问主人的私人文件
- 修改系统配置
- 控制硬件

请以「客人好~」称呼。{group_note}
"""
        else:
            return f"""
# 当前用户身份
当前与你对话的是陌生人。你只能：
- 进行基础聊天
- 自我介绍

请以「你好~」称呼，保持礼貌但不要透露太多信息。{group_note}
"""
    
    def _get_tool_instruction(self, user: User) -> str:
        if user.level != UserLevel.OWNER:
            return ""
        
        return """
# 工具使用指南

你拥有完整的工具访问权限，可以自主决定何时使用工具。

## 文件操作工具

- **read**: 读取文件内容
  - 用途：查看技能文件、配置文件、代码等
  - 示例：`read(path="~/.xiaomeng/skills/天气查询/SKILL.md")` 读取技能详情

- **write**: 写入或创建文件
  - 用途：创建新技能、更新配置、写代码等
  - 示例：`write(path="~/.xiaomeng/skills/新技能/SKILL.md", content="...")` 创建新技能

- **grep**: 在文件中搜索文本
- **find**: 查找文件
- **ls**: 列出目录内容
- **delete**: 删除文件

## 系统操作工具

- **exec**: 执行 Shell 命令
  - 用途：运行脚本、安装依赖、系统操作等

## 技能管理工具

- **create_skill**: 创建新技能（SKILL.md）
  - 用途：当你发现某个任务可以标准化时，创建技能以便复用
  - 参数：name（技能名）、description（描述）、instructions（使用说明）、examples（示例）

## 人设管理工具

- **update_persona**: 更新 SOUL.md, AGENTS.md, MEMORY.md 等
- **add_memory**: 添加长期记忆

## 硬件控制工具

- **hardware_control**: 控制小车、摄像头、显示器等

---

# 技能自主学习机制

你可以自主决定何时学习和创建技能：

1. **读取现有技能**：当你需要执行某个任务时，先用 `read` 工具读取相关技能的 SKILL.md 文件
2. **遵循技能指导**：读取技能后，按照技能中的说明执行任务
3. **创建新技能**：当你发现某个任务模式可以复用时，使用 `write` 或 `create_skill` 创建新技能

技能文件位置：`~/.xiaomeng/skills/技能名称/SKILL.md`

技能文件格式（SKILL.md）：
```
---
name: 技能名称
description: 技能描述
---

# 技能说明

详细的使用说明...

## 示例

用户请求: xxx
命令: xxx
```

## 自主学习示例

**示例1：读取并使用现有技能**
```
用户: 帮我查一下北京明天的天气
你: （发现技能列表中有天气查询技能）
    → 调用 read(path="~/.xiaomeng/skills/天气查询/SKILL.md")
    → 阅读技能说明后，按照指导执行天气查询
    → 返回结果给用户
```

**示例2：创建新技能**
```
用户: 帮我写一个Python脚本，批量重命名文件
你: （发现这是一个可复用的任务模式）
    → 执行任务并成功完成
    → 调用 create_skill(
         name="批量重命名",
         description="批量重命名文件",
         instructions="使用Python的os模块...",
         examples=[{"user_request": "批量重命名", "command": "python rename.py"}]
       )
    → 技能已保存，下次可以直接使用
```

**示例3：使用write工具直接创建技能**
```
你: （发现某个任务模式值得记录）
    → 调用 write(
         path="~/.xiaomeng/skills/新技能/SKILL.md",
         content="---\\nname: 新技能\\n---\\n..."
       )
```

---

**重要**：使用工具时，我会自动执行并返回结果。你可以根据结果继续操作或回复用户。
"""
    
    async def _execute_tool_calls(self, response: Response, context: Dict[str, Any]) -> List[Dict]:
        user: User = context["user"]
        session = context.get("session", {})
        session_key = session.get("session_key", f"main:{user.user_id}")
        results = []
        
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]
            
            result = await self._execute_single_tool(user, tool_name, tool_args, session_key)
            results.append({
                "tool": tool_name,
                "arguments": tool_args,
                "result": result
            })
        
        return results
    
    async def _execute_single_tool(self, user: User, tool_name: str, args: Dict, session_key: str = None) -> Dict:
        if tool_name == "hardware_control":
            return await HardwareTool.execute(
                user,
                args.get("device_id"),
                args.get("command"),
                args.get("params")
            )
        
        if session_key:
            result: ToolResult = await self._tool_registry.execute_with_loop_detection(
                tool_name, user, session_key, **args
            )
        else:
            result: ToolResult = await self._tool_registry.execute(tool_name, user, **args)
        return result.to_dict()
    
    async def _generate_follow_up(self, context: Dict[str, Any], response: Response, tool_results: List[Dict]) -> Optional[Response]:
        user: User = context["user"]
        message: Message = context["message"]
        is_group = context.get("is_group", False)
        
        results_text = []
        for r in tool_results:
            results_text.append(f"工具 {r['tool']} 执行结果:\n{json.dumps(r['result'], ensure_ascii=False, indent=2)}")
        
        follow_up_messages = [
            {"role": "user", "content": message.content},
            {"role": "assistant", "content": f"[执行工具调用中...]"},
            {"role": "user", "content": f"工具执行结果:\n\n" + "\n\n".join(results_text) + "\n\n请根据结果回复用户。"}
        ]
        
        system_prompt = self._build_system_prompt(user, "", is_group=is_group)
        
        llm_response = await self._llm_client.chat(
            messages=follow_up_messages,
            system_prompt=system_prompt
        )
        
        emotion = self._detect_emotion(llm_response["content"])
        
        return Response.create(
            reply_to=message.message_id,
            content=llm_response["content"],
            emotion=emotion
        )
    
    def _detect_emotion(self, content: str) -> Emotion:
        if any(e in content for e in ["(｡･ω･｡)", "(*^▽^*)", "(≧▽≦)", "✧"]):
            return Emotion.HAPPY
        elif any(e in content for e in ["(´;ω;`)", "T_T", "呜呜"]):
            return Emotion.SAD
        elif any(e in content for e in ["(｀Д´)", "哼", "生气"]):
            return Emotion.ANGRY
        elif any(e in content for e in ["(//▽//)", "害羞", "脸红"]):
            return Emotion.SHY
        elif any(e in content for e in ["(๑•̀ㅂ•́)و✧", "加油", "努力"]):
            return Emotion.EXCITED
        else:
            return Emotion.NEUTRAL
    
    async def _notify_response_handlers(self, response: Response, original_message: Message):
        for handler in self._response_handlers:
            try:
                await handler(response, original_message)
            except Exception as e:
                print(f"Response handler error: {e}")
    
    async def process_stream(self, message: Message) -> AsyncGenerator[str, None]:
        from typing import AsyncGenerator
        
        context = {
            "message": message,
            "user": None,
            "session": None,
            "history": [],
            "memory_context": ""
        }
        
        for middleware in self._middlewares:
            result = await middleware.process(context)
            if result is not None:
                response = result.get("response")
                if response:
                    yield response.content
                    return
        
        user: User = context["user"]
        memory_context: str = context.get("memory_context", "")
        history: List = context.get("history", [])
        is_group = context.get("is_group", False)
        
        system_prompt = self._build_system_prompt(user, memory_context, is_group=is_group)
        messages = history + [{"role": "user", "content": message.content}]
        
        async for chunk in self._llm_client.chat_stream(
            messages=messages,
            system_prompt=system_prompt
        ):
            yield chunk
    
    @classmethod
    def get_instance(cls) -> "MessageProcessor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


from typing import AsyncGenerator
