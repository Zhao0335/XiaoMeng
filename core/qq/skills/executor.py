"""
Skill 执行器

上下文感知的技能执行引擎：
- 接收 SkillContext（包含 model_tier, user_level, identity）
- 根据权限过滤可用技能
- 执行技能 handler（如果存在）
- 返回执行结果
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .definition import ModelTier, SkillDefinition, SkillRisk, UserLevel
from .permissions import SkillPermissionChecker

logger = logging.getLogger(__name__)


@dataclass
class SkillContext:
    """技能执行上下文

    类比 Harness 的 Context + World：
    - Context: 请求级上下文（用户、模型、会话）
    - World:  全局状态（文件系统、数据库、工具）
    """
    model_tier: ModelTier = ModelTier.LOCAL
    user_level: UserLevel = UserLevel.STRANGER
    identity: str = ""

    session_key: str = ""
    sender_qq: int = 0

    tool_executor: Any = None

    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_gateway(
        cls,
        route: str,
        perm_level,   # PermLevel
        identity: str = "",
        session_key: str = "",
        sender_qq: int = 0,
        tool_executor=None,
    ) -> "SkillContext":
        from ..permissions import PermLevel

        tier = ModelTier.from_route(route)

        if isinstance(perm_level, int):
            perm_level = PermLevel(perm_level)

        if perm_level == PermLevel.OWNER:
            user_lv = UserLevel.OWNER
        elif perm_level == PermLevel.ADMIN:
            user_lv = UserLevel.ADMIN
        elif perm_level == PermLevel.BLACKLIST:
            user_lv = UserLevel.STRANGER
        else:
            user_lv = UserLevel.STRANGER

        return cls(
            model_tier=tier,
            user_level=user_lv,
            identity=identity,
            session_key=session_key,
            sender_qq=sender_qq,
            tool_executor=tool_executor,
        )


class SkillExecutor:
    """技能执行器"""

    def __init__(self, perm_checker: Optional[SkillPermissionChecker] = None):
        self._perm = perm_checker or SkillPermissionChecker()

    def get_available_skills(
        self,
        skills: list[SkillDefinition],
        ctx: SkillContext,
    ) -> list[SkillDefinition]:
        """返回当前上下文可用的技能列表"""
        return self._perm.filter_skills(
            skills, ctx.model_tier, ctx.user_level, ctx.identity,
        )

    async def execute(
        self,
        skill: SkillDefinition,
        ctx: SkillContext,
        *args,
        **kwargs,
    ) -> Optional[str]:
        """执行技能 handler（如果有的话）"""
        if not self._perm.can_use(skill, ctx.model_tier, ctx.user_level, ctx.identity):
            logger.warning(f"技能 {skill.name} 权限不足，跳过执行")
            return f"权限不足：{skill.name} 需要 {skill.permission.min_user_level.label()}+"

        if skill.handler is None:
            logger.debug(f"技能 {skill.name} 没有 handler")
            return None

        try:
            import asyncio
            if asyncio.iscoroutinefunction(skill.handler):
                result = await skill.handler(ctx, *args, **kwargs)
            else:
                result = skill.handler(ctx, *args, **kwargs)
            return str(result) if result is not None else ""
        except Exception as e:
            logger.error(f"执行技能 {skill.name} 失败: {e}")
            return f"技能 {skill.name} 执行失败: {e}"

    def build_active_prompt(
        self,
        skills: list[SkillDefinition],
        ctx: SkillContext,
    ) -> str:
        """构建可注入 system prompt 的技能段落

        类比 Harness 的 feedforward context：
        只在 system prompt 中注入当前上下文下有权限的技能。
        """
        available = [
            s for s in skills
            if s.enabled and s.always_active and self._perm.can_use(s, ctx.model_tier, ctx.user_level, ctx.identity)
        ]

        if not available:
            return ""

        index_lines = []
        body_sections = []

        for s in available:
            label = f"**{s.name}**"
            if s.description:
                label += f": {s.description}"
            if s.emoji:
                label = f"{s.emoji} {label}"
            index_lines.append(f"- {label}")
            if s.body:
                body_sections.append(f"### {s.name}\n\n{s.body}")

        parts = ["## 可用技能\n"]
        if index_lines:
            parts.append("\n".join(index_lines))
        if body_sections:
            parts.append("\n---\n")
            parts.append("\n\n---\n\n".join(body_sections))

        return "\n".join(parts)
