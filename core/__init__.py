"""
XiaoMengCore 核心模块

QQ Bot 入口: run_qq.py
管理面板: run_panel.py
"""

from .model_layer import ModelLayerRouter, ModelEndpoint, ModelLayer, ModelRole
from .qq.permissions import QQPermissionManager, PermLevel
from .qq.commands import QQCommandParser
from .qq.proactive import ProactiveManager
from .qq.tools import QQToolExecutor, TOOL_SCHEMAS

__all__ = [
    "ModelLayerRouter", "ModelEndpoint", "ModelLayer", "ModelRole",
    "QQPermissionManager", "PermLevel",
    "QQCommandParser",
    "ProactiveManager",
    "QQToolExecutor", "TOOL_SCHEMAS",
]
