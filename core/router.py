"""
XiaoMengCore 增强版路由系统
这是相比OpenClaw的核心改进之一

特性：
1. 跨平台身份统一 - QQ/微信/Telegram等平台消息路由到同一会话
2. 用户分组管理 - 不同用户组有不同的权限和配置
3. 智能消息路由 - 根据消息类型、优先级、用户等级路由
4. 会话隔离 - 每个用户组独立会话
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import asyncio
import hashlib
import logging

logger = logging.getLogger(__name__)


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


class UserLevel(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    TRUSTED = "trusted"
    NORMAL = "normal"
    GUEST = "guest"


class MessagePriority(Enum):
    STEER = "steer"
    FOLLOWUP = "followup"
    COLLECT = "collect"


@dataclass
class PlatformIdentity:
    """平台身份"""
    platform: Platform
    platform_user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def identity_key(self) -> str:
        return f"{self.platform.value}:{self.platform_user_id}"
    
    def to_dict(self) -> Dict:
        return {
            "platform": self.platform.value,
            "platform_user_id": self.platform_user_id,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PlatformIdentity":
        return cls(
            platform=Platform(data["platform"]),
            platform_user_id=data["platform_user_id"],
            display_name=data.get("display_name"),
            avatar_url=data.get("avatar_url"),
            metadata=data.get("metadata", {})
        )


@dataclass
class UnifiedIdentity:
    """统一身份 - 跨平台用户身份"""
    identity_id: str
    display_name: Optional[str] = None
    level: UserLevel = UserLevel.NORMAL
    group_id: Optional[str] = None
    platform_identities: List[PlatformIdentity] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_platform_identity(self, pi: PlatformIdentity):
        for existing in self.platform_identities:
            if existing.identity_key == pi.identity_key:
                return
        self.platform_identities.append(pi)
    
    def get_platform_identity(self, platform: Platform, user_id: str) -> Optional[PlatformIdentity]:
        for pi in self.platform_identities:
            if pi.platform == platform and pi.platform_user_id == user_id:
                return pi
        return None
    
    def to_dict(self) -> Dict:
        return {
            "identity_id": self.identity_id,
            "display_name": self.display_name,
            "level": self.level.value,
            "group_id": self.group_id,
            "platform_identities": [pi.to_dict() for pi in self.platform_identities],
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "UnifiedIdentity":
        return cls(
            identity_id=data["identity_id"],
            display_name=data.get("display_name"),
            level=UserLevel(data.get("level", "normal")),
            group_id=data.get("group_id"),
            platform_identities=[PlatformIdentity.from_dict(pi) for pi in data.get("platform_identities", [])],
            preferences=data.get("preferences", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else datetime.now(),
            metadata=data.get("metadata", {})
        )


@dataclass
class UserGroup:
    """用户组"""
    group_id: str
    name: str
    description: str = ""
    owner_identity_id: Optional[str] = None
    members: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    permissions: Dict[str, bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "description": self.description,
            "owner_identity_id": self.owner_identity_id,
            "members": self.members,
            "config": self.config,
            "permissions": self.permissions,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "UserGroup":
        return cls(
            group_id=data["group_id"],
            name=data["name"],
            description=data.get("description", ""),
            owner_identity_id=data.get("owner_identity_id"),
            members=data.get("members", []),
            config=data.get("config", {}),
            permissions=data.get("permissions", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        )


@dataclass
class RoutedMessage:
    """路由后的消息"""
    message_id: str
    content: str
    identity: UnifiedIdentity
    group: Optional[UserGroup]
    platform: Platform
    platform_user_id: str
    priority: MessagePriority
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def session_key(self) -> str:
        if self.group:
            return f"group:{self.group.group_id}:{self.identity.identity_id}"
        return f"user:{self.identity.identity_id}"
    
    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "content": self.content,
            "identity": self.identity.to_dict(),
            "group": self.group.to_dict() if self.group else None,
            "platform": self.platform.value,
            "platform_user_id": self.platform_user_id,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class EnhancedRouter:
    """
    增强版路由器
    
    核心功能：
    1. 跨平台身份解析 - 将平台身份映射到统一身份
    2. 用户组管理 - 管理用户分组和权限
    3. 消息路由 - 根据优先级和规则路由消息
    4. 会话隔离 - 确保不同用户组的会话独立
    """
    
    def __init__(
        self,
        storage_path: str = "./data/router"
    ):
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        
        self._identities: Dict[str, UnifiedIdentity] = {}
        self._platform_to_identity: Dict[str, str] = {}
        self._groups: Dict[str, UserGroup] = {}
        self._identity_to_group: Dict[str, str] = {}
        
        self._hooks: Dict[str, List[Callable]] = {
            "before_route": [],
            "after_route": [],
            "identity_created": [],
            "group_created": [],
        }
        
        self._load()
    
    def _load(self):
        """加载存储的数据"""
        identities_file = self._storage_path / "identities.json"
        if identities_file.exists():
            try:
                data = json.loads(identities_file.read_text(encoding='utf-8'))
                self._identities = {k: UnifiedIdentity.from_dict(v) for k, v in data.items()}
                self._rebuild_platform_index()
            except Exception as e:
                logger.error(f"Failed to load identities: {e}")
        
        groups_file = self._storage_path / "groups.json"
        if groups_file.exists():
            try:
                data = json.loads(groups_file.read_text(encoding='utf-8'))
                self._groups = {k: UserGroup.from_dict(v) for k, v in data.items()}
                self._rebuild_group_index()
            except Exception as e:
                logger.error(f"Failed to load groups: {e}")
    
    def _save(self):
        """保存数据"""
        identities_file = self._storage_path / "identities.json"
        identities_file.write_text(
            json.dumps({k: v.to_dict() for k, v in self._identities.items()}, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        groups_file = self._storage_path / "groups.json"
        groups_file.write_text(
            json.dumps({k: v.to_dict() for k, v in self._groups.items()}, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
    
    def _rebuild_platform_index(self):
        """重建平台索引"""
        self._platform_to_identity.clear()
        for identity in self._identities.values():
            for pi in identity.platform_identities:
                self._platform_to_identity[pi.identity_key] = identity.identity_id
    
    def _rebuild_group_index(self):
        """重建组索引"""
        self._identity_to_group.clear()
        for group in self._groups.values():
            for member_id in group.members:
                self._identity_to_group[member_id] = group.group_id
    
    def resolve_identity(
        self,
        platform: Platform,
        platform_user_id: str,
        display_name: Optional[str] = None
    ) -> UnifiedIdentity:
        """解析身份 - 将平台身份映射到统一身份"""
        identity_key = f"{platform.value}:{platform_user_id}"
        
        if identity_key in self._platform_to_identity:
            identity_id = self._platform_to_identity[identity_key]
            identity = self._identities[identity_id]
            identity.last_active = datetime.now()
            if display_name and not identity.display_name:
                identity.display_name = display_name
            return identity
        
        identity_id = hashlib.md5(identity_key.encode()).hexdigest()[:16]
        
        identity = UnifiedIdentity(
            identity_id=identity_id,
            display_name=display_name or f"User_{identity_id[:8]}",
            level=UserLevel.NORMAL
        )
        
        platform_identity = PlatformIdentity(
            platform=platform,
            platform_user_id=platform_user_id,
            display_name=display_name
        )
        identity.add_platform_identity(platform_identity)
        
        self._identities[identity_id] = identity
        self._platform_to_identity[identity_key] = identity_id
        
        self._save()
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._run_hooks("identity_created", identity))
        except RuntimeError:
            pass
        
        return identity
    
    def link_platform_identity(
        self,
        identity_id: str,
        platform: Platform,
        platform_user_id: str,
        display_name: Optional[str] = None
    ) -> bool:
        """关联平台身份到统一身份"""
        if identity_id not in self._identities:
            return False
        
        identity = self._identities[identity_id]
        
        new_key = f"{platform.value}:{platform_user_id}"
        if new_key in self._platform_to_identity:
            existing_id = self._platform_to_identity[new_key]
            if existing_id != identity_id:
                return False
        
        platform_identity = PlatformIdentity(
            platform=platform,
            platform_user_id=platform_user_id,
            display_name=display_name
        )
        
        identity.add_platform_identity(platform_identity)
        self._platform_to_identity[new_key] = identity_id
        
        self._save()
        return True
    
    def create_group(
        self,
        name: str,
        owner_identity_id: str,
        description: str = ""
    ) -> UserGroup:
        """创建用户组"""
        group_id = hashlib.md5(f"{name}{owner_identity_id}{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        
        group = UserGroup(
            group_id=group_id,
            name=name,
            description=description,
            owner_identity_id=owner_identity_id,
            members=[owner_identity_id]
        )
        
        self._groups[group_id] = group
        self._identity_to_group[owner_identity_id] = group_id
        
        if owner_identity_id in self._identities:
            self._identities[owner_identity_id].group_id = group_id
        
        self._save()
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._run_hooks("group_created", group))
        except RuntimeError:
            pass
        
        return group
    
    def add_to_group(self, identity_id: str, group_id: str) -> bool:
        """将用户添加到组"""
        if identity_id not in self._identities or group_id not in self._groups:
            return False
        
        group = self._groups[group_id]
        if identity_id not in group.members:
            group.members.append(identity_id)
        
        self._identity_to_group[identity_id] = group_id
        self._identities[identity_id].group_id = group_id
        
        self._save()
        return True
    
    def get_group(self, group_id: str) -> Optional[UserGroup]:
        """获取用户组"""
        return self._groups.get(group_id)
    
    def get_identity_group(self, identity_id: str) -> Optional[UserGroup]:
        """获取用户所属组"""
        group_id = self._identity_to_group.get(identity_id)
        if group_id:
            return self._groups.get(group_id)
        return None
    
    def set_user_level(self, identity_id: str, level: UserLevel) -> bool:
        """设置用户等级"""
        if identity_id not in self._identities:
            return False
        
        self._identities[identity_id].level = level
        self._save()
        return True
    
    async def route_message(
        self,
        platform: Platform,
        platform_user_id: str,
        content: str,
        priority: MessagePriority = MessagePriority.FOLLOWUP,
        metadata: Dict = None
    ) -> RoutedMessage:
        """路由消息"""
        await self._run_hooks("before_route", platform, platform_user_id, content)
        
        identity = self.resolve_identity(platform, platform_user_id)
        group = self.get_identity_group(identity.identity_id)
        
        message_id = hashlib.md5(f"{identity.identity_id}{content}{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        
        routed = RoutedMessage(
            message_id=message_id,
            content=content,
            identity=identity,
            group=group,
            platform=platform,
            platform_user_id=platform_user_id,
            priority=priority,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        await self._run_hooks("after_route", routed)
        
        return routed
    
    def register_hook(self, hook_name: str, callback: Callable):
        """注册钩子"""
        if hook_name in self._hooks:
            self._hooks[hook_name].append(callback)
    
    async def _run_hooks(self, hook_name: str, *args, **kwargs):
        """运行钩子"""
        for callback in self._hooks.get(hook_name, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Hook {hook_name} error: {e}")
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_identities": len(self._identities),
            "total_platform_links": len(self._platform_to_identity),
            "total_groups": len(self._groups),
            "identities_by_level": {
                level.value: sum(1 for i in self._identities.values() if i.level == level)
                for level in UserLevel
            }
        }
