"""
工具 Schema 聚合器

将内置工具（TOOL_SCHEMAS）与插件工具（PluginManager）合并，
按模型层级和用户权限过滤后返回给 LLM。

来源优先级：
  1. 内置工具（builtins，在 tools.py 中定义）
  2. 插件工具（由 PluginManager 管理的 data/plugins/ 中的插件注册）
"""

from typing import Dict, List, Optional

from .definition import ModelTier, UserLevel


class ToolSchemaBuilder:
    """聚合所有来源的工具 schema。"""

    @staticmethod
    def from_tools(
        base_tools: List[Dict],
        model_tier: ModelTier,
        user_level: UserLevel,
        identity: str = "",
        plugin_manager=None,
    ) -> List[Dict]:
        """
        构建最终工具列表。

        base_tools    — 内置工具 schema（已按模型层级预过滤）
        plugin_manager — PluginManager 实例，None 则跳过插件工具
        """
        tools = list(base_tools)

        if plugin_manager is not None and model_tier >= ModelTier.CLOUD:
            plugin_schemas = plugin_manager.get_all_tool_schemas(int(user_level))
            tools.extend(plugin_schemas)

        return tools
