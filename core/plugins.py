"""
XiaoMengCore 插件系统
兼容 OpenClaw 插件机制

插件结构：
plugins/
├── my-plugin/
│   ├── plugin.json      # 插件配置
│   ├── main.py          # 插件入口（可选）
│   └── SKILL.md         # 插件技能（可选）
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Callable, Awaitable
from pathlib import Path
import json
import asyncio
import importlib.util
import sys

from models import User


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    enabled: bool = True
    priority: int = 100
    
    requires: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PluginMetadata":
        return cls(
            name=data.get("name", "unnamed"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
            requires=data.get("requires", []),
            provides=data.get("provides", []),
            hooks=data.get("hooks", [])
        )


@dataclass
class Plugin:
    """插件定义"""
    metadata: PluginMetadata
    plugin_dir: Path
    main_module: Optional[Any] = None
    skill_path: Optional[Path] = None
    
    _handlers: Dict[str, Callable] = field(default_factory=dict)
    _tools: List[Dict] = field(default_factory=list)
    
    async def initialize(self) -> bool:
        """初始化插件"""
        main_file = self.plugin_dir / "main.py"
        if main_file.exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    f"plugin_{self.metadata.name}",
                    main_file
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[f"plugin_{self.metadata.name}"] = module
                    spec.loader.exec_module(module)
                    self.main_module = module
                    
                    if hasattr(module, 'on_load'):
                        await module.on_load()
                    
                    if hasattr(module, 'HANDLERS'):
                        self._handlers = module.HANDLERS
                    
                    if hasattr(module, 'TOOLS'):
                        self._tools = module.TOOLS
                    
                    return True
            except Exception as e:
                print(f"插件 {self.metadata.name} 初始化失败: {e}")
                return False
        
        return True
    
    async def unload(self):
        """卸载插件"""
        if self.main_module and hasattr(self.main_module, 'on_unload'):
            await self.main_module.on_unload()
    
    def get_handler(self, event: str) -> Optional[Callable]:
        """获取事件处理器"""
        return self._handlers.get(event)
    
    def get_tools(self) -> List[Dict]:
        """获取插件提供的工具"""
        return self._tools
    
    def has_skill(self) -> bool:
        """是否有技能文件"""
        skill_file = self.plugin_dir / "SKILL.md"
        return skill_file.exists()


class PluginManager:
    """
    插件管理器
    
    参考 OpenClaw 插件机制
    """
    
    _instance: Optional["PluginManager"] = None
    
    def __init__(self, plugins_dir: str = "plugins"):
        self._plugins_dir = Path(plugins_dir)
        self._plugins: Dict[str, Plugin] = {}
        self._tools: Dict[str, Dict] = {}
        self._hooks: Dict[str, List[Callable]] = {}
        
        self._load_plugins()
    
    def _load_plugins(self):
        """加载所有插件"""
        if not self._plugins_dir.exists():
            self._plugins_dir.mkdir(parents=True, exist_ok=True)
            return
        
        for plugin_dir in self._plugins_dir.iterdir():
            if plugin_dir.is_dir():
                self._load_plugin(plugin_dir)
    
    def _load_plugin(self, plugin_dir: Path) -> Optional[Plugin]:
        """加载单个插件"""
        manifest_file = plugin_dir / "plugin.json"
        
        if not manifest_file.exists():
            return None
        
        try:
            manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            metadata = PluginMetadata.from_dict(manifest)
            
            if not metadata.enabled:
                return None
            
            plugin = Plugin(
                metadata=metadata,
                plugin_dir=plugin_dir,
                skill_path=plugin_dir / "SKILL.md" if (plugin_dir / "SKILL.md").exists() else None
            )
            
            self._plugins[metadata.name] = plugin
            
            for hook in metadata.hooks:
                if hook not in self._hooks:
                    self._hooks[hook] = []
                self._hooks[hook].append(plugin)
            
            return plugin
            
        except Exception as e:
            print(f"加载插件 {plugin_dir.name} 失败: {e}")
            return None
    
    async def initialize_plugins(self):
        """初始化所有插件"""
        for plugin in self._plugins.values():
            success = await plugin.initialize()
            if success:
                for tool in plugin.get_tools():
                    tool_name = tool.get("name", plugin.metadata.name)
                    self._tools[tool_name] = {
                        "plugin": plugin.metadata.name,
                        "schema": tool
                    }
    
    async def unload_all(self):
        """卸载所有插件"""
        for plugin in self._plugins.values():
            await plugin.unload()
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """获取插件"""
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[Plugin]:
        """列出所有插件"""
        return list(self._plugins.values())
    
    def get_all_tools(self) -> Dict[str, Dict]:
        """获取所有插件工具"""
        return self._tools
    
    def get_skill_paths(self) -> List[Path]:
        """获取所有插件的技能路径"""
        return [
            p.skill_path 
            for p in self._plugins.values() 
            if p.skill_path and p.skill_path.exists()
        ]
    
    async def emit_event(self, event: str, *args, **kwargs) -> List[Any]:
        """触发事件"""
        results = []
        for plugin in self._hooks.get(event, []):
            handler = plugin.get_handler(event)
            if handler:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        result = await handler(*args, **kwargs)
                    else:
                        result = handler(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    print(f"插件 {plugin.metadata.name} 处理事件 {event} 失败: {e}")
        return results
    
    def enable_plugin(self, name: str) -> bool:
        """启用插件"""
        plugin = self._plugins.get(name)
        if plugin:
            plugin.metadata.enabled = True
            self._save_plugin_manifest(plugin)
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """禁用插件"""
        plugin = self._plugins.get(name)
        if plugin:
            plugin.metadata.enabled = False
            self._save_plugin_manifest(plugin)
            return True
        return False
    
    def _save_plugin_manifest(self, plugin: Plugin):
        """保存插件配置"""
        manifest_file = plugin.plugin_dir / "plugin.json"
        manifest = {
            "name": plugin.metadata.name,
            "version": plugin.metadata.version,
            "description": plugin.metadata.description,
            "author": plugin.metadata.author,
            "enabled": plugin.metadata.enabled,
            "priority": plugin.metadata.priority,
            "requires": plugin.metadata.requires,
            "provides": plugin.metadata.provides,
            "hooks": plugin.metadata.hooks
        }
        manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    
    def install_plugin(self, source: str) -> Optional[Plugin]:
        """安装插件（从目录或 Git）"""
        import shutil
        
        if Path(source).is_dir():
            source_path = Path(source)
            plugin_name = source_path.name
            dest_path = self._plugins_dir / plugin_name
            
            if dest_path.exists():
                shutil.rmtree(dest_path)
            
            shutil.copytree(source_path, dest_path)
            return self._load_plugin(dest_path)
        
        return None
    
    def uninstall_plugin(self, name: str) -> bool:
        """卸载插件"""
        import shutil
        
        plugin = self._plugins.get(name)
        if plugin:
            shutil.rmtree(plugin.plugin_dir)
            del self._plugins[name]
            return True
        return False
    
    @classmethod
    def get_instance(cls) -> "PluginManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def initialize(cls, plugins_dir: str = "plugins") -> "PluginManager":
        cls._instance = cls(plugins_dir)
        return cls._instance
