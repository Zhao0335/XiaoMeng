"""
XiaoMengCore 技能系统
完全兼容 OpenClaw SKILL.md 格式

参考 OpenClaw 源码：
- src/agents/skills/types.ts
- src/agents/skills/frontmatter.ts
- skills/healthcheck/SKILL.md
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Callable, Awaitable, Union, Literal
from pathlib import Path
from datetime import datetime
import re
import yaml
import asyncio
import os

from models import User, UserLevel


@dataclass
class SkillRequires:
    """
    技能依赖要求
    
    参考 OpenClaw types.ts OpenClawSkillMetadata.requires
    """
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
    """
    技能安装规范
    
    参考 OpenClaw types.ts SkillInstallSpec
    支持 brew, node, go, uv, download 五种安装方式
    """
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
    
    def to_dict(self) -> Dict:
        result = {"kind": self.kind}
        if self.id:
            result["id"] = self.id
        if self.label:
            result["label"] = self.label
        if self.bins:
            result["bins"] = self.bins
        if self.os:
            result["os"] = self.os
        if self.formula:
            result["formula"] = self.formula
        if self.package:
            result["package"] = self.package
        if self.module:
            result["module"] = self.module
        if self.url:
            result["url"] = self.url
        if self.archive:
            result["archive"] = self.archive
        if self.extract is not None:
            result["extract"] = self.extract
        if self.strip_components is not None:
            result["stripComponents"] = self.strip_components
        if self.target_dir:
            result["targetDir"] = self.target_dir
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillInstallSpec":
        return cls(
            kind=data.get("kind", "brew"),
            id=data.get("id"),
            label=data.get("label"),
            bins=data.get("bins", []),
            os=data.get("os", []),
            formula=data.get("formula"),
            package=data.get("package"),
            module=data.get("module"),
            url=data.get("url"),
            archive=data.get("archive"),
            extract=data.get("extract"),
            strip_components=data.get("stripComponents"),
            target_dir=data.get("targetDir")
        )


@dataclass
class SkillMetadata:
    """
    技能元数据 - 完全兼容 OpenClaw
    
    参考 OpenClaw types.ts OpenClawSkillMetadata
    
    基础字段：
    - name: 技能名称
    - description: 技能描述
    
    OpenClaw 扩展字段：
    - always: 是否总是加载
    - skill_key: 技能唯一标识
    - primary_env: 主要环境变量
    - emoji: 技能图标
    - homepage: 主页链接
    - os: 支持的操作系统列表
    - requires: 依赖要求
    - install: 安装规范
    """
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
    
    def to_dict(self) -> Dict:
        result = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags
        }
        if self.always is not None:
            result["always"] = self.always
        if self.skill_key:
            result["skillKey"] = self.skill_key
        if self.primary_env:
            result["primaryEnv"] = self.primary_env
        if self.emoji:
            result["emoji"] = self.emoji
        if self.homepage:
            result["homepage"] = self.homepage
        if self.os:
            result["os"] = self.os
        if self.requires:
            result["requires"] = self.requires.to_dict()
        if self.install:
            result["install"] = [i.to_dict() for i in self.install]
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillMetadata":
        requires = None
        if data.get("requires"):
            requires = SkillRequires.from_dict(data["requires"])
        
        install = []
        for inst in data.get("install", []):
            install.append(SkillInstallSpec.from_dict(inst))
        
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            always=data.get("always"),
            skill_key=data.get("skillKey"),
            primary_env=data.get("primaryEnv"),
            emoji=data.get("emoji"),
            homepage=data.get("homepage"),
            os=data.get("os", []),
            requires=requires,
            install=install
        )


@dataclass
class SkillInvocationPolicy:
    """
    技能调用策略
    
    参考 OpenClaw types.ts SkillInvocationPolicy
    """
    user_invocable: bool = True
    disable_model_invocation: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "userInvocable": self.user_invocable,
            "disableModelInvocation": self.disable_model_invocation
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillInvocationPolicy":
        return cls(
            user_invocable=data.get("userInvocable", True),
            disable_model_invocation=data.get("disableModelInvocation", False)
        )


@dataclass
class SkillCommandDispatchSpec:
    """
    技能命令调度规范
    
    参考 OpenClaw types.ts SkillCommandDispatchSpec
    """
    kind: Literal["tool"] = "tool"
    tool_name: Optional[str] = None
    arg_mode: Optional[Literal["raw"]] = None
    
    def to_dict(self) -> Dict:
        result = {"kind": self.kind}
        if self.tool_name:
            result["toolName"] = self.tool_name
        if self.arg_mode:
            result["argMode"] = self.arg_mode
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillCommandDispatchSpec":
        return cls(
            kind=data.get("kind", "tool"),
            tool_name=data.get("toolName"),
            arg_mode=data.get("argMode")
        )


@dataclass
class SkillCommandSpec:
    """
    技能命令规范
    
    参考 OpenClaw types.ts SkillCommandSpec
    """
    name: str
    skill_name: str
    description: str
    dispatch: Optional[SkillCommandDispatchSpec] = None
    
    def to_dict(self) -> Dict:
        result = {
            "name": self.name,
            "skillName": self.skill_name,
            "description": self.description
        }
        if self.dispatch:
            result["dispatch"] = self.dispatch.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillCommandSpec":
        dispatch = None
        if data.get("dispatch"):
            dispatch = SkillCommandDispatchSpec.from_dict(data["dispatch"])
        return cls(
            name=data.get("name", ""),
            skill_name=data.get("skillName", ""),
            description=data.get("description", ""),
            dispatch=dispatch
        )


@dataclass
class SkillExample:
    """技能示例"""
    user_request: str
    command: str
    explanation: str = ""


@dataclass
class Skill:
    """
    技能定义 - 完全兼容 OpenClaw SKILL.md 格式
    
    OpenClaw SKILL.md 文件结构：
    1. YAML frontmatter (元数据)
    2. 技能概述
    3. 核心规则
    4. 工作流程
    5. 使用示例
    6. 注意事项
    
    参考：
    - OpenClaw skills/healthcheck/SKILL.md
    - OpenClaw src/agents/skills/frontmatter.ts
    """
    metadata: SkillMetadata
    content: str
    examples: List[SkillExample] = field(default_factory=list)
    instructions: str = ""
    skill_path: str = ""
    invocation: SkillInvocationPolicy = field(default_factory=SkillInvocationPolicy)
    commands: List[SkillCommandSpec] = field(default_factory=list)
    
    @classmethod
    def from_markdown(cls, content: str, skill_path: str = "") -> "Skill":
        """从 SKILL.md 文件解析技能"""
        frontmatter = cls._parse_frontmatter(content)
        metadata = SkillMetadata.from_dict(frontmatter)
        invocation = cls._parse_invocation_policy(frontmatter)
        examples = cls._parse_examples(content)
        instructions = cls._parse_instructions(content)
        commands = cls._parse_commands(frontmatter)
        
        return cls(
            metadata=metadata,
            content=content,
            examples=examples,
            instructions=instructions,
            skill_path=skill_path,
            invocation=invocation,
            commands=commands
        )
    
    @classmethod
    def from_file(cls, file_path: str) -> "Skill":
        """从文件加载技能"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"技能文件不存在: {file_path}")
        
        content = path.read_text(encoding='utf-8')
        return cls.from_markdown(content, str(path))
    
    @staticmethod
    def _parse_frontmatter(content: str) -> Dict:
        """解析 YAML frontmatter"""
        pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(pattern, content, re.DOTALL)
        
        if match:
            try:
                data = yaml.safe_load(match.group(1))
                return data if data else {}
            except yaml.YAMLError:
                pass
        
        return {}
    
    @staticmethod
    def _parse_invocation_policy(frontmatter: Dict) -> SkillInvocationPolicy:
        """解析调用策略"""
        return SkillInvocationPolicy(
            user_invocable=frontmatter.get("user-invocable", True),
            disable_model_invocation=frontmatter.get("disable-model-invocation", False)
        )
    
    @staticmethod
    def _parse_commands(frontmatter: Dict) -> List[SkillCommandSpec]:
        """解析命令规范"""
        commands = []
        cmd_data = frontmatter.get("commands", {})
        
        if isinstance(cmd_data, dict):
            for cmd_name, cmd_info in cmd_data.items():
                if isinstance(cmd_info, str):
                    commands.append(SkillCommandSpec(
                        name=cmd_name,
                        skill_name=frontmatter.get("name", ""),
                        description=cmd_info
                    ))
                elif isinstance(cmd_info, dict):
                    dispatch = None
                    if cmd_info.get("dispatch"):
                        dispatch = SkillCommandDispatchSpec.from_dict(cmd_info["dispatch"])
                    commands.append(SkillCommandSpec(
                        name=cmd_name,
                        skill_name=frontmatter.get("name", ""),
                        description=cmd_info.get("description", ""),
                        dispatch=dispatch
                    ))
        
        return commands
    
    @staticmethod
    def _parse_examples(content: str) -> List[SkillExample]:
        """解析示例"""
        examples = []
        
        context_pattern = r"(?:用户请求|User request|Example)[:：]\s*「?([^「\n]+)」?"
        
        lines = content.split('\n')
        current_context = ""
        in_code_block = False
        code_lines = []
        
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                if in_code_block:
                    if code_lines:
                        examples.append(SkillExample(
                            user_request=current_context,
                            command="\n".join(code_lines),
                            explanation=""
                        ))
                        current_context = ""
                        code_lines = []
                    in_code_block = False
                else:
                    in_code_block = True
            elif in_code_block:
                code_lines.append(line)
            else:
                context_match = re.match(context_pattern, line, re.IGNORECASE)
                if context_match:
                    current_context = context_match.group(1).strip()
        
        return examples
    
    @staticmethod
    def _parse_instructions(content: str) -> str:
        """解析使用说明"""
        lines = content.split('\n')
        instructions = []
        in_section = False
        current_section = ""
        
        for line in lines:
            header_match = re.match(r"^#+\s*(.+)", line)
            if header_match:
                header = header_match.group(1).lower()
                if any(kw in header for kw in ["使用说明", "instructions", "how to use", "overview", "概述", "workflow", "工作流程", "core rules", "核心规则"]):
                    in_section = True
                    current_section = header_match.group(1)
                    continue
                elif in_section and not any(kw in header for kw in ["example", "示例", "required", "required confirmations", "logging", "memory"]):
                    pass
                else:
                    in_section = False
            
            if in_section:
                instructions.append(line)
        
        return "\n".join(instructions).strip()
    
    def to_prompt(self) -> str:
        """转换为 LLM 提示"""
        parts = [f"# 技能: {self.metadata.name}"]
        
        if self.metadata.emoji:
            parts[0] = f"# {self.metadata.emoji} {self.metadata.name}"
        
        if self.metadata.description:
            parts.append(f"\n{self.metadata.description}")
        
        if self.instructions:
            parts.append(f"\n## 使用说明\n\n{self.instructions}")
        
        if self.examples:
            parts.append("\n## 示例")
            for ex in self.examples:
                parts.append(f"\n用户: {ex.user_request}")
                parts.append(f"命令: `{ex.command}`")
        
        if self.metadata.requires:
            req_parts = []
            if self.metadata.requires.bins:
                req_parts.append(f"二进制文件: {', '.join(self.metadata.requires.bins)}")
            if self.metadata.requires.env:
                req_parts.append(f"环境变量: {', '.join(self.metadata.requires.env)}")
            if req_parts:
                parts.append(f"\n## 依赖\n\n" + "\n".join(req_parts))
        
        if self.metadata.os:
            parts.append(f"\n## 支持的系统\n\n{', '.join(self.metadata.os)}")
        
        return "\n".join(parts)
    
    def to_openclaw_format(self) -> str:
        """转换为 OpenClaw SKILL.md 格式"""
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
        
        if self.metadata.requires:
            req_dict = {}
            if self.metadata.requires.bins:
                req_dict["bins"] = self.metadata.requires.bins
            if self.metadata.requires.any_bins:
                req_dict["anyBins"] = self.metadata.requires.any_bins
            if self.metadata.requires.env:
                req_dict["env"] = self.metadata.requires.env
            if self.metadata.requires.config:
                req_dict["config"] = self.metadata.requires.config
            if req_dict:
                lines.append(f"requires:")
                for k, v in req_dict.items():
                    lines.append(f"  {k}: {v}")
        
        if self.metadata.install:
            lines.append("install:")
            for inst in self.metadata.install:
                inst_lines = [f"  - kind: {inst.kind}"]
                if inst.id:
                    inst_lines.append(f"    id: {inst.id}")
                if inst.package:
                    inst_lines.append(f"    package: {inst.package}")
                if inst.formula:
                    inst_lines.append(f"    formula: {inst.formula}")
                lines.extend(inst_lines)
        
        lines.append("---")
        lines.append("")
        
        if self.content and not self.content.startswith("---"):
            lines.append(self.content)
        else:
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
            
            if self.examples:
                lines.append("## 示例")
                lines.append("")
                for ex in self.examples:
                    lines.append(f"用户请求: {ex.user_request}")
                    lines.append("```bash")
                    lines.append(ex.command)
                    lines.append("```")
                    lines.append("")
        
        return "\n".join(lines)


