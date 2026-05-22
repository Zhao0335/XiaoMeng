"""
插件基类和接口定义

所有 XiaoMeng 插件必须继承 PluginBase 类并实现相应方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict
import logging

if TYPE_CHECKING:
    from ..qq.napcat import NapCatClient
    from ..tasks import AsyncTask

logger = logging.getLogger(__name__)


class PluginContext(TypedDict, total=False):
    """插件工具调用的上下文，传入 on_tool_call 的 context 参数。"""
    session_key: str        # "group:xxx" 或 "private:xxx"
    sender_qq: int          # 发送者 QQ 号
    level: int              # 权限级别 0=陌生人 1=管理员 2=主人
    identity: str           # canonical 身份名
    napcat: "NapCatClient"  # QQ API 客户端（WebSocket）
    data_dir: Path          # data/ 目录路径
    is_private: bool        # 是否私聊
    target_id: int          # 发送目标（group_id 或 user_id）
    task: "AsyncTask"       # 当前异步任务对象


class PluginState(Enum):
    """插件状态枚举"""
    UNLOADED = "unloaded"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    homepage: str = ""
    license: str = "MIT"
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    min_xiaomeng_version: str = "1.0.0"
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "license": self.license,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "min_xiaomeng_version": self.min_xiaomeng_version,
        }


@dataclass
class ToolDefinition:
    """工具定义（OpenAI Function Calling 格式）"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    # 最低用户权限：0=陌生人，1=管理员，2=主人（对应 PermLevel）
    min_user_level: int = 0
    # 调用时展示给用户的进度提示（None=不展示）
    progress_msg: Optional[str] = None

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


@dataclass
class CommandDefinition:
    """命令定义"""
    prefix: str
    description: str
    handler: Callable
    usage: str = ""
    aliases: List[str] = field(default_factory=list)


class PluginBase(ABC):
    """
    XiaoMeng 插件基类
    
    所有插件必须继承此类并实现以下方法：
    - get_metadata(): 返回插件元数据
    - on_initialize(): 插件初始化逻辑
    - on_shutdown(): 插件关闭逻辑
    
    可选实现：
    - get_tools(): 返回工具定义列表
    - get_commands(): 返回命令定义列表
    - on_message(): 处理消息的钩子
    """
    
    def __init__(
        self,
        plugin_dir: Path,
        config: Optional[Dict[str, Any]] = None,
    ):
        self._plugin_dir = plugin_dir
        self._config = config or {}
        self._state = PluginState.UNLOADED
        self._tools: List[ToolDefinition] = []
        self._commands: List[CommandDefinition] = []
        self._logger = logging.getLogger(f"plugin.{self.__class__.__name__}")
    
    @property
    def state(self) -> PluginState:
        return self._state
    
    @property
    def plugin_dir(self) -> Path:
        return self._plugin_dir
    
    @property
    def config(self) -> Dict[str, Any]:
        return self._config
    
    @property
    def is_enabled(self) -> bool:
        return self._config.get("enabled", True)
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """返回插件元数据"""
        pass
    
    @abstractmethod
    async def on_initialize(self) -> bool:
        """
        插件初始化逻辑
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    async def on_shutdown(self) -> None:
        """插件关闭逻辑"""
        pass
    
    def get_tools(self) -> List[ToolDefinition]:
        """
        返回工具定义列表
        
        Returns:
            List[ToolDefinition]: 工具定义列表
        """
        return self._tools
    
    def get_commands(self) -> List[CommandDefinition]:
        """
        返回命令定义列表
        
        Returns:
            List[CommandDefinition]: 命令定义列表
        """
        return self._commands
    
    async def on_message(
        self,
        message: str,
        sender_id: int,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """
        消息处理钩子
        
        Args:
            message: 消息内容
            sender_id: 发送者ID（QQ号）
            context: 上下文信息
            
        Returns:
            Optional[str]: 处理结果，None 表示不处理
        """
        return None
    
    async def on_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: "PluginContext",
    ) -> str:
        """工具调用处理，context 字段见 PluginContext。"""
        return f"工具 {tool_name} 未实现"
    
    async def on_command(
        self,
        command: str,
        args: str,
        sender_id: int,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """
        命令处理
        
        Args:
            command: 命令名称
            args: 命令参数
            sender_id: 发送者ID
            context: 上下文信息
            
        Returns:
            Optional[str]: 命令执行结果
        """
        return None
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具"""
        self._tools.append(tool)
        self._logger.debug(f"注册工具: {tool.name}")
    
    def register_command(self, command: CommandDefinition) -> None:
        """注册命令"""
        self._commands.append(command)
        self._logger.debug(f"注册命令: {command.prefix}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取插件状态"""
        metadata = self.get_metadata()
        return {
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "state": self._state.value,
            "enabled": self.is_enabled,
            "tools_count": len(self._tools),
            "commands_count": len(self._commands),
        }
    
    def _set_state(self, state: PluginState) -> None:
        self._state = state
        self._logger.info(f"插件状态变更: {state.value}")


class SimplePlugin(PluginBase):
    """
    简单插件基类
    
    用于快速创建不需要复杂逻辑的插件
    """
    
    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        plugin_dir: Path = Path("."),
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(plugin_dir, config)
        self._name = name
        self._version = version
        self._description = description
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name,
            version=self._version,
            description=self._description,
        )
    
    async def on_initialize(self) -> bool:
        return True
    
    async def on_shutdown(self) -> None:
        pass
