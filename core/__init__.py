"""
XiaoMengCore 核心模块

核心改进（相比OpenClaw）：
1. 增强版模型管理 - 并行加载、健康检查、自动重试
2. 深度情感记忆 - 知识图谱+RAG、多模态情感分析
3. 跨平台路由 - 身份统一、用户分组、会话隔离
"""

from .user_manager import UserManager
from .session_manager import SessionManager
from .llm_client import LLMClient
from .processor import MessageProcessor, Middleware
from .memory import MemoryManager
from .tools import ToolRegistry, ToolResult
from .skills import SkillManager, Skill
from .hardware import HardwareManager, HardwareTool
from .heartbeat import HeartbeatManager, HeartbeatTask
from .model_router import ModelRouter, ModelConfig, ModelType, TaskComplexity, TaskPriority
from .scheduler import PriorityScheduler, ThreeLayerCoordinator, Priority
from .plugins import PluginManager, Plugin, PluginMetadata
from .model_layer import ModelLayerRouter, ModelEndpoint, ModelLayer, ModelRole
from .self_improving import SelfImprovingAgent, LearningCategory, LearningPriority
from .care import ProactiveCareSystem, CareType, CareContext, SpecialDay, UserPreference
from .personalization import PersonalizationEngine, UserProfile, PreferenceCategory
from .schedule import ScheduleManager, ScheduleItem, ScheduleType, SchedulePriority, ScheduleStatus
from .todo import TodoManager, TodoItem, TodoPriority, TodoStatus, TodoCategory
from .realtime_info import RealtimeInfoService, WeatherInfo, NewsItem, ExchangeRate

from .system_prompt import (
    build_agent_system_prompt, 
    SystemPromptParams, 
    PromptMode,
    CORE_TOOL_SUMMARIES
)
from .skill_loader import (
    SkillLoader,
    SkillsLimits,
    SkillEligibilityContext
)
from .skills_types import (
    SkillRequires,
    SkillInstallSpec,
    SkillMetadata,
    SkillInvocationPolicy,
    SkillEntry,
    SkillSnapshot
)
from .model_manager import (
    EnhancedModelManager,
    ModelHealth,
    LoadBalancingConfig
)
from .router import (
    EnhancedRouter,
    Platform,
    UserLevel,
    MessagePriority,
    PlatformIdentity,
    UnifiedIdentity,
    UserGroup,
    RoutedMessage
)

__all__ = [
    "UserManager",
    "SessionManager",
    "LLMClient",
    "MessageProcessor",
    "Middleware",
    "MemoryManager",
    "ToolRegistry",
    "ToolResult",
    "SkillManager",
    "Skill",
    "HardwareManager",
    "HardwareTool",
    "HeartbeatManager",
    "HeartbeatTask",
    "ModelRouter",
    "ModelConfig",
    "ModelType",
    "TaskComplexity",
    "TaskPriority",
    "PriorityScheduler",
    "ThreeLayerCoordinator",
    "Priority",
    "PluginManager",
    "Plugin",
    "PluginMetadata",
    "ModelLayerRouter",
    "ModelEndpoint",
    "ModelLayer",
    "ModelRole",
    "SelfImprovingAgent",
    "LearningCategory",
    "LearningPriority",
    "ProactiveCareSystem",
    "CareType",
    "CareContext",
    "SpecialDay",
    "UserPreference",
    "PersonalizationEngine",
    "UserProfile",
    "PreferenceCategory",
    "ScheduleManager",
    "ScheduleItem",
    "ScheduleType",
    "SchedulePriority",
    "ScheduleStatus",
    "TodoManager",
    "TodoItem",
    "TodoPriority",
    "TodoStatus",
    "TodoCategory",
    "RealtimeInfoService",
    "WeatherInfo",
    "NewsItem",
    "ExchangeRate",
    "build_agent_system_prompt",
    "SystemPromptParams",
    "PromptMode",
    "CORE_TOOL_SUMMARIES",
    "SkillLoader",
    "SkillsLimits",
    "SkillEligibilityContext",
    "SkillRequires",
    "SkillInstallSpec",
    "SkillMetadata",
    "SkillInvocationPolicy",
    "SkillEntry",
    "SkillSnapshot",
    "EnhancedModelManager",
    "ModelHealth",
    "LoadBalancingConfig",
    "EnhancedRouter",
    "Platform",
    "UserLevel",
    "MessagePriority",
    "PlatformIdentity",
    "UnifiedIdentity",
    "UserGroup",
    "RoutedMessage",
]
