"""
RenderQ - 插件注册表
"""
import importlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.base import RenderPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件注册表"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._plugins: dict[str, "RenderPlugin"] = {}
        self._initialized = True
    
    def register(self, plugin: "RenderPlugin"):
        """注册插件"""
        if plugin.name in self._plugins:
            logger.warning(f"Plugin {plugin.name} already registered, overwriting")
        self._plugins[plugin.name] = plugin
        logger.info(f"Registered plugin: {plugin.name} ({plugin.display_name})")
    
    def unregister(self, name: str):
        """取消注册插件"""
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Unregistered plugin: {name}")
    
    def get(self, name: str) -> "RenderPlugin | None":
        """获取插件"""
        return self._plugins.get(name)
    
    def get_all(self) -> dict[str, "RenderPlugin"]:
        """获取所有插件"""
        return self._plugins.copy()
    
    def list_plugins(self) -> list[dict]:
        """列出所有插件信息"""
        return [p.get_info() for p in self._plugins.values()]
    
    def load_builtin_plugins(self):
        """加载内置插件"""
        builtin_plugins = [
            "plugins.aftereffects",
            # "plugins.blender",
            # "plugins.max",
            # "plugins.ffmpeg",
        ]
        
        for module_name in builtin_plugins:
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "plugin"):
                    self.register(module.plugin)
            except ImportError as e:
                logger.warning(f"Failed to load plugin {module_name}: {e}")
    
    def load_plugins_from_directory(self, directory: Path):
        """从目录加载插件"""
        if not directory.exists():
            return
        
        for py_file in directory.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                module_name = py_file.stem
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if hasattr(module, "plugin"):
                    self.register(module.plugin)
            except Exception as e:
                logger.error(f"Failed to load plugin from {py_file}: {e}")


# 全局注册表实例
registry = PluginRegistry()


def get_plugin(name: str) -> "RenderPlugin | None":
    """获取插件的便捷函数"""
    return registry.get(name)


def get_all_plugins() -> dict[str, "RenderPlugin"]:
    """获取所有插件的便捷函数"""
    return registry.get_all()
