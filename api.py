"""
XiaoMengCore API - 简洁易用的接口层

提供高度可扩展和可自定义的 API：
- XiaoMengBot: 主机器人类，一键启动
- Plugin: 插件基类，轻松扩展功能
- Tool: 工具基类，自定义工具
- Skill: 技能基类，自定义技能
- Middleware: 中间件基类，自定义处理流程
"""

from typing import Optional, Callable, Dict, Any, List, Awaitable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import asyncio

from .core import (
    UserManager, SessionManager, LLMClient, MessageProcessor,
    MemoryManager, ToolRegistry, ToolResult, SkillManager,
    PriorityScheduler, Priority
)
from .models import User, Message, Response, Source, UserLevel
from .config import ConfigManager, XiaoMengConfig


@dataclass
class BotConfig:
    """机器人配置 - 简化版"""
    name: str = "小萌"
    data_dir: str = "./data"
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:3b"
    llm_base_url: str = "http://localhost:11434/v1"
    owner_id: str = "owner"
    
    @classmethod
    def from_file(cls, path: str) -> "BotConfig":
        """从配置文件加载"""
        import json
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(
            name=data.get("name", "小萌"),
            data_dir=data.get("data_dir", "./data"),
            llm_provider=data.get("llm", {}).get("provider", "ollama"),
            llm_model=data.get("llm", {}).get("model", "qwen2.5:3b"),
            llm_base_url=data.get("llm", {}).get("base_url", "http://localhost:11434/v1"),
            owner_id=data.get("owner", {}).get("user_id", "owner"),
        )


class Plugin(ABC):
    """
    插件基类 - 轻松扩展功能
    
    示例:
    ```python
    class MyPlugin(Plugin):
        name = "my_plugin"
        
        async def on_load(self, bot):
            print("插件加载")
        
        async def on_message(self, message, response):
            # 处理消息
            return response
    ```
    """
    
    name: str = "base_plugin"
    priority: int = 100
    
    async def on_load(self, bot: "XiaoMengBot") -> None:
        """插件加载时调用"""
        pass
    
    async def on_unload(self, bot: "XiaoMengBot") -> None:
        """插件卸载时调用"""
        pass
    
    async def on_message(self, message: Message, response: str) -> str:
        """处理消息，返回修改后的响应"""
        return response
    
    async def on_tool_call(self, tool_name: str, params: Dict) -> Optional[Dict]:
        """工具调用前拦截"""
        return None


class Tool(ABC):
    """
    工具基类 - 自定义工具
    
    示例:
    ```python
    class WeatherTool(Tool):
        name = "weather"
        description = "获取天气信息"
        
        async def execute(self, city: str) -> ToolResult:
            # 获取天气
            return ToolResult(True, f"{city}的天气是晴天")
    ```
    """
    
    name: str = "base_tool"
    description: str = "基础工具"
    requires_owner: bool = False
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass
    
    def get_schema(self) -> Dict:
        """获取工具 schema"""
        return {
            "name": self.name,
            "description": self.description,
            "requires_owner": self.requires_owner
        }


class Middleware(ABC):
    """
    中间件基类 - 自定义处理流程
    
    示例:
    ```python
    class LoggingMiddleware(Middleware):
        async def process(self, message, next_handler):
            print(f"收到消息: {message.content}")
            response = await next_handler(message)
            print(f"回复: {response}")
            return response
    ```
    """
    
    priority: int = 100
    
    @abstractmethod
    async def process(self, message: Message, next_handler: Callable) -> str:
        """处理消息"""
        pass


