"""
XiaoMeng Skill 系统

Skills = 给 LLM 注入的上下文文档（SKILL.md），描述 LLM 可以做什么、怎么做。
Tools  = LLM 可调用的原子函数（定义在 tools.py 或插件中）。
Plugins = Python 扩展包（data/plugins/），可注册新工具和后台服务。
"""

from .definition import (
    ModelTier,
    SkillDefinition,
    SkillPermission,
    SkillRisk,
    UserLevel,
)
from .executor import SkillContext, SkillExecutor
from .loader import SkillLoader
from .permissions import SkillPermissionChecker
from .registry import SkillRegistry
from .schema import ToolSchemaBuilder

__all__ = [
    "SkillRegistry",
    "SkillDefinition",
    "SkillPermission",
    "SkillRisk",
    "ModelTier",
    "UserLevel",
    "SkillContext",
    "SkillExecutor",
    "SkillLoader",
    "SkillPermissionChecker",
    "ToolSchemaBuilder",
]
