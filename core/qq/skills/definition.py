"""
Skill 系统核心定义

基于 Harness 框架设计理念：
- SkillRegistry: 统一注册、发现、验证、启用/禁用
- Risk 分类: READ_ONLY / SENSITIVE / DANGEROUS（类比 Harness 的 read-only / effectful）
- ModelTier 过滤: 不同模型层级可用的技能不同
- UserLevel 过滤: 基于用户身份（非 QQ 号）的权限控制
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional


class SkillRisk(IntEnum):
    """技能风险等级（类比 Harness: read-only, effectful, dangerous）"""
    READ_ONLY = 0
    SENSITIVE = 1
    DANGEROUS = 2

    def label(self) -> str:
        return {
            SkillRisk.READ_ONLY: "只读",
            SkillRisk.SENSITIVE:  "敏感",
            SkillRisk.DANGEROUS: "危险",
        }[self]


class ModelTier(IntEnum):
    """模型层级（对应 ModelLayer）
    Basic  = Local 14b (Ollama)
    Brain  = Cloud DeepSeek API
    Pro    = 最强云端模型
    """
    LOCAL  = 0   # 对应 ModelLayer.BASIC
    CLOUD  = 1   # 对应 ModelLayer.BRAIN
    PRO    = 2   # 对应 ModelLayer.PRO

    @classmethod
    def from_route(cls, route: str) -> "ModelTier":
        """从路由字符串转换"""
        mapping = {"LOCAL": cls.LOCAL, "CLOUD": cls.CLOUD, "PRO": cls.PRO}
        return mapping.get(route.upper(), cls.LOCAL)

    def label(self) -> str:
        return {
            ModelTier.LOCAL: "本地模型",
            ModelTier.CLOUD: "云端模型",
            ModelTier.PRO:   "Pro 模型",
        }[self]


class UserLevel(IntEnum):
    """用户权限级别（对应 PermLevel）"""
    STRANGER  = 0
    ADMIN     = 1
    OWNER     = 2

    def label(self) -> str:
        return {
            UserLevel.STRANGER: "陌生人",
            UserLevel.ADMIN:    "管理员",
            UserLevel.OWNER:    "主人",
        }[self]


@dataclass
class SkillPermission:
    """技能权限定义

    与 plain dict 不同，这是类型安全的权限对象，可以在注册时校验。
    """
    min_user_level: UserLevel = UserLevel.STRANGER
    min_model_tier: ModelTier = ModelTier.LOCAL
    allowed_identities: List[str] = field(default_factory=list)

    def allows_user(self, level: UserLevel, identity: str = "") -> bool:
        if level < self.min_user_level:
            if self.allowed_identities and identity in self.allowed_identities:
                return True
            return False
        return True

    def allows_model(self, tier: ModelTier) -> bool:
        return tier >= self.min_model_tier


@dataclass
class SkillDefinition:
    """技能元数据定义

    类比 Harness 的 #[skill] 宏注解属性。
    """
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = "XiaoMeng"

    risk: SkillRisk = SkillRisk.READ_ONLY
    permission: SkillPermission = field(default_factory=SkillPermission)

    tags: List[str] = field(default_factory=list)
    emoji: str = ""

    enabled: bool = True
    always_active: bool = False   # True = 总是注入 system prompt

    body: str = ""

    source_file: str = ""

    handler: Optional[Callable] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "risk": self.risk.name,
            "risk_label": self.risk.label(),
            "min_user_level": self.permission.min_user_level.name,
            "min_model_tier": self.permission.min_model_tier.name,
            "enabled": self.enabled,
            "always_active": self.always_active,
            "tags": self.tags,
        }

    def to_tool_schema(self) -> Optional[Dict[str, Any]]:
        """如果技能注册了 handler，生成 OpenAI function-calling schema"""
        if self.handler is None:
            return None
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
