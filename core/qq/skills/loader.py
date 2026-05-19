"""
Skill 加载器

支持两种格式：
1. SKILL.md (YAML frontmatter + Markdown body) — 向后兼容现有技能文件
2. skill plugin (.py) — 可执行技能（带 handler）

基于 Harness 的 agentskills.io SKILL.md 规范 + proc-macro 注册模式。
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .definition import ModelTier, SkillDefinition, SkillPermission, SkillRisk, UserLevel

logger = logging.getLogger(__name__)


class SkillLoader:
    """从文件系统加载技能定义"""

    def __init__(self, skills_dir: str):
        self._skills_dir = Path(skills_dir)
        self._loaded: set[str] = set()

    def load_all(self) -> List[SkillDefinition]:
        """扫描 skills 目录，加载所有技能"""
        if not self._skills_dir.exists():
            return []

        skills: List[SkillDefinition] = []
        self._loaded.clear()

        for item in sorted(self._skills_dir.iterdir()):
            if item.is_file() and item.suffix == ".md":
                skill = self._load_skill_md(item)
                if skill:
                    skills.append(skill)
                    self._loaded.add(skill.name)
            elif item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    skill = self._load_skill_md(skill_md)
                    if skill:
                        skills.append(skill)
                        self._loaded.add(skill.name)

        return skills

    def load_single(self, path: str) -> Optional[SkillDefinition]:
        """加载单个技能文件"""
        full_path = self._skills_dir / path
        if not full_path.exists():
            full_path = Path(path)
        if full_path.is_dir():
            full_path = full_path / "SKILL.md"
        if full_path.exists() and full_path.suffix == ".md":
            return self._load_skill_md(full_path)
        return None

    def _load_skill_md(self, md_file: Path) -> Optional[SkillDefinition]:
        """解析 SKILL.md 文件"""
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"读取技能文件失败 {md_file}: {e}")
            return None

        frontmatter, body = self._parse_frontmatter(text)
        stem = md_file.stem
        if stem == "SKILL":
            stem = md_file.parent.name

        name = frontmatter.get("name", stem)
        desc = frontmatter.get("description", "")
        version = frontmatter.get("version", "1.0.0")
        author = frontmatter.get("author", "XiaoMeng")
        emoji = frontmatter.get("emoji", "")

        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        if not isinstance(tags, list):
            tags = []

        always = frontmatter.get("always", False)

        risk = self._parse_risk(frontmatter.get("risk", "read_only"))
        permission = self._parse_permission(frontmatter)

        return SkillDefinition(
            name=name,
            description=desc,
            version=version,
            author=author,
            risk=risk,
            permission=permission,
            tags=tags,
            emoji=emoji,
            always_active=always,
            body=body.strip(),
            source_file=str(md_file),
        )

    @staticmethod
    def _parse_frontmatter(text: str) -> Tuple[dict, str]:
        """提取 YAML frontmatter 和正文"""
        m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
        if not m:
            return {}, text.strip()

        fm_text = m.group(1)
        body = text[m.end():].strip()

        data = {}
        for line in fm_text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if key == "tags":
                    if value.startswith("[") and value.endswith("]"):
                        value = [t.strip().strip("'\"") for t in value[1:-1].split(",") if t.strip()]
                    elif value.startswith("-"):
                        pass
                elif value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                data[key] = value

        return data, body

    @staticmethod
    def _parse_risk(raw: str) -> SkillRisk:
        """解析风险等级字符串"""
        mapping = {
            "read_only": SkillRisk.READ_ONLY,
            "read-only": SkillRisk.READ_ONLY,
            "sensitive":  SkillRisk.SENSITIVE,
            "dangerous": SkillRisk.DANGEROUS,
            "0": SkillRisk.READ_ONLY,
            "1": SkillRisk.SENSITIVE,
            "2": SkillRisk.DANGEROUS,
        }
        return mapping.get(str(raw).lower().strip(), SkillRisk.READ_ONLY)

    @staticmethod
    def _parse_permission(frontmatter: dict) -> SkillPermission:
        """从 frontmatter 解析权限配置"""
        min_user = UserLevel.STRANGER
        min_model = ModelTier.LOCAL
        allowed = []

        perm_cfg = frontmatter.get("permission", {})
        if isinstance(perm_cfg, dict):
            user_str = str(perm_cfg.get("min_user_level", "stranger")).upper()
            model_str = str(perm_cfg.get("min_model_tier", "local")).upper()

            user_map = {"STRANGER": UserLevel.STRANGER, "ADMIN": UserLevel.ADMIN, "OWNER": UserLevel.OWNER}
            model_map = {"LOCAL": ModelTier.LOCAL, "CLOUD": ModelTier.CLOUD, "PRO": ModelTier.PRO}

            min_user = user_map.get(user_str, UserLevel.STRANGER)
            min_model = model_map.get(model_str, ModelTier.LOCAL)
            raw_allowed = perm_cfg.get("allowed_identities", [])
            if isinstance(raw_allowed, list):
                allowed = raw_allowed
        else:
            min_user_str = str(frontmatter.get("min_user_level", "stranger")).upper()
            min_model_str = str(frontmatter.get("min_model_tier", "local")).upper()

            user_map = {"STRANGER": UserLevel.STRANGER, "ADMIN": UserLevel.ADMIN, "OWNER": UserLevel.OWNER}
            model_map = {"LOCAL": ModelTier.LOCAL, "CLOUD": ModelTier.CLOUD, "PRO": ModelTier.PRO}

            min_user = user_map.get(min_user_str, UserLevel.STRANGER)
            min_model = model_map.get(min_model_str, ModelTier.LOCAL)

        return SkillPermission(
            min_user_level=min_user,
            min_model_tier=min_model,
            allowed_identities=allowed,
        )


def skill(
    name: str = "",
    description: str = "",
    risk: str = "read_only",
    min_user_level: str = "stranger",
    min_model_tier: str = "local",
    always_active: bool = False,
    tags: list = None,
):
    """技能注册装饰器

    类比 Harness 的 #[skill] proc-macro：
    ```rust
    #[harness::skill(name = "polite-hello", risk = "read-only")]
    async fn polite_hello(ctx, world) -> Result<(), SkillError> { ... }
    ```

    用法：
    ```python
    @skill(name="my-skill", risk="sensitive", min_user_level="admin")
    async def my_skill(ctx: SkillContext) -> str:
        return "done"
    ```
    """
    from .registry import SkillRegistry

    def decorator(func):
        risk_enum = SkillLoader._parse_risk(risk)
        user_map = {"stranger": UserLevel.STRANGER, "admin": UserLevel.ADMIN, "owner": UserLevel.OWNER}
        model_map = {"local": ModelTier.LOCAL, "cloud": ModelTier.CLOUD, "pro": ModelTier.PRO}

        skill_def = SkillDefinition(
            name=name or func.__name__,
            description=description or (func.__doc__ or "").strip().split("\n")[0],
            risk=risk_enum,
            permission=SkillPermission(
                min_user_level=user_map.get(min_user_level.lower(), UserLevel.STRANGER),
                min_model_tier=model_map.get(min_model_tier.lower(), ModelTier.LOCAL),
            ),
            always_active=always_active,
            tags=tags or [],
            handler=func,
        )
        SkillRegistry.get_instance().register(skill_def)
        return func

    return decorator
