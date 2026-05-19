"""
Calendar Maker Plugin 主类
适配 XiaoMeng 插件系统接口
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.plugins.base import PluginBase, PluginMetadata, ToolDefinition, CommandDefinition

from account_manager import AccountManager
from calendar_client import CalendarClient
from commands import CalendarCommandParser
from config import CalendarMakerConfig
from tools import CALENDAR_TOOL_SCHEMAS, CalendarToolExecutor

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """
    Calendar Maker 插件
    
    功能：
    - 向 calendar_backend 添加日程安排
    - 通过 QQ 验证账号名和密码信息
    - 支持账号切换（需密码验证）
    - 支持QQ号与calendar账号绑定
    """
    
    def __init__(
        self,
        plugin_dir: Path,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(plugin_dir, config)
        
        config_path = plugin_dir / "config.json"
        data_dir = plugin_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        self._config_path = config_path
        self._data_dir = data_dir
        
        self._plugin_config = CalendarMakerConfig.from_file(config_path)
        self._account_manager: Optional[AccountManager] = None
        self._tool_executor: Optional[CalendarToolExecutor] = None
        self._command_parser: Optional[CalendarCommandParser] = None
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="calendar_maker",
            version="1.0.0",
            description="日历管理插件 - 支持通过QQ管理calendar_backend系统的日程安排",
            author="XiaoMeng Plugin Developer",
            tags=["calendar", "schedule", "todo", "productivity"],
        )
    
    async def on_initialize(self) -> bool:
        if not self._plugin_config.enabled:
            logger.info("插件 calendar_maker 已禁用")
            return False
        
        try:
            self._account_manager = AccountManager(
                config=self._plugin_config,
                data_dir=self._data_dir,
            )
            
            self._tool_executor = CalendarToolExecutor(self._account_manager)
            self._command_parser = CalendarCommandParser(self._account_manager)
            
            self._register_tools()
            self._register_commands()
            
            healthy = await self._account_manager.health_check()
            if healthy:
                logger.info("插件 calendar_maker 初始化成功，后端服务可用")
            else:
                logger.warning("插件 calendar_maker 初始化成功，但后端服务不可用")
            
            return True
            
        except Exception as e:
            logger.error(f"插件 calendar_maker 初始化失败: {e}")
            return False
    
    async def on_shutdown(self) -> None:
        if self._account_manager:
            self._account_manager.logout()
        logger.info("插件 calendar_maker 已关闭")
    
    def _register_tools(self) -> None:
        for schema in CALENDAR_TOOL_SCHEMAS:
            func = schema.get("function", {})
            tool = ToolDefinition(
                name=func.get("name", ""),
                description=func.get("description", ""),
                parameters=func.get("parameters", {}),
            )
            self.register_tool(tool)
    
    def _register_commands(self) -> None:
        commands = [
            ("/日历 绑定", "绑定QQ号到calendar账号"),
            ("/日历 解绑", "解除当前QQ号的绑定"),
            ("/日历 绑定状态", "查看绑定状态"),
            ("/日历 切换账号", "切换到其他账号"),
            ("/日历 登录", "登录日历账号"),
            ("/日历 登出", "登出当前账号"),
            ("/日历 账号列表", "查看已保存账号"),
            ("/日历 注册", "注册新账号"),
            ("/日历 添加日程", "添加日程"),
            ("/日历 添加待办", "添加待办"),
            ("/日历 查看日程", "查看所有日程"),
            ("/日历 查看待办", "查看所有待办"),
            ("/日历 帮助", "显示帮助"),
        ]
        
        for prefix, desc in commands:
            self.register_command(CommandDefinition(
                prefix=prefix,
                description=desc,
                handler=self._handle_command,
            ))
    
    async def _handle_command(
        self,
        command: str,
        args: str,
        sender_id: int,
        context: Dict[str, Any],
    ) -> str:
        if not self._command_parser:
            return "插件未初始化"
        
        session_key = context.get("session_key", "")
        result = await self._command_parser.handle(
            text=f"{command} {args}".strip(),
            sender_qq=sender_id,
            session_key=session_key,
        )
        
        if result:
            return result.reply
        return "命令处理失败"
    
    async def on_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        if not self._tool_executor:
            return "插件未初始化"
        
        qq = context.get("qq", context.get("sender_id", 0))
        self._tool_executor.set_context(qq)
        
        return await self._tool_executor.execute(tool_name, arguments)
    
    async def on_command(
        self,
        command: str,
        args: str,
        sender_id: int,
        context: Dict[str, Any],
    ) -> Optional[str]:
        if not self._command_parser:
            return None
        
        text = f"{command} {args}".strip() if args else command
        session_key = context.get("session_key", "")
        
        result = await self._command_parser.handle(
            text=text,
            sender_qq=sender_id,
            session_key=session_key,
        )
        
        if result:
            return result.reply
        return None
    
    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status["backend_url"] = self._plugin_config.backend.backend_url
        status["current_account"] = (
            self._account_manager.current_account
            if self._account_manager else None
        )
        status["is_logged_in"] = (
            self._account_manager.is_logged_in
            if self._account_manager else False
        )
        return status


def create_plugin(
    plugin_dir: Path,
    config: Optional[Dict[str, Any]] = None,
) -> Plugin:
    return Plugin(plugin_dir=plugin_dir, config=config)
