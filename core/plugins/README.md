# XiaoMeng 插件系统

## 概述

XiaoMeng 插件系统提供了一个标准化的插件架构，支持：

- 自动发现和加载 `plugins/` 目录下的插件
- 统一的工具（Tool）和命令（Command）分发
- 插件生命周期管理
- 配置文件支持

## 目录结构

```
XiaoMeng/
├── core/
│   └── plugins/
│       ├── __init__.py      # 模块入口
│       ├── base.py          # 插件基类和接口定义
│       ├── loader.py        # 插件加载器
│       └── manager.py       # 插件管理器
└── plugins/
    └── your_plugin/
        ├── plugin.py        # 插件入口（必须）
        ├── config.json      # 插件配置（可选）
        └── ...              # 其他文件
```

## 开发插件

### 1. 创建插件目录

```bash
mkdir -p plugins/my_plugin
```

### 2. 创建 plugin.py

```python
from pathlib import Path
from typing import Any, Dict, Optional

from core.plugins.base import PluginBase, PluginMetadata, ToolDefinition, CommandDefinition


class Plugin(PluginBase):
    """我的插件"""
    
    def __init__(self, plugin_dir: Path, config: Optional[Dict[str, Any]] = None):
        super().__init__(plugin_dir, config)
        # 初始化代码
    
    def get_metadata(self) -> PluginMetadata:
        """返回插件元数据"""
        return PluginMetadata(
            name="my_plugin",
            version="1.0.0",
            description="我的插件描述",
            author="作者名",
            tags=["tag1", "tag2"],
        )
    
    async def on_initialize(self) -> bool:
        """插件初始化"""
        # 注册工具
        self.register_tool(ToolDefinition(
            name="my_tool",
            description="工具描述",
            parameters={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "参数1"}
                },
                "required": ["arg1"]
            },
        ))
        
        # 注册命令
        self.register_command(CommandDefinition(
            prefix="/mycmd",
            description="命令描述",
            handler=self._handle_command,
        ))
        
        return True
    
    async def on_shutdown(self) -> None:
        """插件关闭"""
        pass
    
    async def on_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """工具调用处理"""
        if tool_name == "my_tool":
            return f"处理结果: {arguments.get('arg1')}"
        return f"未知工具: {tool_name}"
    
    async def on_command(
        self,
        command: str,
        args: str,
        sender_id: int,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """命令处理"""
        if command == "/mycmd":
            return f"命令执行结果: {args}"
        return None
```

### 3. 创建配置文件（可选）

```json
{
  "enabled": true,
  "custom_option": "value"
}
```

## 使用插件系统

### 初始化

```python
from pathlib import Path
from core.plugins import PluginManager

# 创建插件管理器
manager = PluginManager(
    plugins_dir=Path("plugins"),
    auto_load=True,
    auto_initialize=True,
)

# 等待初始化完成
await manager.initialize_all()
await manager.start_all()
```

### 获取所有工具 Schema

```python
# 用于 LLM Function Calling
schemas = manager.get_all_tool_schemas()
```

### 分发工具调用

```python
result = await manager.dispatch_tool_call(
    tool_name="calendar_add_event",
    arguments={"title": "会议", "date": "2024-01-15"},
    context={"qq": 123456789}
)
```

### 分发命令

```python
result = await manager.dispatch_command(
    text="/日历 查看日程",
    sender_id=123456789,
    context={"session_key": "xxx"}
)
```

### 分发消息（自动识别命令）

```python
result = await manager.dispatch_message(
    message="/日历 帮助",
    sender_id=123456789,
    context={}
)
```

## 插件接口

### PluginBase 方法

| 方法 | 必须 | 说明 |
|------|------|------|
| `get_metadata()` | ✅ | 返回插件元数据 |
| `on_initialize()` | ✅ | 插件初始化 |
| `on_shutdown()` | ✅ | 插件关闭 |
| `get_tools()` | ❌ | 返回工具定义列表 |
| `get_commands()` | ❌ | 返回命令定义列表 |
| `on_tool_call()` | ❌ | 工具调用处理 |
| `on_command()` | ❌ | 命令处理 |
| `on_message()` | ❌ | 消息处理钩子 |

### PluginMetadata 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 插件名称 |
| `version` | str | 版本号 |
| `description` | str | 描述 |
| `author` | str | 作者 |
| `tags` | List[str] | 标签 |
| `dependencies` | List[str] | 依赖 |

## 示例：集成到 XiaoMeng

```python
# 在 gateway.py 或主程序中

from pathlib import Path
from core.plugins import PluginManager

class XiaoMeng:
    def __init__(self):
        self.plugin_manager = PluginManager(
            plugins_dir=Path("plugins"),
        )
    
    async def start(self):
        await self.plugin_manager.initialize_all()
        await self.plugin_manager.start_all()
    
    async def handle_message(self, message: str, qq: int):
        # 先尝试插件处理
        result = await self.plugin_manager.dispatch_message(
            message=message,
            sender_id=qq,
            context={}
        )
        
        if result:
            return result
        
        # 其他处理逻辑...
    
    async def handle_tool_call(self, tool_name: str, arguments: dict, qq: int):
        return await self.plugin_manager.dispatch_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            context={"qq": qq}
        )
```

## 插件状态

| 状态 | 说明 |
|------|------|
| UNLOADED | 未加载 |
| LOADED | 已加载 |
| INITIALIZED | 已初始化 |
| RUNNING | 运行中 |
| ERROR | 错误 |
| DISABLED | 已禁用 |
