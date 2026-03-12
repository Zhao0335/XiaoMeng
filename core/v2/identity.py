"""
XiaoMengCore v2 - 统一身份系统

核心概念：
1. Identity: 规范身份（一个真实用户）
2. PlatformIdentity: 平台身份（QQ号、微信号、Telegram ID等）
3. IdentityLink: 身份映射（将平台身份映射到规范身份）

这样实现跨平台统一：
- 用户用 QQ 发消息 → 映射到 identity:alice → 同一个 session
- 用户用微信发消息 → 映射到 identity:alice → 同一个 session
- Agent 看到的是同一个人沿时间顺序发的消息
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Set
from datetime import datetime
from pathlib import Path
import json
import hashlib


class Platform(Enum):
    QQ = "qq"
    WECHAT = "wechat"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WEBSOCKET = "websocket"
    HTTP = "http"
    CLI = "cli"
    WEBCHAT = "webchat"
    PLUGIN = "plugin"


@dataclass
class PlatformIdentity:
    platform: Platform
    platform_user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def identity_key(self) -> str:
        return f"{self.platform.value}:{self.platform_user_id}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform.value,
            "platform_user_id": self.platform_user_id,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlatformIdentity":
        return cls(
            platform=Platform(data["platform"]),
            platform_user_id=data["platform_user_id"],
            display_name=data.get("display_name"),
            avatar_url=data.get("avatar_url"),
            metadata=data.get("metadata", {})
        )


@dataclass
class Identity:
    """
    规范身份 - 代表一个真实用户
    
    一个 Identity 可以关联多个 PlatformIdentity
    例如：
    - identity:alice 关联 qq:12345, wechat:wxid_xxx, telegram:456789
    - 无论从哪个平台发消息，都会路由到同一个 session
    """
    identity_id: str
    display_name: Optional[str] = None
    level: str = "normal"
    group_id: Optional[str] = None
    platform_identities: List[PlatformIdentity] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_platform_identity(self, platform_identity: PlatformIdentity):
        for existing in self.platform_identities:
            if existing.identity_key == platform_identity.identity_key:
                return
        self.platform_identities.append(platform_identity)
    
    def get_platform_identity(self, platform: Platform, user_id: str) -> Optional[PlatformIdentity]:
        for pi in self.platform_identities:
            if pi.platform == platform and pi.platform_user_id == user_id:
                return pi
        return None
    
    def has_platform(self, platform: Platform) -> bool:
        return any(pi.platform == platform for pi in self.platform_identities)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "display_name": self.display_name,
            "level": self.level,
            "group_id": self.group_id,
            "platform_identities": [pi.to_dict() for pi in self.platform_identities],
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Identity":
        return cls(
            identity_id=data["identity_id"],
            display_name=data.get("display_name"),
            level=data.get("level", "normal"),
            group_id=data.get("group_id"),
            platform_identities=[PlatformIdentity.from_dict(pi) for pi in data.get("platform_identities", [])],
            preferences=data.get("preferences", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else datetime.now(),
            metadata=data.get("metadata", {})
        )


class IdentityManager:
    """
    身份管理器
    
    管理 Identity 和 PlatformIdentity 的映射关系
    """
    
    _instance: Optional["IdentityManager"] = None
    
    def __init__(self, data_dir: str = "data/identities"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        self._identities: Dict[str, Identity] = {}
        self._platform_to_identity: Dict[str, str] = {}
        
        self._load_identities()
    
    @classmethod
    def get_instance(cls) -> "IdentityManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _load_identities(self):
        identities_file = self._data_dir / "identities.json"
        if identities_file.exists():
            try:
                with open(identities_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for identity_data in data.get("identities", []):
                        identity = Identity.from_dict(identity_data)
                        self._identities[identity.identity_id] = identity
                        for pi in identity.platform_identities:
                            self._platform_to_identity[pi.identity_key] = identity.identity_id
            except Exception as e:
                print(f"加载身份失败: {e}")
    
    def _save_identities(self):
        identities_file = self._data_dir / "identities.json"
        data = {
            "identities": [identity.to_dict() for identity in self._identities.values()],
            "updated_at": datetime.now().isoformat()
        }
        with open(identities_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    def create_identity(
        self,
        identity_id: str,
        display_name: Optional[str] = None,
        level: str = "normal",
        group_id: Optional[str] = None
    ) -> Identity:
        identity = Identity(
            identity_id=identity_id,
            display_name=display_name,
            level=level,
            group_id=group_id
        )
        self._identities[identity_id] = identity
        self._save_identities()
        return identity
    
    def get_identity(self, identity_id: str) -> Optional[Identity]:
        return self._identities.get(identity_id)
    
    def resolve_identity(
        self,
        platform: Platform,
        platform_user_id: str
    ) -> Optional[Identity]:
        """
        通过平台身份解析规范身份
        
        这是跨平台统一的核心：
        - 输入: platform=QQ, platform_user_id="12345"
        - 输出: Identity(identity_id="alice", ...)
        """
        identity_key = f"{platform.value}:{platform_user_id}"
        identity_id = self._platform_to_identity.get(identity_key)
        if identity_id:
            return self._identities.get(identity_id)
        return None
    
    def link_platform_identity(
        self,
        identity_id: str,
        platform: Platform,
        platform_user_id: str,
        display_name: Optional[str] = None
    ) -> bool:
        """
        将平台身份关联到规范身份
        
        例如：
        link_platform_identity("alice", Platform.QQ, "12345")
        link_platform_identity("alice", Platform.WECHAT, "wxid_xxx")
        
        之后无论从 QQ 还是微信发消息，都会映射到 alice
        """
        identity = self._identities.get(identity_id)
        if not identity:
            return False
        
        platform_identity = PlatformIdentity(
            platform=platform,
            platform_user_id=platform_user_id,
            display_name=display_name
        )
        
        identity.add_platform_identity(platform_identity)
        self._platform_to_identity[platform_identity.identity_key] = identity_id
        identity.last_active = datetime.now()
        
        self._save_identities()
        return True
    
    def unlink_platform_identity(
        self,
        identity_id: str,
        platform: Platform,
        platform_user_id: str
    ) -> bool:
        identity = self._identities.get(identity_id)
        if not identity:
            return False
        
        identity_key = f"{platform.value}:{platform_user_id}"
        identity.platform_identities = [
            pi for pi in identity.platform_identities 
            if pi.identity_key != identity_key
        ]
        self._platform_to_identity.pop(identity_key, None)
        
        self._save_identities()
        return True
    
    def get_or_create_identity(
        self,
        platform: Platform,
        platform_user_id: str,
        display_name: Optional[str] = None,
        level: str = "normal"
    ) -> Identity:
        """
        获取或创建身份
        
        如果平台身份已关联，返回对应的规范身份
        否则创建新的规范身份
        """
        identity = self.resolve_identity(platform, platform_user_id)
        if identity:
            identity.last_active = datetime.now()
            return identity
        
        identity_id = f"user_{platform.value}_{platform_user_id}"
        identity = self.create_identity(
            identity_id=identity_id,
            display_name=display_name,
            level=level
        )
        
        self.link_platform_identity(
            identity_id=identity_id,
            platform=platform,
            platform_user_id=platform_user_id,
            display_name=display_name
        )
        
        return identity
    
    def list_identities(self) -> List[Identity]:
        return list(self._identities.values())
    
    def get_identities_by_group(self, group_id: str) -> List[Identity]:
        return [i for i in self._identities.values() if i.group_id == group_id]
    
    def import_identity_links(self, links: Dict[str, List[str]]):
        """
        批量导入身份映射
        
        参考 OpenClaw 的 identityLinks 配置：
        {
            "alice": ["qq:12345", "wechat:wxid_xxx", "telegram:456789"],
            "bob": ["qq:67890", "discord:123456789"]
        }
        """
        for identity_id, platform_keys in links.items():
            if identity_id not in self._identities:
                self.create_identity(identity_id)
            
            for platform_key in platform_keys:
                try:
                    parts = platform_key.split(":", 1)
                    if len(parts) == 2:
                        platform = Platform(parts[0])
                        platform_user_id = parts[1]
                        self.link_platform_identity(identity_id, platform, platform_user_id)
                except ValueError:
                    print(f"无效的平台键: {platform_key}")
        
        self._save_identities()
