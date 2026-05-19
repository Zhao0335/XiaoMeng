"""
Calendar Maker Plugin for XiaoMeng
日历管理插件 - 支持通过QQ管理calendar_backend系统的日程

功能：
- 向calendar_backend添加日程安排
- 通过QQ验证账号名和密码信息
- 支持账号切换（需密码验证）
- 支持QQ号与calendar账号绑定
"""

from .plugin import CalendarMakerPlugin
from .tools import CALENDAR_TOOL_SCHEMAS, CalendarToolExecutor
from .commands import CalendarCommandParser
from .binding_manager import BindingManager, BindingInfo

__all__ = [
    "CalendarMakerPlugin",
    "CALENDAR_TOOL_SCHEMAS",
    "CalendarToolExecutor",
    "CalendarCommandParser",
    "BindingManager",
    "BindingInfo",
]

__version__ = "1.0.0"
__author__ = "XiaoMeng Plugin Developer"