@dataclass
class SkillEntry:
    """
    技能条目 - 参考 OpenClaw types.ts SkillEntry
    """
    skill: Skill
    frontmatter: Dict
    metadata: Optional[SkillMetadata] = None
    invocation: Optional[SkillInvocationPolicy] = None
    
    def to_dict(self) -> Dict:
        return {
            "skill": self.skill.to_prompt(),
            "frontmatter": self.frontmatter,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "invocation": self.invocation.to_dict() if self.invocation else None
        }


@dataclass
class SkillSnapshot:
    """
    技能快照 - 参考 OpenClaw types.ts SkillSnapshot
    """
    prompt: str
    skills: List[Dict[str, Any]] = field(default_factory=list)
    skill_filter: Optional[List[str]] = None
    resolved_skills: List[Skill] = field(default_factory=list)
    version: int = 1
    
    def to_dict(self) -> Dict:
        return {
            "prompt": self.prompt,
            "skills": self.skills,
            "skillFilter": self.skill_filter,
            "version": self.version
        }


class SkillManager:
    """
    技能管理器 - 完全兼容 OpenClaw
    
    管理所有技能，支持：
    1. 加载 SKILL.md 文件（完全兼容 OpenClaw 格式）
    2. 动态注册新技能
    3. 根据用户请求匹配技能
    4. AI 自主学习新技能
    5. 技能安装和依赖检查
    
    参考 OpenClaw src/agents/skills/workspace.ts
    """
    
    _instance: Optional["SkillManager"] = None
    
    def __init__(
        self,
        skills_dir: str = "./data/skills",
        extra_dirs: List[str] = None,
        max_skills_in_prompt: int = 150,
        max_skills_prompt_chars: int = 30000
    ):
        self._skills_dir = Path(skills_dir)
        self._extra_dirs = [Path(d) for d in (extra_dirs or [])]
        self._skills: Dict[str, Skill] = {}
        self._skill_entries: Dict[str, SkillEntry] = {}
        self._command_handlers: Dict[str, Callable] = {}
        self._max_skills_in_prompt = max_skills_in_prompt
        self._max_skills_prompt_chars = max_skills_prompt_chars
        self._load_skills()
    
    def _load_skills(self):
        """加载所有技能"""
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        
        all_dirs = [self._skills_dir] + self._extra_dirs
        
        for skills_root in all_dirs:
            if not skills_root.exists():
                continue
            
            for skill_dir in skills_root.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        try:
                            skill = Skill.from_file(str(skill_file))
                            self._skills[skill.metadata.name] = skill
                            
                            frontmatter = Skill._parse_frontmatter(skill.content)
                            self._skill_entries[skill.metadata.name] = SkillEntry(
                                skill=skill,
                                frontmatter=frontmatter,
                                metadata=skill.metadata,
                                invocation=skill.invocation
                            )
                        except Exception as e:
                            print(f"加载技能失败 {skill_dir}: {e}")
    
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
    
    def get_skills_prompt(self, user_level: UserLevel, skill_filter: List[str] = None) -> str:
        """
        获取技能列表提示 - 参考 OpenClaw buildSkillsSection
        
        格式：
        ## Skills (mandatory)
        Before replying: scan <available_skills> <description> entries.
        - If exactly one skill clearly applies: read its SKILL.md at <location> with `read`, then follow it.
        - If multiple could apply: choose the most specific one, then read/follow it.
        - If none clearly apply: do not read any SKILL.md.
        """
        if not self._skills:
            return ""
        
        skills_to_include = list(self._skills.values())
        
        if skill_filter:
            skills_to_include = [
                s for s in skills_to_include 
                if s.metadata.name in skill_filter
            ]
        
        skills_to_include = skills_to_include[:self._max_skills_in_prompt]
        
        parts = [
            "## Skills (mandatory)",
            "Before replying: scan <available_skills> <description> entries.",
            "- If exactly one skill clearly applies: read its SKILL.md at <location> with `read`, then follow it.",
            "- If multiple could apply: choose the most specific one, then read/follow it.",
            "- If none clearly apply: do not read any SKILL.md.",
            "Constraints: never read more than one skill up front; only read after selecting.",
            ""
        ]
        
        for skill in skills_to_include:
            location = skill.skill_path or f"~/.xiaomeng/skills/{skill.metadata.name}/SKILL.md"
            parts.append(f"<available_skills>")
            parts.append(f"  <skill>")
            parts.append(f"    <name>{skill.metadata.name}</name>")
            if skill.metadata.emoji:
                parts.append(f"    <emoji>{skill.metadata.emoji}</emoji>")
            parts.append(f"    <description>{skill.metadata.description}</description>")
            parts.append(f"    <location>{location}</location>")
            parts.append(f"  </skill>")
            parts.append(f"</available_skills>")
        
        prompt = "\n".join(parts)
        
        if len(prompt) > self._max_skills_prompt_chars:
            prompt = prompt[:self._max_skills_prompt_chars] + "\n... (truncated)"
        
        return prompt
    
    def build_skill_snapshot(self, skill_filter: List[str] = None) -> SkillSnapshot:
        """构建技能快照"""
        prompt = self.get_skills_prompt(UserLevel.OWNER, skill_filter)
        
        skills_info = [
            {
                "name": s.metadata.name,
                "primaryEnv": s.metadata.primary_env
            }
            for s in self._skills.values()
        ]
        
        return SkillSnapshot(
            prompt=prompt,
            skills=skills_info,
            skill_filter=skill_filter,
            resolved_skills=list(self._skills.values())
        )
    
    def register_skill(self, skill: Skill):
        """注册技能"""
        self._skills[skill.metadata.name] = skill
        frontmatter = Skill._parse_frontmatter(skill.content)
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
        examples: List[Dict[str, str]],
        skill_key: str = None,
        emoji: str = None,
        requires: Dict = None,
        install: List[Dict] = None
    ) -> Skill:
        """
        创建新技能 - AI 可以调用此方法自主学习新技能
        
        参考 OpenClaw SKILL.md 格式
        """
        skill_dir = self._skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        skill_examples = [
            SkillExample(
                user_request=ex.get("user_request", ""),
                command=ex.get("command", ""),
                explanation=ex.get("explanation", "")
            )
            for ex in examples
        ]
        
        skill_requires = None
        if requires:
            skill_requires = SkillRequires.from_dict(requires)
        
        skill_install = []
        if install:
            for inst in install:
                skill_install.append(SkillInstallSpec.from_dict(inst))
        
        skill = Skill(
            metadata=SkillMetadata(
                name=name,
                description=description,
                skill_key=skill_key or name,
                emoji=emoji,
                requires=skill_requires,
                install=skill_install
            ),
            content="",
            examples=skill_examples,
            instructions=instructions
        )
        
        skill_content = skill.to_openclaw_format()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_content, encoding='utf-8')
        
        skill.content = skill_content
        skill.skill_path = str(skill_file)
        self._skills[name] = skill
        
        frontmatter = Skill._parse_frontmatter(skill.content)
        self._skill_entries[name] = SkillEntry(
            skill=skill,
            frontmatter=frontmatter,
            metadata=skill.metadata,
            invocation=skill.invocation
        )
        
        return skill
    
    def delete_skill(self, name: str) -> bool:
        """删除技能"""
        if name not in self._skills:
            return False
        
        skill = self._skills[name]
        skill_dir = Path(skill.skill_path).parent
        
        import shutil
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        
        del self._skills[name]
        if name in self._skill_entries:
            del self._skill_entries[name]
        
        return True
    
    def match_skill_for_request(self, request: str) -> Optional[Skill]:
        """根据用户请求匹配技能"""
        request_lower = request.lower()
        
        for skill in self._skills.values():
            if skill.metadata.name.lower() in request_lower:
                return skill
            
            for tag in skill.metadata.tags:
                if tag.lower() in request_lower:
                    return skill
            
            if skill.metadata.description and skill.metadata.description.lower() in request_lower:
                return skill
            
            for ex in skill.examples:
                if ex.user_request.lower() in request_lower:
                    return skill
        
        return None
    
    def check_skill_eligibility(
        self, 
        skill: Skill,
        has_bin: Callable[[str], bool] = None,
        has_env: Callable[[str], bool] = None,
        current_os: str = None
    ) -> bool:
        """
        检查技能是否可用
        
        参考 OpenClaw SkillEligibilityContext
        """
        if skill.metadata.os:
            if current_os and current_os.lower() not in [o.lower() for o in skill.metadata.os]:
                return False
        
        if skill.metadata.requires:
            if skill.metadata.requires.bins:
                if has_bin:
                    for bin_name in skill.metadata.requires.bins:
                        if not has_bin(bin_name):
                            return False
            
            if skill.metadata.requires.any_bins:
                if has_bin:
                    if not any(has_bin(b) for b in skill.metadata.requires.any_bins):
                        return False
            
            if skill.metadata.requires.env:
                if has_env:
                    for env_name in skill.metadata.requires.env:
                        if not has_env(env_name):
                            return False
        
        return True
    
    def get_installable_skills(self) -> List[Skill]:
        """获取可安装的技能"""
        return [
            s for s in self._skills.values()
            if s.metadata.install
        ]
    
    def install_skill_dependencies(self, skill: Skill, prefer_brew: bool = True) -> Dict[str, Any]:
        """
        安装技能依赖
        
        参考 OpenClaw SkillsInstallPreferences
        
        Args:
            skill: 技能对象
            prefer_brew: 是否优先使用 brew (macOS)
        
        Returns:
            安装结果
        """
        import subprocess
        import platform
        
        results = {
            "skill": skill.metadata.name,
            "installed": [],
            "failed": [],
            "skipped": []
        }
        
        if not skill.metadata.install:
            results["skipped"].append("no install specs")
            return results
        
        current_os = platform.system().lower()
        if current_os == "darwin":
            current_os = "macos"
        
        for spec in skill.metadata.install:
            if spec.os and current_os not in [o.lower() for o in spec.os]:
                results["skipped"].append(f"{spec.kind}: not for {current_os}")
                continue
            
            try:
                if spec.kind == "brew":
                    if prefer_brew and current_os == "macos":
                        package = spec.package or spec.formula or skill.metadata.name
                        result = subprocess.run(
                            ["brew", "install", package],
                            capture_output=True,
                            timeout=300000
                        )
                        if result.returncode == 0:
                            results["installed"].append(f"brew:{package}")
                        else:
                            results["failed"].append(f"brew:{package}")
                
                elif spec.kind == "node":
                    package = spec.package or skill.metadata.name
                    result = subprocess.run(
                        ["npm", "install", "-g", package],
                        capture_output=True,
                        timeout=300000
                    )
                    if result.returncode == 0:
                        results["installed"].append(f"npm:{package}")
                    else:
                        results["failed"].append(f"npm:{package}")
                
                elif spec.kind == "go":
                    module = spec.module or skill.metadata.name
                    result = subprocess.run(
                        ["go", "install", module],
                        capture_output=True,
                        timeout=300000
                    )
                    if result.returncode == 0:
                        results["installed"].append(f"go:{module}")
                    else:
                        results["failed"].append(f"go:{module}")
                
                elif spec.kind == "uv":
                    package = spec.package or skill.metadata.name
                    result = subprocess.run(
                        ["uv", "pip", "install", package],
                        capture_output=True,
                        timeout=300000
                    )
                    if result.returncode == 0:
                        results["installed"].append(f"uv:{package}")
                    else:
                        results["failed"].append(f"uv:{package}")
                
                elif spec.kind == "download":
                    if spec.url:
                        import urllib.request
                        dest = spec.target_dir or str(self._skills_dir / skill.metadata.name)
                        Path(dest).mkdir(parents=True, exist_ok=True)
                        filename = spec.archive or spec.url.split("/")[-1]
                        dest_path = Path(dest) / filename
                        urllib.request.urlretrieve(spec.url, dest_path)
                        results["installed"].append(f"download:{filename}")
            
            except Exception as e:
                results["failed"].append(f"{spec.kind}: {str(e)}")
        
        return results
    
    def check_binary_available(self, bin_name: str) -> bool:
        """检查二进制文件是否可用"""
        import shutil
        return shutil.which(bin_name) is not None
    
    def check_env_available(self, env_name: str) -> bool:
        """检查环境变量是否设置"""
        return os.environ.get(env_name) is not None
    
    def get_skill_status(self, skill: Skill) -> Dict[str, Any]:
        """
        获取技能状态
        
        参考 OpenClaw SkillEligibilityContext
        """
        import platform
        
        current_os = platform.system().lower()
        if current_os == "darwin":
            current_os = "macos"
        
        status = {
            "name": skill.metadata.name,
            "os_compatible": True,
            "bins_available": [],
            "bins_missing": [],
            "env_available": [],
            "env_missing": [],
            "eligible": True
        }
        
        if skill.metadata.os:
            status["os_compatible"] = current_os in [o.lower() for o in skill.metadata.os]
            if not status["os_compatible"]:
                status["eligible"] = False
                return status
        
        if skill.metadata.requires:
            for bin_name in skill.metadata.requires.bins:
                if self.check_binary_available(bin_name):
                    status["bins_available"].append(bin_name)
                else:
                    status["bins_missing"].append(bin_name)
                    status["eligible"] = False
            
            if skill.metadata.requires.any_bins:
                any_available = any(
                    self.check_binary_available(b) 
                    for b in skill.metadata.requires.any_bins
                )
                if not any_available:
                    status["bins_missing"].extend(skill.metadata.requires.any_bins)
                    status["eligible"] = False
            
            for env_name in skill.metadata.requires.env:
                if self.check_env_available(env_name):
                    status["env_available"].append(env_name)
                else:
                    status["env_missing"].append(env_name)
                    status["eligible"] = False
        
        return status
    
    def refresh_skills(self):
        """刷新技能列表"""
        self._skills.clear()
        self._skill_entries.clear()
        self._load_skills()
    
    async def execute_skill_command(
        self,
        skill_name: str,
        command_name: str,
        args: str = "",
        user: "User" = None
    ) -> Dict[str, Any]:
        """
        执行技能命令
        
        参考 OpenClaw dispatch 机制
        """
        from .tools import ToolRegistry
        
        skill = self._skills.get(skill_name)
        if not skill:
            return {"success": False, "error": f"技能不存在: {skill_name}"}
        
        command = None
        for cmd in skill.commands:
            if cmd.name == command_name:
                command = cmd
                break
        
        if not command:
            return {"success": False, "error": f"命令不存在: {command_name}"}
        
        if command.dispatch and command.dispatch.kind == "tool":
            tool_name = command.dispatch.tool_name or command_name
            tool_registry = ToolRegistry.get_instance()
            
            if command.dispatch.arg_mode == "raw":
                tool_args = args
            else:
                import shlex
                try:
                    tool_args = shlex.split(args) if args else []
                except:
                    tool_args = [args] if args else []
            
            tool = tool_registry.get_tool(tool_name)
            if tool:
                if isinstance(tool_args, list):
                    result = await tool.execute(user, *tool_args)
                else:
                    result = await tool.execute(user, tool_args)
                return result.to_dict()
            else:
                return {"success": False, "error": f"工具不存在: {tool_name}"}
        
        return {"success": False, "error": "未定义 dispatch"}
    
    def get_skill_commands(self, skill_name: str) -> List[Dict]:
        """获取技能的所有命令"""
        skill = self._skills.get(skill_name)
        if not skill:
            return []
        
        return [cmd.to_dict() for cmd in skill.commands]
    
    def get_all_commands(self) -> Dict[str, List[Dict]]:
        """获取所有技能的命令"""
        result = {}
        for skill_name, skill in self._skills.items():
            if skill.commands:
                result[skill_name] = [cmd.to_dict() for cmd in skill.commands]
        return result
    
    @classmethod
    def get_instance(cls) -> "SkillManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
