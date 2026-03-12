"""
XiaoMengCore 技能加载器
完全参考 OpenClaw src/agents/skills/workspace.ts 实现

实现：
1. 6级优先级加载：extra < bundled < managed < agents-skills-personal < agents-skills-project < workspace
2. 完整的资格检查：OS、依赖、配置
3. 技能过滤和限制
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Callable, Set
from pathlib import Path
import platform
import os
import shutil
import re

from .skills_types import (
    Skill, SkillEntry, SkillMetadata, SkillRequires,
    SkillInvocationPolicy, SkillSnapshot, SkillEligibilityContext
)


DEFAULT_MAX_CANDIDATES_PER_ROOT = 300
DEFAULT_MAX_SKILLS_LOADED_PER_SOURCE = 200
DEFAULT_MAX_SKILLS_IN_PROMPT = 150
DEFAULT_MAX_SKILLS_PROMPT_CHARS = 30000
DEFAULT_MAX_SKILL_FILE_BYTES = 256000


@dataclass
class SkillsLimits:
    """技能加载限制"""
    max_candidates_per_root: int = DEFAULT_MAX_CANDIDATES_PER_ROOT
    max_skills_loaded_per_source: int = DEFAULT_MAX_SKILLS_LOADED_PER_SOURCE
    max_skills_in_prompt: int = DEFAULT_MAX_SKILLS_IN_PROMPT
    max_skills_prompt_chars: int = DEFAULT_MAX_SKILLS_PROMPT_CHARS
    max_skill_file_bytes: int = DEFAULT_MAX_SKILL_FILE_BYTES


def resolve_runtime_platform() -> str:
    """获取当前运行平台"""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system


def has_binary(bin_name: str) -> bool:
    """检查二进制文件是否可用"""
    return shutil.which(bin_name) is not None


def has_env(env_name: str) -> bool:
    """检查环境变量是否设置"""
    return os.environ.get(env_name) is not None


def list_child_directories(dir_path: Path) -> List[str]:
    """列出子目录"""
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    
    dirs = []
    try:
        for entry in dir_path.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.name == "node_modules":
                continue
            if entry.is_dir():
                dirs.append(entry.name)
            elif entry.is_symlink():
                try:
                    if entry.resolve().is_dir():
                        dirs.append(entry.name)
                except:
                    pass
    except:
        pass
    
    return dirs


def compact_skill_paths(skills: List[Skill]) -> List[Skill]:
    """压缩技能路径，用~替换home目录"""
    home = Path.home()
    if not home:
        return skills
    
    prefix = str(home)
    if not prefix.endswith(os.sep):
        prefix += os.sep
    
    result = []
    for skill in skills:
        if skill.skill_path and skill.skill_path.startswith(prefix):
            new_path = "~/" + skill.skill_path[len(prefix):]
            new_skill = Skill(
                metadata=skill.metadata,
                content=skill.content,
                examples=skill.examples,
                instructions=skill.instructions,
                skill_path=new_path,
                invocation=skill.invocation,
                commands=skill.commands
            )
            result.append(new_skill)
        else:
            result.append(skill)
    
    return result


def evaluate_runtime_requires(
    requires: Optional[SkillRequires],
    has_bin: Callable[[str], bool] = has_binary,
    has_env_func: Callable[[str], bool] = has_env,
    is_config_truthy: Callable[[str], bool] = lambda x: True
) -> bool:
    """评估运行时依赖要求"""
    if not requires:
        return True
    
    if requires.bins:
        for bin_name in requires.bins:
            if not has_bin(bin_name):
                return False
    
    if requires.any_bins:
        if not any(has_bin(b) for b in requires.any_bins):
            return False
    
    if requires.env:
        for env_name in requires.env:
            if not has_env_func(env_name):
                return False
    
    if requires.config:
        for config_path in requires.config:
            if not is_config_truthy(config_path):
                return False
    
    return True


def should_include_skill(
    entry: SkillEntry,
    config: Optional[Dict] = None,
    eligibility: Optional[SkillEligibilityContext] = None,
    skill_config: Optional[Dict] = None,
    allow_bundled: Optional[List[str]] = None
) -> bool:
    """
    判断技能是否应该被包含 - 参考 OpenClaw shouldIncludeSkill
    
    检查：
    1. 配置是否启用
    2. OS兼容性
    3. 依赖要求
    4. always标记
    """
    if skill_config and skill_config.get("enabled") is False:
        return False
    
    os_list = entry.metadata.os if entry.metadata else []
    current_os = resolve_runtime_platform()
    remote_platforms = eligibility.remote.platforms if eligibility and eligibility.remote else []
    
    if os_list:
        os_compatible = current_os in [o.lower() for o in os_list]
        remote_compatible = any(p.lower() in [o.lower() for o in os_list] for p in remote_platforms)
        if not os_compatible and not remote_compatible:
            return False
    
    if entry.metadata and entry.metadata.always is True:
        return True
    
    requires = entry.metadata.requires if entry.metadata else None
    return evaluate_runtime_requires(
        requires=requires,
        has_bin=has_binary if not eligibility or not eligibility.remote else eligibility.remote.has_bin,
        has_env_func=has_env,
    )


def filter_skill_entries(
    entries: List[SkillEntry],
    config: Optional[Dict] = None,
    skill_filter: Optional[List[str]] = None,
    eligibility: Optional[SkillEligibilityContext] = None
) -> List[SkillEntry]:
    """过滤技能条目"""
    filtered = [
        entry for entry in entries
        if should_include_skill(entry, config, eligibility)
    ]
    
    if skill_filter is not None:
        normalized = [f.lower().strip() for f in skill_filter if f.strip()]
        if normalized:
            filtered = [
                entry for entry in filtered
                if entry.skill.metadata.name.lower() in normalized
            ]
        else:
            filtered = []
    
    return filtered


class SkillLoader:
    """
    技能加载器 - 完全参考 OpenClaw workspace.ts
    
    实现6级优先级加载：
    1. extra - 额外目录
    2. bundled - 内置技能
    3. managed - 托管技能
    4. agents-skills-personal - 个人Agents技能
    5. agents-skills-project - 项目Agents技能
    6. workspace - 工作区技能（最高优先级）
    """
    
    def __init__(
        self,
        workspace_dir: str = "./workspace",
        config: Optional[Dict] = None,
        limits: Optional[SkillsLimits] = None
    ):
        self._workspace_dir = Path(workspace_dir)
        self._config = config or {}
        self._limits = limits or SkillsLimits()
        self._skills: Dict[str, Skill] = {}
        self._skill_entries: Dict[str, SkillEntry] = {}
    
    def _load_skills_from_dir(
        self,
        dir_path: Path,
        source: str
    ) -> List[Skill]:
        """从目录加载技能"""
        if not dir_path.exists():
            return []
        
        skills = []
        
        root_skill_md = dir_path / "SKILL.md"
        if root_skill_md.exists():
            try:
                size = root_skill_md.stat().st_size
                if size <= self._limits.max_skill_file_bytes:
                    skill = Skill.from_file(str(root_skill_md))
                    skills.append(skill)
            except:
                pass
        
        child_dirs = list_child_directories(dir_path)
        if len(child_dirs) > self._limits.max_candidates_per_root:
            child_dirs = sorted(child_dirs)[:self._limits.max_skills_loaded_per_source]
        
        for name in child_dirs:
            if len(skills) >= self._limits.max_skills_loaded_per_source:
                break
            
            skill_dir = dir_path / name
            skill_md = skill_dir / "SKILL.md"
            
            if not skill_md.exists():
                continue
            
            try:
                size = skill_md.stat().st_size
                if size > self._limits.max_skill_file_bytes:
                    continue
                
                skill = Skill.from_file(str(skill_md))
                skills.append(skill)
            except:
                pass
        
        return skills
    
    def load_all_skills(
        self,
        extra_dirs: Optional[List[str]] = None,
        bundled_dir: Optional[str] = None,
        managed_dir: Optional[str] = None
    ) -> Dict[str, Skill]:
        """
        加载所有技能 - 实现6级优先级
        
        优先级：extra < bundled < managed < agents-skills-personal < agents-skills-project < workspace
        """
        merged: Dict[str, Skill] = {}
        
        extra_skills = []
        for dir_path in (extra_dirs or []):
            path = Path(dir_path).expanduser().resolve()
            extra_skills.extend(self._load_skills_from_dir(path, "extra"))
        for skill in extra_skills:
            merged[skill.metadata.name] = skill
        
        if bundled_dir:
            path = Path(bundled_dir).expanduser().resolve()
            bundled_skills = self._load_skills_from_dir(path, "bundled")
            for skill in bundled_skills:
                merged[skill.metadata.name] = skill
        
        if managed_dir:
            path = Path(managed_dir).expanduser().resolve()
            managed_skills = self._load_skills_from_dir(path, "managed")
            for skill in managed_skills:
                merged[skill.metadata.name] = skill
        
        personal_agents_dir = Path.home() / ".agents" / "skills"
        personal_skills = self._load_skills_from_dir(personal_agents_dir, "agents-skills-personal")
        for skill in personal_skills:
            merged[skill.metadata.name] = skill
        
        project_agents_dir = self._workspace_dir / ".agents" / "skills"
        project_skills = self._load_skills_from_dir(project_agents_dir, "agents-skills-project")
        for skill in project_skills:
            merged[skill.metadata.name] = skill
        
        workspace_skills_dir = self._workspace_dir / "skills"
        workspace_skills = self._load_skills_from_dir(workspace_skills_dir, "workspace")
        for skill in workspace_skills:
            merged[skill.metadata.name] = skill
        
        self._skills = merged
        self._build_skill_entries()
        
        return merged
    
    def _build_skill_entries(self):
        """构建技能条目"""
        self._skill_entries = {}
        for name, skill in self._skills.items():
            frontmatter = Skill._parse_frontmatter(skill.content) if skill.content else {}
            self._skill_entries[name] = SkillEntry(
                skill=skill,
                frontmatter=frontmatter,
                metadata=skill.metadata,
                invocation=skill.invocation
            )
    
    def get_eligible_skills(
        self,
        skill_filter: Optional[List[str]] = None,
        eligibility: Optional[SkillEligibilityContext] = None
    ) -> List[SkillEntry]:
        """获取符合条件的技能"""
        entries = list(self._skill_entries.values())
        return filter_skill_entries(entries, self._config, skill_filter, eligibility)
    
    def apply_prompt_limits(
        self,
        skills: List[Skill]
    ) -> tuple[List[Skill], bool]:
        """应用提示限制"""
        total = len(skills)
        by_count = skills[:self._limits.max_skills_in_prompt]
        
        skills_for_prompt = by_count
        truncated = total > len(by_count)
        
        def fits(skill_list: List[Skill]) -> bool:
            prompt = self._format_skills_for_prompt(skill_list)
            return len(prompt) <= self._limits.max_skills_prompt_chars
        
        if not fits(skills_for_prompt):
            lo, hi = 0, len(skills_for_prompt)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if fits(skills_for_prompt[:mid]):
                    lo = mid
                else:
                    hi = mid - 1
            skills_for_prompt = skills_for_prompt[:lo]
            truncated = True
        
        return skills_for_prompt, truncated
    
    def _format_skills_for_prompt(self, skills: List[Skill]) -> str:
        """格式化技能为提示"""
        lines = []
        for skill in compact_skill_paths(skills):
            lines.append("<available_skills>")
            lines.append("  <skill>")
            lines.append(f"    <name>{skill.metadata.name}</name>")
            if skill.metadata.emoji:
                lines.append(f"    <emoji>{skill.metadata.emoji}</emoji>")
            if skill.metadata.description:
                lines.append(f"    <description>{skill.metadata.description}</description>")
            if skill.skill_path:
                lines.append(f"    <location>{skill.skill_path}</location>")
            lines.append("  </skill>")
            lines.append("</available_skills>")
        return "\n".join(lines)
    
    def build_skills_prompt(
        self,
        skill_filter: Optional[List[str]] = None,
        eligibility: Optional[SkillEligibilityContext] = None
    ) -> str:
        """构建技能提示"""
        eligible = self.get_eligible_skills(skill_filter, eligibility)
        
        prompt_entries = [
            entry for entry in eligible
            if not (entry.invocation and entry.invocation.disable_model_invocation)
        ]
        
        resolved_skills = [entry.skill for entry in prompt_entries]
        skills_for_prompt, truncated = self.apply_prompt_limits(resolved_skills)
        
        truncation_note = ""
        if truncated:
            truncation_note = f"⚠️ Skills truncated: included {len(skills_for_prompt)} of {len(resolved_skills)}.\n"
        
        remote_note = ""
        if eligibility and eligibility.remote and eligibility.remote.note:
            remote_note = eligibility.remote.note + "\n"
        
        return remote_note + truncation_note + self._format_skills_for_prompt(skills_for_prompt)
    
    def build_skill_snapshot(
        self,
        skill_filter: Optional[List[str]] = None,
        eligibility: Optional[SkillEligibilityContext] = None,
        version: Optional[int] = None
    ) -> SkillSnapshot:
        """构建技能快照"""
        eligible = self.get_eligible_skills(skill_filter, eligibility)
        prompt = self.build_skills_prompt(skill_filter, eligibility)
        
        skills_info = [
            {
                "name": entry.skill.metadata.name,
                "primaryEnv": entry.metadata.primary_env if entry.metadata else None
            }
            for entry in eligible
        ]
        
        resolved_skills = [entry.skill for entry in eligible]
        
        return SkillSnapshot(
            prompt=prompt,
            skills=skills_info,
            skill_filter=skill_filter,
            resolved_skills=resolved_skills,
            version=version
        )
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self._skills.get(name)
    
    def get_skill_entry(self, name: str) -> Optional[SkillEntry]:
        """获取技能条目"""
        return self._skill_entries.get(name)
    
    def get_all_skills(self) -> List[Skill]:
        """获取所有技能"""
        return list(self._skills.values())
    
    def get_all_skill_entries(self) -> List[SkillEntry]:
        """获取所有技能条目"""
        return list(self._skill_entries.values())
    
    def register_skill(self, skill: Skill):
        """注册技能"""
        self._skills[skill.metadata.name] = skill
        frontmatter = Skill._parse_frontmatter(skill.content) if skill.content else {}
        self._skill_entries[skill.metadata.name] = SkillEntry(
            skill=skill,
            frontmatter=frontmatter,
            metadata=skill.metadata,
            invocation=skill.invocation
        )
    
    def create_skill(
        self,
        name: str,
        description: str,
        instructions: str,
        examples: List[Dict[str, str]] = None,
        skill_key: str = None,
        emoji: str = None,
        requires: Dict = None,
        install: List[Dict] = None
    ) -> Skill:
        """创建新技能"""
        workspace_skills_dir = self._workspace_dir / "skills" / name
        workspace_skills_dir.mkdir(parents=True, exist_ok=True)
        
        skill = Skill(
            metadata=SkillMetadata(
                name=name,
                description=description,
                skill_key=skill_key or name,
                emoji=emoji,
            ),
            content="",
            examples=[],
            instructions=instructions
        )
        
        skill_content = skill.to_openclaw_format()
        skill_file = workspace_skills_dir / "SKILL.md"
        skill_file.write_text(skill_content, encoding='utf-8')
        
        skill.content = skill_content
        skill.skill_path = str(skill_file)
        self.register_skill(skill)
        
        return skill
    
    def delete_skill(self, name: str) -> bool:
        """删除技能"""
        if name not in self._skills:
            return False
        
        skill = self._skills[name]
        skill_dir = Path(skill.skill_path).parent if skill.skill_path else None
        
        if skill_dir and skill_dir.exists():
            shutil.rmtree(skill_dir)
        
        del self._skills[name]
        if name in self._skill_entries:
            del self._skill_entries[name]
        
        return True