class XiaoMengBot:
    """
    XiaoMengBot 主类 - 一键启动机器人
    
    示例:
    ```python
    # 最简单的使用方式
    bot = XiaoMengBot()
    await bot.start()
    response = await bot.chat("你好")
    print(response)
    
    # 自定义配置
    bot = XiaoMengBot(config=BotConfig(
        name="小螃蟹",
        llm_model="qwen2.5:7b"
    ))
    
    # 添加插件
    bot.add_plugin(MyPlugin())
    
    # 添加工具
    bot.add_tool(WeatherTool())
    
    # 添加中间件
    bot.add_middleware(LoggingMiddleware())
    
    # 启动
    await bot.start()
    ```
    """
    
    def __init__(
        self,
        config: Optional[BotConfig] = None,
        config_path: Optional[str] = None
    ):
        if config_path:
            self.config = BotConfig.from_file(config_path)
        else:
            self.config = config or BotConfig()
        
        self._plugins: List[Plugin] = []
        self._tools: List[Tool] = []
        self._middlewares: List[Middleware] = []
        self._started = False
        
        self._user_manager: Optional[UserManager] = None
        self._session_manager: Optional[SessionManager] = None
        self._llm_client: Optional[LLMClient] = None
        self._memory_manager: Optional[MemoryManager] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._skill_manager: Optional[SkillManager] = None
        self._scheduler: Optional[PriorityScheduler] = None
    
    def add_plugin(self, plugin: Plugin) -> "XiaoMengBot":
        """添加插件"""
        self._plugins.append(plugin)
        return self
    
    def add_tool(self, tool: Tool) -> "XiaoMengBot":
        """添加工具"""
        self._tools.append(tool)
        return self
    
    def add_middleware(self, middleware: Middleware) -> "XiaoMengBot":
        """添加中间件"""
        self._middlewares.append(middleware)
        return self
    
    async def start(self) -> None:
        """启动机器人"""
        if self._started:
            return
        
        self._user_manager = UserManager()
        self._session_manager = SessionManager()
        self._memory_manager = MemoryManager()
        self._tool_registry = ToolRegistry.get_instance()
        self._skill_manager = SkillManager()
        self._scheduler = PriorityScheduler()
        
        for tool in self._tools:
            self._tool_registry.register_tool(tool)
        
        for plugin in self._plugins:
            await plugin.on_load(self)
        
        self._started = True
    
    async def stop(self) -> None:
        """停止机器人"""
        for plugin in self._plugins:
            await plugin.on_unload(self)
        self._started = False
    
    async def chat(
        self,
        content: str,
        user_id: Optional[str] = None,
        source: Source = Source.CLI
    ) -> str:
        """
        发送消息并获取回复
        
        Args:
            content: 消息内容
            user_id: 用户ID，默认为 owner
            source: 消息来源
        
        Returns:
            机器人回复
        """
        if not self._started:
            await self.start()
        
        user_id = user_id or self.config.owner_id
        user = User(user_id=user_id, level=UserLevel.OWNER)
        message = Message(source=source, user=user, content=content)
        
        response = await self._process_message(message)
        
        for plugin in self._plugins:
            response = await plugin.on_message(message, response)
        
        return response
    
    async def _process_message(self, message: Message) -> str:
        """处理消息"""
        persona = self._memory_manager.load_persona()
        
        messages = [
            {"role": "system", "content": persona.soul or f"你是{self.config.name}"},
            {"role": "user", "content": message.content}
        ]
        
        response = await self._llm_client.chat(messages=messages)
        return response.get("content", "")
    
    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        return self._user_manager.get_user(user_id) if self._user_manager else None
    
    def get_memory(self) -> MemoryManager:
        """获取记忆管理器"""
        return self._memory_manager
    
    def get_tools(self) -> ToolRegistry:
        """获取工具注册表"""
        return self._tool_registry
    
    def get_skills(self) -> SkillManager:
        """获取技能管理器"""
        return self._skill_manager


def create_bot(
    name: str = "小萌",
    model: str = "qwen2.5:3b",
    **kwargs
) -> XiaoMengBot:
    """
    快速创建机器人
    
    示例:
    ```python
    bot = create_bot(name="小螃蟹", model="qwen2.5:7b")
    response = await bot.chat("你好")
    ```
    """
    config = BotConfig(name=name, llm_model=model, **kwargs)
    return XiaoMengBot(config=config)


__all__ = [
    "XiaoMengBot",
    "BotConfig",
    "Plugin",
    "Tool",
    "Middleware",
    "create_bot",
]
