"""
工具 Schema 生成器

组合硬编码工具（TOOL_SCHEMAS）和动态技能（SkillRegistry）的 schema，
支持按模型层级和用户权限过滤。

基于 Harness 的 tool schema + registry dispatch 模式。
"""

from typing import Dict, List, Optional

from .definition import ModelTier, UserLevel
from .registry import SkillRegistry


class ToolSchemaBuilder:
    """构建上下文感知的工具 schema 列表

    工具来源：
    1. 硬编码工具（web_search, add_memory, etc.）— TOOL_SCHEMAS
    2. 动态技能（SkillRegistry 中注册了 handler 的技能）

    过滤逻辑：
    - 本地模型 (LOCAL): 仅提供记忆搜索+对话回调（轻量工具集）
    - 云端模型 (CLOUD): 提供敏感级以下全部工具
    - Pro 模型 (PRO): 全部工具
    """

    @staticmethod
    def from_tools(
        base_tools: List[Dict],
        model_tier: ModelTier,
        user_level: UserLevel,
        identity: str = "",
    ) -> List[Dict]:
        """从基础工具列表 + SkillRegistry 构建最终工具 schema"""
        registry = SkillRegistry.get_instance()

        skill_tools = registry.get_tool_schemas(model_tier, user_level, identity)

        return base_tools + skill_tools
