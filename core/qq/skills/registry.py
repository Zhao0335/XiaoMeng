"""
Skill 注册中心

基于 Harness 的 Registry-based dispatch 模式：
- 单一注册中心（Singleton）
- 统一的技能发现、验证、启用/禁用
- 运行时热加载
- 技能生命周期管理

类比 Harness 的 SkillRegistry::with_macro_skills() +
harness skills validate / list / export CLI。
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .definition import (
    ModelTier, SkillDefinition, SkillPermission, SkillRisk, UserLevel,
)
from .loader import SkillLoader
from .permissions import SkillPermissionChecker

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册中心

    单例模式，全局唯一的技能管理中心。
    """

    _instance: Optional["SkillRegistry"] = None

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}
        self._loader: Optional[SkillLoader] = None
        self._perm_checker = SkillPermissionChecker()

    @classmethod
    def get_instance(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def init_loader(self, skills_dir: str) -> "SkillRegistry":
        """初始化文件加载器并加载所有文件定义技能"""
        self._loader = SkillLoader(skills_dir)
        file_skills = self._loader.load_all()
        for skill in file_skills:
            self.register(skill, override=False)
        logger.info(f"SkillRegistry: 从 {skills_dir} 加载了 {len(file_skills)} 个文件技能")
        return self

    def register(self, skill: SkillDefinition, override: bool = True) -> bool:
        """注册技能"""
        if skill.name in self._skills and not override:
            logger.debug(f"技能 {skill.name} 已存在，跳过注册")
            return False
        self._skills[skill.name] = skill
        logger.info(f"SkillRegistry: 注册技能 {skill.name} (risk={skill.risk.name}, user_level={skill.permission.min_user_level.name})")
        return True

    def unregister(self, name: str) -> bool:
        """注销技能"""
        if name in self._skills:
            del self._skills[name]
            logger.info(f"SkillRegistry: 注销技能 {name}")
            return True
        return False

    def get(self, name: str) -> Optional[SkillDefinition]:
        """获取技能定义"""
        return self._skills.get(name)

    def list_all(self) -> List[SkillDefinition]:
        """列出所有已注册技能"""
        return list(self._skills.values())

    def list_enabled(self) -> List[SkillDefinition]:
        """列出所有已启用的技能"""
        return [s for s in self._skills.values() if s.enabled]

    def enable(self, name: str) -> bool:
        """启用技能"""
        skill = self._skills.get(name)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用技能"""
        skill = self._skills.get(name)
        if skill:
            skill.enabled = False
            return True
        return False

    def reload(self) -> int:
        """从文件系统重新加载所有技能"""
        if self._loader is None:
            return 0
        file_skills = self._loader.load_all()
        for skill in file_skills:
            self.register(skill, override=True)
        logger.info(f"SkillRegistry: 重新加载了 {len(file_skills)} 个技能")
        return len(file_skills)

    def get_for_context(
        self,
        model_tier: ModelTier,
        user_level: UserLevel,
        identity: str = "",
    ) -> List[SkillDefinition]:
        """获取当前上下文（模型层级+用户级别+身份）可用的技能列表

        这是权限控制的核心入口。

        硬规则：Skill 是给 CLOUD/PRO 模型用的——本地小模型（LOCAL）不加载任何技能，
        避免占用上下文、干扰推理。基础工具（web_search/add_memory 等）已有独立的层级过滤。
        """
        if model_tier >= ModelTier.CLOUD:
            enabled = self.list_enabled()
            return self._perm_checker.filter_skills(enabled, model_tier, user_level, identity)
        return []

    def get_active_prompt_skills(
        self,
        model_tier: ModelTier,
        user_level: UserLevel,
        identity: str = "",
    ) -> List[SkillDefinition]:
        """获取应注入 system prompt 的技能（always_active=True 且有权限）"""
        available = self.get_for_context(model_tier, user_level, identity)
        return [s for s in available if s.always_active]

    def validate(self, name: str) -> Optional[str]:
        """验证技能定义的完整性

        类比 Harness 的 harness skills validate 命令。
        """
        skill = self._skills.get(name)
        if skill is None:
            return f"技能 {name} 未注册"
        issues = []
        if not skill.name:
            issues.append("缺少名称")
        if not skill.body and skill.handler is None:
            issues.append("缺少正文或 handler")
        return "; ".join(issues) if issues else None

    def validate_all(self) -> Dict[str, Optional[str]]:
        """验证所有技能，返回 {skill_name: error_or_none}"""
        return {name: self.validate(name) for name in self._skills}

    def to_summary(self) -> List[Dict]:
        """导出所有技能摘要（用于 CLI /status 等）"""
        return [s.to_summary() for s in self._skills.values()]

    @property
    def count(self) -> int:
        return len(self._skills)

    @property
    def enabled_count(self) -> int:
        return len(self.list_enabled())

    def __len__(self) -> int:
        return self.count

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __iter__(self):
        return iter(self._skills.values())
