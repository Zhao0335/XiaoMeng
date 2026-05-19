"""
XiaoMeng Skill 系统

基于 Harness 框架设计理念重构的模块化技能系统。

核心组件：
- SkillRegistry:   统一技能注册中心（单例）
- SkillDefinition:  技能元数据定义
- SkillPermission:  权限控制（ModelTier + UserLevel + Identity）
- SkillLoader:     文件系统技能加载（SKILL.md 格式）
- SkillExecutor:   上下文感知的技能执行引擎
- SkillContext:     执行上下文（模型层级、用户级别、身份）
- @skill 装饰器:    编程式技能注册（类比 Harness #[skill] proc-macro）

架构设计原则：
1. Registry-based dispatch — 统一注册→发现→过滤→执行管道
2. Risk classification — READ_ONLY / SENSITIVE / DANGEROUS 三层风险
3. Model-aware routing — 本地14b / Cloud DeepSeek / Pro 三级模型过滤
4. User-identity control — 基于身份（非QQ号）的权限，OWNER/ADMIN/STRANGER
5. Backward compatible — 现有 SKILL.md 文件无需修改即可使用

迁移指南：
  旧方式:
    skills_prompt = load_skills_prompt(skills_dir)  # 纯文本注入 system prompt
  新方式:
    registry = SkillRegistry.get_instance()
    registry.init_loader(skills_dir)
    skills = registry.get_active_prompt_skills(tier, level, identity)
    prompt = SkillExecutor().build_active_prompt(skills, ctx)
"""

from .definition import (
    ModelTier,
    SkillDefinition,
    SkillPermission,
    SkillRisk,
    UserLevel,
)
from .executor import SkillContext, SkillExecutor
from .loader import SkillLoader, skill
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
    "skill",
]
