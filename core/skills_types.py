"""
XiaoMengCore 技能类型定义
完全参考 OpenClaw src/agents/skills/types.ts
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Callable, Literal


@dataclass
class SkillRequires:
    """技能依赖要求"""
    bins: List[str] = field(default_factory=list)
    any_bins: List[str] = field(default_factory=list)
    env: List[str] = field(default_factory=list)
    config: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "bins": self.bins,
            "anyBins": self.any_bins,
            "env": self.env,
            "config": self.config
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillRequires":
        if not data:
            return cls()
        return cls(
            bins=data.get("bins", []),
            any_bins=data.get("anyBins", []),
            env=data.get("env", []),
            config=data.get("config", [])
        )


@dataclass
class SkillInstallSpec:
    """技能安装规范"""
    kind: Literal["brew", "node", "go", "uv", "download"]
    id: Optional[str] = None
    label: Optional[str] = None
    bins: List[str] = field(default_factory=list)
    os: List[str] = field(default_factory=list)
    formula: Optional[str] = None
    package: Optional[str] = None
    module: Optional[str] = None
    url: Optional[str] = None
    archive: Optional[str] = None
    extract: Optional[bool] = None
    strip_components: Optional[int] = None
    target_dir: Optional[str] = None


@dataclass
class SkillMetadata:
    """技能元数据"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    always: Optional[bool] = None
    skill_key: Optional[str] = None
    primary_env: Optional[str] = None
    emoji: Optional[str] = None
    homepage: Optional[str] = None
    os: List[str] = field(default_factory=list)
    requires: Optional[SkillRequires] = None
    install: List[SkillInstallSpec] = field(default_factory=list)


@dataclass
class SkillInvocationPolicy:
    """技能调用策略"""
    user_invocable: bool = True
    disable_model_invocation: bool = False


@dataclass
class SkillCommandSpec:
    """技能命令规范"""
    name: str
    skill_name: str
    description: str


@dataclass
class SkillExample:
    """技能示例"""
    user_request: str
    command: str
    explanation: str = ""


@dataclass
class Skill:
    """技能定义"""
    metadata: SkillMetadata
    content: str
    examples: List[SkillExample] = field(default_factory=list)
    instructions: str = ""
    skill_path: str = ""
    invocation: SkillInvocationPolicy = field(default_factory=SkillInvocationPolicy)
    commands: List[SkillCommandSpec] = field(default_factory=list)
    
    @staticmethod
    def _parse_frontmatter(content: str) -> Dict:
        """解析frontmatter"""
        import re
        import yaml
        
        pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(pattern, content, re.DOTALL)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except:
                pass
        return {}
    
    @classmethod
    def from_file(cls, file_path: str) -> "Skill":
        """从文件加载技能"""
        from pathlib import Path
        import re
        import yaml
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"技能文件不存在: {file_path}")
        
        content = path.read_text(encoding='utf-8')
        
        frontmatter = {}
        pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(pattern, content, re.DOTALL)
        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
            except:
                pass
        
        metadata = SkillMetadata(
            name=frontmatter.get("name", "unnamed"),
            description=frontmatter.get("description", ""),
            version=frontmatter.get("version", "1.0.0"),
            author=frontmatter.get("author", ""),
            tags=frontmatter.get("tags", []),
            always=frontmatter.get("always"),
            skill_key=frontmatter.get("skillKey"),
            primary_env=frontmatter.get("primaryEnv"),
            emoji=frontmatter.get("emoji"),
            homepage=frontmatter.get("homepage"),
            os=frontmatter.get("os", []),
        )
        
        requires_data = frontmatter.get("requires", {})
        if requires_data:
            metadata.requires = SkillRequires.from_dict(requires_data)
        
        invocation = SkillInvocationPolicy(
            user_invocable=frontmatter.get("user-invocable", True),
            disable_model_invocation=frontmatter.get("disable-model-invocation", False)
        )
        
        return cls(
            metadata=metadata,
            content=content,
            instructions="",
            skill_path=str(path),
            invocation=invocation
        )
    
    def to_openclaw_format(self) -> str:
        """转换为OpenClaw格式"""
        lines = ["---"]
        lines.append(f"name: {self.metadata.name}")
        if self.metadata.description:
            lines.append(f"description: {self.metadata.description}")
        if self.metadata.version != "1.0.0":
            lines.append(f"version: {self.metadata.version}")
        if self.metadata.author:
            lines.append(f"author: {self.metadata.author}")
        if self.metadata.always is not None:
            lines.append(f"always: {self.metadata.always}")
        if self.metadata.skill_key:
            lines.append(f"skillKey: {self.metadata.skill_key}")
        if self.metadata.primary_env:
            lines.append(f"primaryEnv: {self.metadata.primary_env}")
        if self.metadata.emoji:
            lines.append(f"emoji: {self.metadata.emoji}")
        if self.metadata.homepage:
            lines.append(f"homepage: {self.metadata.homepage}")
        if self.metadata.os:
            lines.append(f"os: {self.metadata.os}")
        if not self.invocation.user_invocable:
            lines.append(f"user-invocable: {self.invocation.user_invocable}")
        if self.invocation.disable_model_invocation:
            lines.append(f"disable-model-invocation: {self.invocation.disable_model_invocation}")
        lines.append("---")
        lines.append("")
        
        if self.metadata.description:
            lines.append(f"# {self.metadata.name}")
            lines.append("")
            lines.append(self.metadata.description)
            lines.append("")
        
        if self.instructions:
            lines.append("## 使用说明")
            lines.append("")
            lines.append(self.instructions)
            lines.append("")
        
        return "\n".join(lines)


@dataclass
class SkillEntry:
    """技能条目"""
    skill: Skill
    frontmatter: Dict
    metadata: Optional[SkillMetadata] = None
    invocation: Optional[SkillInvocationPolicy] = None


@dataclass
class RemoteEligibility:
    """远程资格"""
    platforms: List[str] = field(default_factory=list)
    has_bin: Callable[[str], bool] = lambda x: False
    has_any_bin: Callable[[List[str]], bool] = lambda x: False
    note: Optional[str] = None


@dataclass
class SkillEligibilityContext:
    """技能资格上下文"""
    remote: Optional[RemoteEligibility] = None


@dataclass
class SkillSnapshot:
    """技能快照"""
    prompt: str
    skills: List[Dict[str, Any]] = field(default_factory=list)
    skill_filter: Optional[List[str]] = None
    resolved_skills: List[Skill] = field(default_factory=list)
    version: Optional[int] = None
