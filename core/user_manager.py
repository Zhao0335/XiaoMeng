"""
XiaoMengCore 用户管理器
支持渠道身份分组和多用户权限管理
"""

from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import json
import uuid

from models import User, UserLevel, ChannelIdentity, Source
from config import XiaoMengConfig, ConfigManager


class UserManager:
    """
    用户管理器
    
    核心功能：
    1. 渠道身份分组 - 多个渠道身份映射到同一个用户
    2. 身份认证 - 根据渠道身份识别用户
    3. 权限管理 - 主人/白名单/陌生人三层权限
    """
    
    _instance: Optional["UserManager"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[XiaoMengConfig] = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self._config = config or ConfigManager.get_instance().get()
        self._data_dir = Path(self._config.data_dir)
        self._users_file = self._data_dir / "users.json"
        self._whitelist_file = self._data_dir / "whitelist.json"
        
        self._users: Dict[str, User] = {}
        self._identity_map: Dict[str, str] = {}
        self._whitelist: Dict[str, datetime] = {}
        
        self._load()
        self._build_identity_map()
        self._initialized = True
    
    def _load(self):
        """加载用户数据"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        if self._users_file.exists():
            with open(self._users_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._users = {uid: User.from_dict(u) for uid, u in data.items()}
        
        if self._whitelist_file.exists():
            with open(self._whitelist_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._whitelist = {
                    uid: datetime.fromisoformat(ts) if isinstance(ts, str) else datetime.now()
                    for uid, ts in data.items()
                }
    
    def _save(self):
        """保存用户数据"""
        with open(self._users_file, 'w', encoding='utf-8') as f:
            json.dump(
                {uid: u.to_dict() for uid, u in self._users.items()},
                f, ensure_ascii=False, indent=2
            )
        
        with open(self._whitelist_file, 'w', encoding='utf-8') as f:
            json.dump(
                {uid: ts.isoformat() for uid, ts in self._whitelist.items()},
                f, ensure_ascii=False, indent=2
            )
    
    def _build_identity_map(self):
        """构建身份映射表"""
        self._identity_map = {}
        
        if self._config.owner.user_id:
            owner = self._get_or_create_owner()
            for identity in owner.identities:
                self._identity_map[identity.unique_key] = owner.user_id
        
        for gid, group in self._config.user_groups.items():
            user = self._get_or_create_group_user(gid, group)
            for identity in group.identities:
                self._identity_map[identity.unique_key] = user.user_id
    
    def _get_or_create_owner(self) -> User:
        """获取或创建主人用户"""
        owner_id = self._config.owner.user_id
        if owner_id in self._users:
            return self._users[owner_id]
        
        owner = User(
            user_id=owner_id,
            level=UserLevel.OWNER,
            identities=[
                ChannelIdentity(
                    source=Source(i.source),
                    channel_user_id=i.channel_user_id,
                    display_name=i.display_name
                )
                for i in self._config.owner.identities
            ],
            preferences=self._config.owner.preferences.copy()
        )
        self._users[owner_id] = owner
        self._save()
        return owner
    
    def _get_or_create_group_user(self, group_id: str, group_config) -> User:
        """获取或创建用户组用户"""
        if group_id in self._users:
            return self._users[group_id]
        
        level = UserLevel(group_config.user_level) if group_config.user_level in ["owner", "whitelist", "stranger"] else UserLevel.STRANGER
        
        user = User(
            user_id=group_id,
            level=level,
            identities=[
                ChannelIdentity(
                    source=Source(i.source),
                    channel_user_id=i.channel_user_id,
                    display_name=i.display_name
                )
                for i in group_config.identities
            ],
            preferences=group_config.preferences.copy()
        )
        self._users[group_id] = user
        self._save()
        return user
    
    def identify_user(self, source: Source, channel_user_id: str) -> User:
        """
        根据渠道身份识别用户
        
        这是核心方法：将渠道身份映射到用户
        """
        identity_key = f"{source.value}:{channel_user_id}"
        
        if identity_key in self._identity_map:
            user_id = self._identity_map[identity_key]
            if user_id in self._users:
                return self._users[user_id]
        
        return self._create_stranger(source, channel_user_id)
    
    def _create_stranger(self, source: Source, channel_user_id: str) -> User:
        """创建陌生人用户"""
        user_id = f"stranger_{source.value}_{channel_user_id}"
        
        if user_id in self._users:
            return self._users[user_id]
        
        user = User(
            user_id=user_id,
            level=UserLevel.STRANGER,
            identities=[
                ChannelIdentity(
                    source=source,
                    channel_user_id=channel_user_id
                )
            ]
        )
        self._users[user_id] = user
        self._identity_map[f"{source.value}:{channel_user_id}"] = user_id
        self._save()
        return user
    
    def get_user(self, user_id: str) -> Optional[User]:
        """根据用户ID获取用户"""
        return self._users.get(user_id)
    
    def get_owner(self) -> Optional[User]:
        """获取主人"""
        owner_id = self._config.owner.user_id
        return self._users.get(owner_id) if owner_id else None
    
    def is_owner(self, user: User) -> bool:
        """检查是否为主人"""
        return user.level == UserLevel.OWNER
    
    def is_whitelisted(self, user: User) -> bool:
        """检查是否为白名单用户"""
        return user.level == UserLevel.WHITELIST or user.level == UserLevel.OWNER
    
    def is_stranger(self, user: User) -> bool:
        """检查是否为陌生人"""
        return user.level == UserLevel.STRANGER
    
    def add_to_whitelist(self, user_id: str) -> bool:
        """添加用户到白名单"""
        if user_id not in self._users:
            return False
        
        user = self._users[user_id]
        user.level = UserLevel.WHITELIST
        user.whitelist_since = datetime.now()
        self._whitelist[user_id] = datetime.now()
        self._save()
        return True
    
    def remove_from_whitelist(self, user_id: str) -> bool:
        """从白名单移除用户"""
        if user_id not in self._whitelist:
            return False
        
        if user_id in self._users:
            user = self._users[user_id]
            if user.level == UserLevel.WHITELIST:
                user.level = UserLevel.STRANGER
                user.whitelist_since = None
        
        del self._whitelist[user_id]
        self._save()
        return True
    
    def add_identity_to_user(
        self, 
        user_id: str, 
        source: Source, 
        channel_user_id: str,
        display_name: Optional[str] = None
    ) -> bool:
        """
        为用户添加新的渠道身份
        
        这允许用户在多个平台使用同一个会话
        """
        if user_id not in self._users:
            return False
        
        user = self._users[user_id]
        
        if user.has_identity(source, channel_user_id):
            return True
        
        identity = ChannelIdentity(
            source=source,
            channel_user_id=channel_user_id,
            display_name=display_name
        )
        user.identities.append(identity)
        
        identity_key = f"{source.value}:{channel_user_id}"
        self._identity_map[identity_key] = user_id
        
        self._save()
        return True
    
    def remove_identity_from_user(
        self, 
        user_id: str, 
        source: Source, 
        channel_user_id: str
    ) -> bool:
        """从用户移除渠道身份"""
        if user_id not in self._users:
            return False
        
        user = self._users[user_id]
        original_len = len(user.identities)
        
        user.identities = [
            i for i in user.identities 
            if not (i.source == source and i.channel_user_id == channel_user_id)
        ]
        
        if len(user.identities) == original_len:
            return False
        
        identity_key = f"{source.value}:{channel_user_id}"
        if identity_key in self._identity_map:
            del self._identity_map[identity_key]
        
        self._save()
        return True
    
    def create_user_group(
        self,
        group_name: str,
        identities: List[Tuple[Source, str, Optional[str]]],
        level: UserLevel = UserLevel.STRANGER
    ) -> User:
        """
        创建用户组
        
        参数:
            group_name: 组名
            identities: 身份列表 [(source, channel_user_id, display_name), ...]
            level: 用户等级
        """
        group_id = f"group_{group_name}_{uuid.uuid4().hex[:8]}"
        
        channel_identities = [
            ChannelIdentity(source=s, channel_user_id=uid, display_name=dn)
            for s, uid, dn in identities
        ]
        
        user = User(
            user_id=group_id,
            level=level,
            identities=channel_identities
        )
        
        self._users[group_id] = user
        
        for identity in channel_identities:
            self._identity_map[identity.unique_key] = group_id
        
        if level == UserLevel.WHITELIST:
            self._whitelist[group_id] = datetime.now()
        
        self._save()
        return user
    
    def get_all_whitelisted_users(self) -> List[User]:
        """获取所有白名单用户"""
        return [
            self._users[uid] 
            for uid in self._whitelist.keys() 
            if uid in self._users
        ]
    
    def get_users_by_level(self, level: UserLevel) -> List[User]:
        """根据等级获取用户列表"""
        return [u for u in self._users.values() if u.level == level]
    
    def check_pairing_code(self, code: str) -> bool:
        """检查配对码"""
        if not self._config.whitelist.pairing_enabled:
            return False
        return self._config.whitelist.pairing_code == code
    
    def pair_user(self, source: Source, channel_user_id: str, pairing_code: str) -> Tuple[bool, str]:
        """
        使用配对码配对用户
        
        返回: (成功与否, 消息)
        """
        if not self.check_pairing_code(pairing_code):
            return False, "配对码错误"
        
        user = self.identify_user(source, channel_user_id)
        self.add_to_whitelist(user.user_id)
        return True, f"配对成功！欢迎加入白名单~"
    
    def reload_config(self):
        """重新加载配置"""
        self._config = ConfigManager.get_instance().get()
        self._build_identity_map()
    
    @classmethod
    def get_instance(cls) -> "UserManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
