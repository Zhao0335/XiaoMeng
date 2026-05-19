"""
Skill 权限检查器

基于 Harness 的 Governance + RBAC 设计：
- 三重判断：ModelTier + UserLevel + Identity
- 支持白名单机制
- 类型安全的权限断言
"""

from .definition import ModelTier, SkillDefinition, SkillRisk, UserLevel


class SkillPermissionChecker:
    """技能权限检查器

    类比 Harness 的 OPA Policy Gates + RBAC 层次。
    """

    def __init__(self):
        self._identity_whitelist: dict[str, set[str]] = {}

    def add_identity_whitelist(self, skill_name: str, identities: list[str]):
        existing = self._identity_whitelist.setdefault(skill_name, set())
        existing.update(identities)

    def can_use(
        self,
        skill: SkillDefinition,
        model_tier: ModelTier,
        user_level: UserLevel,
        identity: str = "",
    ) -> bool:
        if not skill.enabled:
            return False

        if not skill.permission.allows_model(model_tier):
            return False

        if not skill.permission.allows_user(user_level, identity):
            return False

        return True

    def filter_skills(
        self,
        skills: list[SkillDefinition],
        model_tier: ModelTier,
        user_level: UserLevel,
        identity: str = "",
    ) -> list[SkillDefinition]:
        return [
            s for s in skills
            if self.can_use(s, model_tier, user_level, identity)
        ]

    def can_use_risk(
        self,
        risk: SkillRisk,
        model_tier: ModelTier,
        user_level: UserLevel,
    ) -> bool:
        """快速检查某个风险级别的技能是否可用（不依赖具体 SkillDefinition）"""
        DEFAULT_RISK_MODEL_MIN = {
            SkillRisk.READ_ONLY: ModelTier.LOCAL,
            SkillRisk.SENSITIVE:  ModelTier.CLOUD,
            SkillRisk.DANGEROUS: ModelTier.PRO,
        }
        min_tier = DEFAULT_RISK_MODEL_MIN.get(risk, ModelTier.PRO)
        return model_tier >= min_tier
