"""
XiaoMengCore 配置系统
支持高度自定义化的配置管理
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml
import json


@dataclass
class ChannelIdentity:
    """渠道身份配置 - 用于将多个渠道身份映射到同一个用户"""
    source: str
    channel_user_id: str
    display_name: Optional[str] = None


@dataclass
class UserGroupConfig:
    """用户组配置 - 定义哪些渠道身份共享同一个会话"""
    group_id: str
    name: str
    identities: List[ChannelIdentity]
    user_level: str = "stranger"
    preferences: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OwnerConfig:
    """主人配置"""
    user_id: str
    identities: List[ChannelIdentity] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WhitelistConfig:
    """白名单配置"""
    enabled: bool = True
    pairing_code: Optional[str] = None
    pairing_enabled: bool = True
    users: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.7
    system_prompt: str = ""


@dataclass
class MemoryConfig:
    """记忆系统配置"""
    enabled: bool = True
    storage_type: str = "hybrid"
    short_term_limit: int = 20
    long_term_enabled: bool = True
    graph_enabled: bool = False
    graphiti_uri: str = "bolt://localhost:7687"
    vector_enabled: bool = True
    chroma_persist_dir: str = "./data/chroma"
    markdown_enabled: bool = True
    markdown_dir: str = "./data/memories"


@dataclass
class GatewayConfig:
    """网关配置"""
    enabled_channels: List[str] = field(default_factory=lambda: ["cli"])
    qq_websocket_url: str = "ws://127.0.0.1:3001"
    http_port: int = 8080
    http_host: str = "0.0.0.0"
    websocket_port: int = 18789
    websocket_host: str = "127.0.0.1"


@dataclass
class SessionConfig:
    """会话配置"""
    session_timeout: int = 3600
    max_history_length: int = 50
    auto_save: bool = True
    save_interval: int = 60


@dataclass
class VersionControlConfig:
    """版本控制配置"""
    enabled: bool = True
    enable_git: bool = True
    require_confirmation: bool = False
    audit_log_dir: str = "./data/audit"
    pending_dir: str = "./data/pending"


@dataclass
class SecurityConfig:
    """安全配置"""
    dm_policy: str = "pairing"
    sandbox_mode: str = "disabled"
    allowed_tools: List[str] = field(default_factory=lambda: ["*"])
    denied_tools: List[str] = field(default_factory=list)


@dataclass
class ModelEndpointConfig:
    """单个模型端点配置"""
    model_id: str
    layer: str = "basic"
    role: str = "chat"
    endpoint: str = "http://localhost:11434/v1"
    model_name: str = ""
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    enabled: bool = True
    priority: int = 1


@dataclass
class ModelsConfig:
    """多模型配置"""
    enabled: bool = True
    basic_layer: List[ModelEndpointConfig] = field(default_factory=list)
    brain_layer: List[ModelEndpointConfig] = field(default_factory=list)
    special_layer: List[ModelEndpointConfig] = field(default_factory=list)


@dataclass
class XiaoMengConfig:
    """XiaoMengCore 主配置"""
    owner: OwnerConfig
    whitelist: WhitelistConfig = field(default_factory=WhitelistConfig)
    user_groups: Dict[str, UserGroupConfig] = field(default_factory=dict)
    llm: LLMConfig = field(default_factory=LLMConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    version_control: VersionControlConfig = field(default_factory=VersionControlConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    data_dir: str = "./data"
    
    @classmethod
    def from_yaml(cls, path: str) -> "XiaoMengConfig":
        """从 YAML 文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)
    
    @classmethod
    def from_json(cls, path: str) -> "XiaoMengConfig":
        """从 JSON 文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls._from_dict(data)
    
    @classmethod
    def _from_dict(cls, data: Dict) -> "XiaoMengConfig":
        """从字典创建配置对象"""
        owner_data = data.get("owner", {})
        owner = OwnerConfig(
            user_id=owner_data.get("user_id", ""),
            identities=[
                ChannelIdentity(**i) for i in owner_data.get("identities", [])
            ],
            preferences=owner_data.get("preferences", {})
        )
        
        whitelist_data = data.get("whitelist", {})
        whitelist = WhitelistConfig(
            enabled=whitelist_data.get("enabled", True),
            pairing_code=whitelist_data.get("pairing_code"),
            pairing_enabled=whitelist_data.get("pairing_enabled", True),
            users=whitelist_data.get("users", [])
        )
        
        user_groups = {}
        for gid, gdata in data.get("user_groups", {}).items():
            user_groups[gid] = UserGroupConfig(
                group_id=gid,
                name=gdata.get("name", gid),
                identities=[
                    ChannelIdentity(**i) for i in gdata.get("identities", [])
                ],
                user_level=gdata.get("user_level", "stranger"),
                preferences=gdata.get("preferences", {})
            )
        
        llm_data = data.get("llm", {})
        llm = LLMConfig(
            provider=llm_data.get("provider", "deepseek"),
            api_key=llm_data.get("api_key", ""),
            base_url=llm_data.get("base_url", "https://api.deepseek.com/v1"),
            model=llm_data.get("model", "deepseek-chat"),
            max_tokens=llm_data.get("max_tokens", 4096),
            temperature=llm_data.get("temperature", 0.7),
            system_prompt=llm_data.get("system_prompt", "")
        )
        
        models_data = data.get("models", {})
        def parse_model_list(model_list: List[Dict]) -> List[ModelEndpointConfig]:
            return [
                ModelEndpointConfig(
                    model_id=m.get("model_id", f"model_{i}"),
                    layer=m.get("layer", "basic"),
                    role=m.get("role", "chat"),
                    endpoint=m.get("endpoint", "http://localhost:11434/v1"),
                    model_name=m.get("model_name", ""),
                    api_key=m.get("api_key"),
                    max_tokens=m.get("max_tokens", 4096),
                    temperature=m.get("temperature", 0.7),
                    timeout=m.get("timeout", 60),
                    enabled=m.get("enabled", True),
                    priority=m.get("priority", 1)
                )
                for i, m in enumerate(model_list)
            ]
        
        models = ModelsConfig(
            enabled=models_data.get("enabled", True),
            basic_layer=parse_model_list(models_data.get("basic_layer", [])),
            brain_layer=parse_model_list(models_data.get("brain_layer", [])),
            special_layer=parse_model_list(models_data.get("special_layer", []))
        )
        
        memory_data = data.get("memory", {})
        memory = MemoryConfig(
            enabled=memory_data.get("enabled", True),
            storage_type=memory_data.get("storage_type", "hybrid"),
            short_term_limit=memory_data.get("short_term_limit", 20),
            long_term_enabled=memory_data.get("long_term_enabled", True),
            graph_enabled=memory_data.get("graph_enabled", False),
            graphiti_uri=memory_data.get("graphiti_uri", "bolt://localhost:7687"),
            vector_enabled=memory_data.get("vector_enabled", True),
            chroma_persist_dir=memory_data.get("chroma_persist_dir", "./data/chroma"),
            markdown_enabled=memory_data.get("markdown_enabled", True),
            markdown_dir=memory_data.get("markdown_dir", "./data/memories")
        )
        
        gateway_data = data.get("gateway", {})
        gateway = GatewayConfig(
            enabled_channels=gateway_data.get("enabled_channels", ["cli"]),
            qq_websocket_url=gateway_data.get("qq_websocket_url", "ws://127.0.0.1:3001"),
            http_port=gateway_data.get("http_port", 8080),
            http_host=gateway_data.get("http_host", "0.0.0.0"),
            websocket_port=gateway_data.get("websocket_port", 18789),
            websocket_host=gateway_data.get("websocket_host", "127.0.0.1")
        )
        
        session_data = data.get("session", {})
        session = SessionConfig(
            session_timeout=session_data.get("session_timeout", 3600),
            max_history_length=session_data.get("max_history_length", 50),
            auto_save=session_data.get("auto_save", True),
            save_interval=session_data.get("save_interval", 60)
        )
        
        return cls(
            owner=owner,
            whitelist=whitelist,
            user_groups=user_groups,
            llm=llm,
            models=models,
            memory=memory,
            gateway=gateway,
            session=session,
            data_dir=data.get("data_dir", "./data")
        )
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "owner": {
                "user_id": self.owner.user_id,
                "identities": [
                    {"source": i.source, "channel_user_id": i.channel_user_id, "display_name": i.display_name}
                    for i in self.owner.identities
                ],
                "preferences": self.owner.preferences
            },
            "whitelist": {
                "enabled": self.whitelist.enabled,
                "pairing_code": self.whitelist.pairing_code,
                "pairing_enabled": self.whitelist.pairing_enabled,
                "users": self.whitelist.users
            },
            "user_groups": {
                gid: {
                    "name": g.name,
                    "identities": [
                        {"source": i.source, "channel_user_id": i.channel_user_id, "display_name": i.display_name}
                        for i in g.identities
                    ],
                    "user_level": g.user_level,
                    "preferences": g.preferences
                }
                for gid, g in self.user_groups.items()
            },
            "llm": {
                "provider": self.llm.provider,
                "api_key": self.llm.api_key,
                "base_url": self.llm.base_url,
                "model": self.llm.model,
                "max_tokens": self.llm.max_tokens,
                "temperature": self.llm.temperature,
                "system_prompt": self.llm.system_prompt
            },
            "models": {
                "enabled": self.models.enabled,
                "basic_layer": [
                    {
                        "model_id": m.model_id,
                        "layer": m.layer,
                        "role": m.role,
                        "endpoint": m.endpoint,
                        "model_name": m.model_name,
                        "api_key": m.api_key,
                        "max_tokens": m.max_tokens,
                        "temperature": m.temperature,
                        "timeout": m.timeout,
                        "enabled": m.enabled,
                        "priority": m.priority
                    }
                    for m in self.models.basic_layer
                ],
                "brain_layer": [
                    {
                        "model_id": m.model_id,
                        "layer": m.layer,
                        "role": m.role,
                        "endpoint": m.endpoint,
                        "model_name": m.model_name,
                        "api_key": m.api_key,
                        "max_tokens": m.max_tokens,
                        "temperature": m.temperature,
                        "timeout": m.timeout,
                        "enabled": m.enabled,
                        "priority": m.priority
                    }
                    for m in self.models.brain_layer
                ],
                "special_layer": [
                    {
                        "model_id": m.model_id,
                        "layer": m.layer,
                        "role": m.role,
                        "endpoint": m.endpoint,
                        "model_name": m.model_name,
                        "api_key": m.api_key,
                        "max_tokens": m.max_tokens,
                        "temperature": m.temperature,
                        "timeout": m.timeout,
                        "enabled": m.enabled,
                        "priority": m.priority
                    }
                    for m in self.models.special_layer
                ]
            },
            "memory": {
                "enabled": self.memory.enabled,
                "storage_type": self.memory.storage_type,
                "short_term_limit": self.memory.short_term_limit,
                "long_term_enabled": self.memory.long_term_enabled,
                "graph_enabled": self.memory.graph_enabled,
                "graphiti_uri": self.memory.graphiti_uri,
                "vector_enabled": self.memory.vector_enabled,
                "chroma_persist_dir": self.memory.chroma_persist_dir,
                "markdown_enabled": self.memory.markdown_enabled,
                "markdown_dir": self.memory.markdown_dir
            },
            "gateway": {
                "enabled_channels": self.gateway.enabled_channels,
                "qq_websocket_url": self.gateway.qq_websocket_url,
                "http_port": self.gateway.http_port,
                "http_host": self.gateway.http_host,
                "websocket_port": self.gateway.websocket_port,
                "websocket_host": self.gateway.websocket_host
            },
            "session": {
                "session_timeout": self.session.session_timeout,
                "max_history_length": self.session.max_history_length,
                "auto_save": self.session.auto_save,
                "save_interval": self.session.save_interval
            },
            "data_dir": self.data_dir
        }
    
    def save_yaml(self, path: str):
        """保存为 YAML 文件"""
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True, default_flow_style=False)
    
    def save_json(self, path: str):
        """保存为 JSON 文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


class ConfigManager:
    """配置管理器"""
    
    _instance: Optional["ConfigManager"] = None
    _config: Optional[XiaoMengConfig] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def load(self, config_path: str) -> XiaoMengConfig:
        """加载配置"""
        path = Path(config_path)
        if path.suffix in [".yaml", ".yml"]:
            self._config = XiaoMengConfig.from_yaml(config_path)
        elif path.suffix == ".json":
            self._config = XiaoMengConfig.from_json(config_path)
        else:
            raise ValueError(f"不支持的配置文件格式: {path.suffix}")
        return self._config
    
    def get(self) -> XiaoMengConfig:
        """获取当前配置"""
        if self._config is None:
            raise RuntimeError("配置未加载，请先调用 load()")
        return self._config
    
    def reload(self, config_path: str) -> XiaoMengConfig:
        """重新加载配置"""
        return self.load(config_path)
    
    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
