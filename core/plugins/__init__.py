"""
XiaoMeng Plugin System
插件系统核心模块
"""

from .base import PluginBase, PluginMetadata, PluginState
from .loader import PluginLoader
from .manager import PluginManager

__all__ = [
    "PluginBase",
    "PluginMetadata",
    "PluginState",
    "PluginLoader",
    "PluginManager",
]
