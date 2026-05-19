"""
插件加载器

自动发现和加载 plugins/ 目录下的所有插件
"""

import importlib
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .base import PluginBase, PluginMetadata, PluginState

logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    """插件加载错误"""
    pass


class PluginLoader:
    """
    插件加载器
    
    功能：
    - 自动发现 plugins/ 目录下的所有插件
    - 动态加载插件模块
    - 验证插件接口
    - 管理插件配置
    """
    
    PLUGIN_ENTRY_FILE = "plugin.py"
    PLUGIN_CONFIG_FILE = "config.json"
    PLUGIN_MANIFEST_FILE = "manifest.json"
    
    def __init__(
        self,
        plugins_dir: Path,
        auto_discover: bool = True,
    ):
        self._plugins_dir = plugins_dir
        self._auto_discover = auto_discover
        self._discovered: Dict[str, Path] = {}
        self._loaded: Dict[str, PluginBase] = {}
        self._plugin_classes: Dict[str, Type[PluginBase]] = {}
        
        plugins_dir_str = str(plugins_dir.absolute())
        if plugins_dir_str not in sys.path:
            sys.path.insert(0, plugins_dir_str)
        
        if auto_discover:
            self.discover()
    
    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir
    
    @property
    def discovered(self) -> Dict[str, Path]:
        return self._discovered
    
    @property
    def loaded(self) -> Dict[str, PluginBase]:
        return self._loaded
    
    def discover(self) -> Dict[str, Path]:
        """
        发现所有可用插件
        
        Returns:
            Dict[str, Path]: 插件名称 -> 插件目录
        """
        self._discovered.clear()
        
        if not self._plugins_dir.exists():
            logger.warning(f"插件目录不存在: {self._plugins_dir}")
            return self._discovered
        
        for plugin_path in self._plugins_dir.iterdir():
            if not plugin_path.is_dir():
                continue
            
            if plugin_path.name.startswith("_") or plugin_path.name.startswith("."):
                continue
            
            entry_file = plugin_path / self.PLUGIN_ENTRY_FILE
            if not entry_file.exists():
                logger.debug(f"跳过无效插件目录: {plugin_path.name} (缺少 plugin.py)")
                continue
            
            self._discovered[plugin_path.name] = plugin_path
            logger.debug(f"发现插件: {plugin_path.name}")
        
        logger.info(f"发现 {len(self._discovered)} 个插件")
        return self._discovered
    
    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """
        获取插件配置
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Dict[str, Any]: 插件配置
        """
        if plugin_name not in self._discovered:
            return {}
        
        plugin_dir = self._discovered[plugin_name]
        config_file = plugin_dir / self.PLUGIN_CONFIG_FILE
        
        if config_file.exists():
            try:
                return json.loads(config_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"加载插件配置失败 [{plugin_name}]: {e}")
        
        return {"enabled": True}
    
    def load_plugin_class(self, plugin_name: str) -> Optional[Type[PluginBase]]:
        """
        加载插件类（不实例化）
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Optional[Type[PluginBase]]: 插件类
        """
        if plugin_name not in self._discovered:
            logger.error(f"未发现插件: {plugin_name}")
            return None
        
        if plugin_name in self._plugin_classes:
            return self._plugin_classes[plugin_name]
        
        plugin_dir = self._discovered[plugin_name]
        entry_file = plugin_dir / self.PLUGIN_ENTRY_FILE
        
        try:
            plugin_dir_str = str(plugin_dir.absolute())
            if plugin_dir_str not in sys.path:
                sys.path.insert(0, plugin_dir_str)
            
            init_file = plugin_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("# Plugin package\n", encoding="utf-8")
            
            module_name = plugin_name
            spec = importlib.util.spec_from_file_location(
                module_name,
                entry_file,
                submodule_search_locations=[plugin_dir_str]
            )
            
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"无法加载插件模块: {entry_file}")
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            
            spec.loader.exec_module(module)
            
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type) and
                    issubclass(attr, PluginBase) and
                    attr is not PluginBase
                ):
                    plugin_class = attr
                    break
            
            if plugin_class is None:
                for attr_name in ["Plugin", "plugin"]:
                    if hasattr(module, attr_name):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, PluginBase):
                            plugin_class = attr
                            break
            
            if plugin_class is None:
                raise PluginLoadError(f"未找到插件类: {plugin_name}")
            
            self._plugin_classes[plugin_name] = plugin_class
            logger.debug(f"加载插件类: {plugin_name} -> {plugin_class.__name__}")
            return plugin_class
            
        except Exception as e:
            logger.error(f"加载插件失败 [{plugin_name}]: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def load(
        self,
        plugin_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Optional[PluginBase]:
        """
        加载并实例化插件
        
        Args:
            plugin_name: 插件名称
            config: 插件配置（可选，默认从配置文件加载）
            
        Returns:
            Optional[PluginBase]: 插件实例
        """
        if plugin_name in self._loaded:
            return self._loaded[plugin_name]
        
        plugin_class = self.load_plugin_class(plugin_name)
        if plugin_class is None:
            return None
        
        if config is None:
            config = self.get_plugin_config(plugin_name)
        
        plugin_dir = self._discovered[plugin_name]
        
        try:
            plugin = plugin_class(
                plugin_dir=plugin_dir,
                config=config,
            )
            
            plugin._set_state(PluginState.LOADED)
            self._loaded[plugin_name] = plugin
            
            logger.info(f"加载插件成功: {plugin_name}")
            return plugin
            
        except Exception as e:
            logger.error(f"实例化插件失败 [{plugin_name}]: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def load_all(self) -> Dict[str, PluginBase]:
        """
        加载所有已发现的插件
        
        Returns:
            Dict[str, PluginBase]: 插件名称 -> 插件实例
        """
        for plugin_name in self._discovered:
            if plugin_name not in self._loaded:
                self.load(plugin_name)
        
        return self._loaded
    
    def unload(self, plugin_name: str) -> bool:
        """
        卸载插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            bool: 是否成功
        """
        if plugin_name not in self._loaded:
            return False
        
        try:
            plugin = self._loaded[plugin_name]
            if plugin.state == PluginState.RUNNING:
                import asyncio
                asyncio.create_task(plugin.on_shutdown())
            
            del self._loaded[plugin_name]
            
            if plugin_name in self._plugin_classes:
                del self._plugin_classes[plugin_name]
            
            if plugin_name in sys.modules:
                del sys.modules[plugin_name]
            
            logger.info(f"卸载插件: {plugin_name}")
            return True
            
        except Exception as e:
            logger.error(f"卸载插件失败 [{plugin_name}]: {e}")
            return False
    
    def reload(self, plugin_name: str) -> Optional[PluginBase]:
        """
        重新加载插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Optional[PluginBase]: 插件实例
        """
        self.unload(plugin_name)
        
        if plugin_name in self._discovered:
            del self._discovered[plugin_name]
        
        self.discover()
        return self.load(plugin_name)
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        获取插件信息
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Optional[Dict[str, Any]]: 插件信息
        """
        if plugin_name not in self._discovered:
            return None
        
        info = {
            "name": plugin_name,
            "path": str(self._discovered[plugin_name]),
            "loaded": plugin_name in self._loaded,
        }
        
        if plugin_name in self._loaded:
            plugin = self._loaded[plugin_name]
            info["status"] = plugin.get_status()
            info["metadata"] = plugin.get_metadata().to_dict()
        
        return info
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        列出所有插件信息
        
        Returns:
            List[Dict[str, Any]]: 插件信息列表
        """
        result = []
        for plugin_name in self._discovered:
            info = self.get_plugin_info(plugin_name)
            if info:
                result.append(info)
        return result
