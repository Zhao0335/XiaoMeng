"""
插件管理器

管理所有已加载的插件，提供统一的工具和命令分发
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base import PluginBase, PluginMetadata, PluginState, ToolDefinition, CommandDefinition
from .loader import PluginLoader

logger = logging.getLogger(__name__)


class PluginManager:
    """
    插件管理器
    
    功能：
    - 管理所有已加载的插件
    - 提供统一的工具 Schema 合并
    - 提供统一的工具调用分发
    - 提供统一的命令分发
    - 插件生命周期管理
    """
    
    def __init__(
        self,
        plugins_dir: Path,
        auto_load: bool = True,
        auto_initialize: bool = False,
    ):
        self._loader = PluginLoader(plugins_dir, auto_discover=False)
        self._initialized: Dict[str, PluginBase] = {}
        self._running: Dict[str, PluginBase] = {}
        self._tool_handlers: Dict[str, PluginBase] = {}
        self._command_handlers: Dict[str, PluginBase] = {}
        self._init_task: Optional[asyncio.Task] = None
        
        if auto_load:
            self._loader.discover()
            self._loader.load_all()
            
            if auto_initialize:
                self._init_task = asyncio.create_task(self.initialize_all())
    
    @property
    def loader(self) -> PluginLoader:
        return self._loader
    
    @property
    def plugins(self) -> Dict[str, PluginBase]:
        return self._loader.loaded
    
    @property
    def initialized(self) -> Dict[str, PluginBase]:
        return self._initialized
    
    @property
    def running(self) -> Dict[str, PluginBase]:
        return self._running
    
    def discover(self) -> Dict[str, Path]:
        """发现插件"""
        return self._loader.discover()
    
    def load_all(self) -> Dict[str, PluginBase]:
        """加载所有插件"""
        if not self._loader.discovered:
            self._loader.discover()
        return self._loader.load_all()
    
    async def initialize_all(self) -> Dict[str, bool]:
        """
        初始化所有已加载的插件
        
        Returns:
            Dict[str, bool]: 插件名称 -> 是否成功
        """
        if not self._loader.loaded:
            self.load_all()
        
        results = {}
        
        for name, plugin in self._loader.loaded.items():
            if not plugin.is_enabled:
                logger.info(f"跳过已禁用的插件: {name}")
                results[name] = False
                continue
            
            if name in self._initialized:
                results[name] = True
                continue
            
            try:
                success = await plugin.on_initialize()
                if success:
                    plugin._set_state(PluginState.INITIALIZED)
                    self._initialized[name] = plugin
                    self._register_plugin_handlers(plugin)
                    results[name] = True
                    logger.info(f"初始化插件成功: {name}")
                else:
                    plugin._set_state(PluginState.ERROR)
                    results[name] = False
                    logger.error(f"初始化插件失败: {name}")
            except Exception as e:
                plugin._set_state(PluginState.ERROR)
                results[name] = False
                logger.error(f"初始化插件异常 [{name}]: {e}")
        
        return results
    
    async def start_all(self) -> Dict[str, bool]:
        """
        启动所有已初始化的插件
        
        Returns:
            Dict[str, bool]: 插件名称 -> 是否成功
        """
        results = {}
        
        for name, plugin in self._initialized.items():
            if name in self._running:
                results[name] = True
                continue
            
            try:
                plugin._set_state(PluginState.RUNNING)
                self._running[name] = plugin
                results[name] = True
                logger.info(f"启动插件: {name}")
            except Exception as e:
                results[name] = False
                logger.error(f"启动插件失败 [{name}]: {e}")
        
        return results
    
    async def stop_all(self) -> Dict[str, bool]:
        """
        停止所有运行中的插件
        
        Returns:
            Dict[str, bool]: 插件名称 -> 是否成功
        """
        results = {}
        
        for name, plugin in list(self._running.items()):
            try:
                await plugin.on_shutdown()
                plugin._set_state(PluginState.INITIALIZED)
                del self._running[name]
                results[name] = True
                logger.info(f"停止插件: {name}")
            except Exception as e:
                results[name] = False
                logger.error(f"停止插件失败 [{name}]: {e}")
        
        return results
    
    async def shutdown_all(self) -> Dict[str, bool]:
        """
        关闭所有插件
        
        Returns:
            Dict[str, bool]: 插件名称 -> 是否成功
        """
        results = await self.stop_all()
        
        for name, plugin in list(self._initialized.items()):
            try:
                await plugin.on_shutdown()
                plugin._set_state(PluginState.LOADED)
                del self._initialized[name]
                self._unregister_plugin_handlers(plugin)
                results[name] = True
            except Exception as e:
                results[name] = False
                logger.error(f"关闭插件失败 [{name}]: {e}")
        
        return results
    
    def _register_plugin_handlers(self, plugin: PluginBase) -> None:
        """注册插件的工具和命令处理器"""
        for tool in plugin.get_tools():
            self._tool_handlers[tool.name] = plugin
            logger.debug(f"注册工具处理器: {tool.name} -> {plugin.get_metadata().name}")
        
        for command in plugin.get_commands():
            self._command_handlers[command.prefix] = plugin
            for alias in command.aliases:
                self._command_handlers[alias] = plugin
            logger.debug(f"注册命令处理器: {command.prefix} -> {plugin.get_metadata().name}")
    
    def _unregister_plugin_handlers(self, plugin: PluginBase) -> None:
        """注销插件的工具和命令处理器"""
        for tool in plugin.get_tools():
            self._tool_handlers.pop(tool.name, None)
        
        for command in plugin.get_commands():
            self._command_handlers.pop(command.prefix, None)
            for alias in command.aliases:
                self._command_handlers.pop(alias, None)
    
    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        获取所有插件的工具 Schema（OpenAI 格式）
        
        Returns:
            List[Dict[str, Any]]: 工具 Schema 列表
        """
        schemas = []
        for plugin in self._initialized.values():
            for tool in plugin.get_tools():
                schemas.append(tool.to_openai_schema())
        return schemas
    
    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        """
        获取所有工具定义
        
        Returns:
            Dict[str, ToolDefinition]: 工具名称 -> 工具定义
        """
        tools = {}
        for plugin in self._initialized.values():
            for tool in plugin.get_tools():
                tools[tool.name] = tool
        return tools
    
    def get_all_commands(self) -> Dict[str, CommandDefinition]:
        """
        获取所有命令定义
        
        Returns:
            Dict[str, CommandDefinition]: 命令前缀 -> 命令定义
        """
        commands = {}
        for plugin in self._initialized.values():
            for command in plugin.get_commands():
                commands[command.prefix] = command
                for alias in command.aliases:
                    commands[alias] = command
        return commands
    
    async def dispatch_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        分发工具调用
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            context: 上下文信息
            
        Returns:
            str: 工具执行结果
        """
        context = context or {}
        
        if tool_name not in self._tool_handlers:
            return f"未知工具: {tool_name}"
        
        plugin = self._tool_handlers[tool_name]
        
        try:
            result = await plugin.on_tool_call(tool_name, arguments, context)
            return result
        except Exception as e:
            logger.error(f"工具调用失败 [{tool_name}]: {e}")
            return f"工具调用失败: {e}"
    
    async def dispatch_command(
        self,
        text: str,
        sender_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        分发命令处理
        
        Args:
            text: 消息文本
            sender_id: 发送者ID
            context: 上下文信息
            
        Returns:
            Optional[str]: 命令处理结果，None 表示无匹配命令
        """
        context = context or {}
        text = text.strip()
        
        matched_prefix = None
        matched_len = 0
        
        for prefix in self._command_handlers.keys():
            if text == prefix or text.startswith(prefix + " "):
                if len(prefix) > matched_len:
                    matched_prefix = prefix
                    matched_len = len(prefix)
        
        if matched_prefix is None:
            return None
        
        plugin = self._command_handlers[matched_prefix]
        args = text[len(matched_prefix):].strip()
        
        try:
            result = await plugin.on_command(
                command=matched_prefix,
                args=args,
                sender_id=sender_id,
                context=context,
            )
            return result
        except Exception as e:
            logger.error(f"命令处理失败 [{matched_prefix}]: {e}")
            return f"命令处理失败: {e}"
    
    async def dispatch_message(
        self,
        message: str,
        sender_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        分发消息处理（先尝试命令，再尝试消息钩子）
        
        Args:
            message: 消息内容
            sender_id: 发送者ID
            context: 上下文信息
            
        Returns:
            Optional[str]: 处理结果
        """
        context = context or {}
        
        cmd_result = await self.dispatch_command(message, sender_id, context)
        if cmd_result is not None:
            return cmd_result
        
        for plugin in self._running.values():
            try:
                result = await plugin.on_message(message, sender_id, context)
                if result is not None:
                    return result
            except Exception as e:
                logger.error(f"消息处理失败 [{plugin.get_metadata().name}]: {e}")
        
        return None
    
    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """获取插件实例"""
        return self._loader.loaded.get(name)
    
    def get_plugin_status(self, name: str) -> Optional[Dict[str, Any]]:
        """获取插件状态"""
        plugin = self.get_plugin(name)
        if plugin:
            return plugin.get_status()
        return None
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """列出所有插件状态"""
        return self._loader.list_plugins()
    
    def enable_plugin(self, name: str) -> bool:
        """启用插件"""
        plugin = self.get_plugin(name)
        if plugin:
            plugin._config["enabled"] = True
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """禁用插件"""
        plugin = self.get_plugin(name)
        if plugin:
            plugin._config["enabled"] = False
            return True
        return False
    
    async def reload_plugin(self, name: str) -> Optional[PluginBase]:
        """重新加载插件"""
        if name in self._running:
            await self.stop_plugin(name)
        
        if name in self._initialized:
            plugin = self._initialized[name]
            await plugin.on_shutdown()
            self._unregister_plugin_handlers(plugin)
            del self._initialized[name]
        
        plugin = self._loader.reload(name)
        if plugin:
            success = await plugin.on_initialize()
            if success:
                plugin._set_state(PluginState.INITIALIZED)
                self._initialized[name] = plugin
                self._register_plugin_handlers(plugin)
        
        return plugin
    
    async def stop_plugin(self, name: str) -> bool:
        """停止单个插件"""
        if name not in self._running:
            return False
        
        plugin = self._running[name]
        try:
            await plugin.on_shutdown()
            plugin._set_state(PluginState.INITIALIZED)
            del self._running[name]
            return True
        except Exception as e:
            logger.error(f"停止插件失败 [{name}]: {e}")
            return False
    
    async def start_plugin(self, name: str) -> bool:
        """启动单个插件"""
        if name not in self._initialized:
            return False
        
        if name in self._running:
            return True
        
        plugin = self._initialized[name]
        plugin._set_state(PluginState.RUNNING)
        self._running[name] = plugin
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取插件系统统计信息"""
        return {
            "discovered": len(self._loader.discovered),
            "loaded": len(self._loader.loaded),
            "initialized": len(self._initialized),
            "running": len(self._running),
            "tools": len(self._tool_handlers),
            "commands": len(self._command_handlers),
        }
