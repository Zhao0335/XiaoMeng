"""
XiaoMengCore 自我改进系统
参考 OpenClaw self-improving-agent 技能

核心功能：
1. 错误记录：操作失败时记录到 .learnings/ERRORS.md
2. 学习记录：用户纠正、知识更新时记录到 .learnings/LEARNINGS.md
3. 功能请求：记录用户需求到 .learnings/FEATURE_REQUESTS.md
4. 学习提升：重要学习内容提升到 AGENTS.md、SOUL.md 等核心文件
5. 自动创建技能：AI可以根据学习内容自主创建新技能
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from enum import Enum
import json
import re


class LearningCategory(Enum):
    CORRECTION = "correction"
    KNOWLEDGE_GAP = "knowledge_gap"
    BEST_PRACTICE = "best_practice"
    ERROR = "error"
    FEATURE_REQUEST = "feature_request"
    WORKFLOW_IMPROVEMENT = "workflow_improvement"
    TOOL_TIP = "tool_tip"
    BEHAVIOR_PATTERN = "behavior_pattern"


class LearningPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class LearningEntry:
    entry_id: str
    category: LearningCategory
    content: str
    context: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    priority: LearningPriority = LearningPriority.MEDIUM
    tags: List[str] = field(default_factory=list)
    resolved: bool = False
    resolution: str = ""
    elevated_to: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_markdown(self) -> str:
        timestamp_str = self.timestamp.strftime("%Y-%m-%d %H:%M")
        tags_str = " ".join([f"#{t}" for t in self.tags]) if self.tags else ""
        status = "✅" if self.resolved else "⏳"
        
        lines = [
            f"## [{timestamp_str}] {self.category.value} {status}",
            f"{self.content}",
        ]
        
        if self.context:
            lines.append(f"\n**上下文**: {self.context}")
        
        if self.tags:
            lines.append(f"\n**标签**: {tags_str}")
        
        if self.resolved and self.resolution:
            lines.append(f"\n**解决方案**: {self.resolution}")
        
        if self.elevated_to:
            lines.append(f"\n**已提升到**: {self.elevated_to}")
        
        return "\n".join(lines)
    
    @classmethod
    def from_markdown(cls, content: str) -> Optional["LearningEntry"]:
        lines = content.strip().split("\n")
        if not lines:
            return None
        
        header_match = re.match(r"## \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] (\w+) (✅|⏳)", lines[0])
        if not header_match:
            return None
        
        timestamp_str, category_str, status_str = header_match.groups()
        category = LearningCategory(category_str)
        resolved = status_str == "✅"
        
        entry_content = []
        context = ""
        tags = []
        resolution = ""
        elevated_to = ""
        
        for line in lines[1:]:
            if line.startswith("**上下文**:"):
                context = line.replace("**上下文**:", "").strip()
            elif line.startswith("**标签**:"):
                tags_str = line.replace("**标签**:", "").strip()
                tags = re.findall(r"#(\w+)", tags_str)
            elif line.startswith("**解决方案**:"):
                resolution = line.replace("**解决方案**:", "").strip()
            elif line.startswith("**已提升到**:"):
                elevated_to = line.replace("**已提升到**:", "").strip()
            else:
                entry_content.append(line)
        
        return cls(
            entry_id="",
            category=category,
            content="\n".join(entry_content).strip(),
            context=context,
            timestamp=datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M"),
            resolved=resolved,
            resolution=resolution,
            elevated_to=elevated_to,
            tags=tags
        )


class LearningsStore:
    """
    学习记录存储
    
    目录结构：
    .learnings/
    ├── ERRORS.md          # 错误记录
    ├── LEARNINGS.md       # 学习记录
    ├── FEATURE_REQUESTS.md # 功能请求
    └── RESOLVED.md        # 已解决的问题
    """
    
    def __init__(self, learnings_dir: str):
        self.learnings_dir = Path(learnings_dir)
        self.learnings_dir.mkdir(parents=True, exist_ok=True)
        
        self._init_files()
    
    def _init_files(self):
        files = {
            "ERRORS.md": "# 错误记录\n\n记录操作失败、命令执行错误等。\n\n",
            "LEARNINGS.md": "# 学习记录\n\n记录用户纠正、知识更新、最佳实践等。\n\n",
            "FEATURE_REQUESTS.md": "# 功能请求\n\n记录用户提出的新功能需求。\n\n",
            "RESOLVED.md": "# 已解决问题\n\n记录已经解决的学习条目。\n\n"
        }
        
        for filename, default_content in files.items():
            file_path = self.learnings_dir / filename
            if not file_path.exists():
                file_path.write_text(default_content, encoding='utf-8')
    
    def add_error(self, entry: LearningEntry):
        self._append_entry("ERRORS.md", entry)
    
    def add_learning(self, entry: LearningEntry):
        self._append_entry("LEARNINGS.md", entry)
    
    def add_feature_request(self, entry: LearningEntry):
        self._append_entry("FEATURE_REQUESTS.md", entry)
    
    def resolve_entry(self, entry: LearningEntry, resolution: str):
        entry.resolved = True
        entry.resolution = resolution
        self._append_entry("RESOLVED.md", entry)
    
    def _append_entry(self, filename: str, entry: LearningEntry):
        file_path = self.learnings_dir / filename
        content = file_path.read_text(encoding='utf-8')
        content += "\n\n" + entry.to_markdown() + "\n"
        file_path.write_text(content, encoding='utf-8')
    
    def get_recent_errors(self, limit: int = 10) -> List[LearningEntry]:
        return self._parse_entries("ERRORS.md", limit)
    
    def get_recent_learnings(self, limit: int = 10) -> List[LearningEntry]:
        return self._parse_entries("LEARNINGS.md", limit)
    
    def get_feature_requests(self, limit: int = 20) -> List[LearningEntry]:
        return self._parse_entries("FEATURE_REQUESTS.md", limit)
    
    def _parse_entries(self, filename: str, limit: int = 10) -> List[LearningEntry]:
        file_path = self.learnings_dir / filename
        if not file_path.exists():
            return []
        
        content = file_path.read_text(encoding='utf-8')
        sections = re.split(r"\n## ", content)
        
        entries = []
        for section in sections[1:limit+1]:
            entry = LearningEntry.from_markdown("## " + section)
            if entry:
                entries.append(entry)
        
        return entries
    
    def search(self, keyword: str) -> List[LearningEntry]:
        results = []
        for filename in ["ERRORS.md", "LEARNINGS.md", "FEATURE_REQUESTS.md"]:
            entries = self._parse_entries(filename, limit=50)
            for entry in entries:
                if keyword.lower() in entry.content.lower():
                    results.append(entry)
        return results


class LearningElevator:
    """
    学习提升器
    
    将重要的学习内容提升到核心文件：
    - 工作流改进 → AGENTS.md
    - 工具技巧 → TOOLS.md
    - 行为模式 → SOUL.md
    """
    
    ELEVATION_RULES = {
        LearningCategory.WORKFLOW_IMPROVEMENT: "AGENTS.md",
        LearningCategory.TOOL_TIP: "TOOLS.md",
        LearningCategory.BEHAVIOR_PATTERN: "SOUL.md",
        LearningCategory.BEST_PRACTICE: "AGENTS.md",
    }
    
    MIN_PRIORITY_FOR_ELEVATION = LearningPriority.HIGH
    
    def __init__(self, persona_dir: str):
        self.persona_dir = Path(persona_dir)
    
    def should_elevate(self, entry: LearningEntry) -> Optional[str]:
        if entry.priority.value < self.MIN_PRIORITY_FOR_ELEVATION.value:
            return None
        
        if entry.category in self.ELEVATION_RULES:
            return self.ELEVATION_RULES[entry.category]
        
        if entry.category == LearningCategory.CORRECTION and entry.priority == LearningPriority.CRITICAL:
            return "AGENTS.md"
        
        return None
    
    def elevate(self, entry: LearningEntry, target_file: str = None) -> bool:
        target = target_file or self.should_elevate(entry)
        if not target:
            return False
        
        file_path = self.persona_dir / target
        if not file_path.exists():
            return False
        
        existing_content = file_path.read_text(encoding='utf-8')
        
        elevation_section = self._format_elevation(entry)
        
        new_content = existing_content + "\n\n" + elevation_section
        file_path.write_text(new_content, encoding='utf-8')
        
        entry.elevated_to = target
        return True
    
    def _format_elevation(self, entry: LearningEntry) -> str:
        timestamp = entry.timestamp.strftime("%Y-%m-%d")
        return f"""<!-- 学习提升 [{timestamp}] -->
{entry.content}

<!-- 来源: {entry.category.value} -->
"""


class SelfImprovingAgent:
    """
    自我改进智能体
    
    参考 OpenClaw self-improving-agent 技能
    实现 AI 的持续学习和自我进化能力
    """
    
    _instance: Optional["SelfImprovingAgent"] = None
    
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.learnings_dir = self.workspace_dir / ".learnings"
        self.persona_dir = self.workspace_dir
        
        self._store = LearningsStore(str(self.learnings_dir))
        self._elevator = LearningElevator(str(self.persona_dir))
    
    def record_error(
        self,
        error_content: str,
        context: str = "",
        command: str = "",
        priority: LearningPriority = LearningPriority.MEDIUM
    ) -> LearningEntry:
        entry = LearningEntry(
            entry_id=self._generate_id(),
            category=LearningCategory.ERROR,
            content=error_content,
            context=f"{context}\n命令: {command}" if command else context,
            priority=priority,
            tags=["error"]
        )
        self._store.add_error(entry)
        return entry
    
    def record_correction(
        self,
        original: str,
        correction: str,
        reason: str = "",
        priority: LearningPriority = LearningPriority.HIGH
    ) -> LearningEntry:
        content = f"**原内容**: {original}\n**纠正**: {correction}"
        if reason:
            content += f"\n**原因**: {reason}"
        
        entry = LearningEntry(
            entry_id=self._generate_id(),
            category=LearningCategory.CORRECTION,
            content=content,
            priority=priority,
            tags=["correction", "user-feedback"]
        )
        self._store.add_learning(entry)
        
        if priority.value >= LearningPriority.HIGH.value:
            self._elevator.elevate(entry)
        
        return entry
    
    def record_knowledge_gap(
        self,
        gap_description: str,
        context: str = "",
        priority: LearningPriority = LearningPriority.MEDIUM
    ) -> LearningEntry:
        entry = LearningEntry(
            entry_id=self._generate_id(),
            category=LearningCategory.KNOWLEDGE_GAP,
            content=gap_description,
            context=context,
            priority=priority,
            tags=["knowledge-gap"]
        )
        self._store.add_learning(entry)
        return entry
    
    def record_best_practice(
        self,
        practice: str,
        context: str = "",
        priority: LearningPriority = LearningPriority.MEDIUM
    ) -> LearningEntry:
        entry = LearningEntry(
            entry_id=self._generate_id(),
            category=LearningCategory.BEST_PRACTICE,
            content=practice,
            context=context,
            priority=priority,
            tags=["best-practice"]
        )
        self._store.add_learning(entry)
        
        self._elevator.elevate(entry)
        
        return entry
    
    def record_feature_request(
        self,
        feature: str,
        description: str = "",
        user_id: str = "",
        priority: LearningPriority = LearningPriority.MEDIUM
    ) -> LearningEntry:
        content = f"**功能**: {feature}"
        if description:
            content += f"\n**描述**: {description}"
        if user_id:
            content += f"\n**请求者**: {user_id}"
        
        entry = LearningEntry(
            entry_id=self._generate_id(),
            category=LearningCategory.FEATURE_REQUEST,
            content=content,
            priority=priority,
            tags=["feature-request"]
        )
        self._store.add_feature_request(entry)
        return entry
    
    def record_workflow_improvement(
        self,
        improvement: str,
        old_workflow: str = "",
        new_workflow: str = "",
        priority: LearningPriority = LearningPriority.HIGH
    ) -> LearningEntry:
        content = f"**改进**: {improvement}"
        if old_workflow:
            content += f"\n**原流程**: {old_workflow}"
        if new_workflow:
            content += f"\n**新流程**: {new_workflow}"
        
        entry = LearningEntry(
            entry_id=self._generate_id(),
            category=LearningCategory.WORKFLOW_IMPROVEMENT,
            content=content,
            priority=priority,
            tags=["workflow", "improvement"]
        )
        self._store.add_learning(entry)
        
        self._elevator.elevate(entry)
        
        return entry
    
    def resolve_error(self, error_id: str, resolution: str) -> bool:
        errors = self._store.get_recent_errors(limit=50)
        for entry in errors:
            if entry.entry_id == error_id:
                self._store.resolve_entry(entry, resolution)
                return True
        return False
    
    def get_recent_learnings(self, limit: int = 10) -> List[LearningEntry]:
        return self._store.get_recent_learnings(limit)
    
    def get_pending_errors(self, limit: int = 10) -> List[LearningEntry]:
        errors = self._store.get_recent_errors(limit)
        return [e for e in errors if not e.resolved]
    
    def get_feature_requests(self, limit: int = 20) -> List[LearningEntry]:
        return self._store.get_feature_requests(limit)
    
    def search_learnings(self, keyword: str) -> List[LearningEntry]:
        return self._store.search(keyword)
    
    def get_learning_summary(self) -> Dict[str, Any]:
        errors = self._store.get_recent_errors(50)
        learnings = self._store.get_recent_learnings(50)
        features = self._store.get_feature_requests(20)
        
        return {
            "total_errors": len(errors),
            "unresolved_errors": len([e for e in errors if not e.resolved]),
            "total_learnings": len(learnings),
            "elevated_learnings": len([l for l in learnings if l.elevated_to]),
            "feature_requests": len(features),
            "recent_errors": [e.to_markdown() for e in errors[:5]],
            "recent_learnings": [l.to_markdown() for l in learnings[:5]]
        }
    
    def _generate_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:8]
    
    @classmethod
    def get_instance(cls) -> "SelfImprovingAgent":
        if cls._instance is None:
            from config import ConfigManager
            config = ConfigManager.get_instance().get()
            cls._instance = cls(config.data_dir)
        return cls._instance
    
    @classmethod
    def initialize(cls, workspace_dir: str) -> "SelfImprovingAgent":
        cls._instance = cls(workspace_dir)
        return cls._instance


class SelfImprovingTools:
    """
    自我改进相关工具
    
    提供给 AI 调用的工具接口
    """
    
    @staticmethod
    def get_tools_schema() -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_error",
                    "description": "记录操作错误或失败",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "error_content": {
                                "type": "string",
                                "description": "错误内容描述"
                            },
                            "context": {
                                "type": "string",
                                "description": "错误发生的上下文"
                            },
                            "command": {
                                "type": "string",
                                "description": "导致错误的命令"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                                "description": "优先级"
                            }
                        },
                        "required": ["error_content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "record_correction",
                    "description": "记录用户纠正（用户指出你的错误并给出正确答案）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "original": {
                                "type": "string",
                                "description": "原来的错误内容"
                            },
                            "correction": {
                                "type": "string",
                                "description": "正确的答案"
                            },
                            "reason": {
                                "type": "string",
                                "description": "纠正的原因"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                                "description": "优先级"
                            }
                        },
                        "required": ["original", "correction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "record_best_practice",
                    "description": "记录发现的最佳实践",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "practice": {
                                "type": "string",
                                "description": "最佳实践内容"
                            },
                            "context": {
                                "type": "string",
                                "description": "应用场景"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                                "description": "优先级"
                            }
                        },
                        "required": ["practice"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "record_feature_request",
                    "description": "记录用户提出的新功能需求",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "feature": {
                                "type": "string",
                                "description": "功能名称"
                            },
                            "description": {
                                "type": "string",
                                "description": "功能描述"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                                "description": "优先级"
                            }
                        },
                        "required": ["feature"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_skill_from_learning",
                    "description": "根据学习内容创建新技能",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "技能名称"
                            },
                            "description": {
                                "type": "string",
                                "description": "技能描述"
                            },
                            "instructions": {
                                "type": "string",
                                "description": "使用说明"
                            },
                            "examples": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "user_request": {"type": "string"},
                                        "command": {"type": "string"}
                                    }
                                },
                                "description": "示例列表"
                            }
                        },
                        "required": ["skill_name", "description", "instructions"]
                    }
                }
            }
        ]
    
    @staticmethod
    async def execute_tool(tool_name: str, arguments: Dict) -> Dict:
        agent = SelfImprovingAgent.get_instance()
        
        priority_map = {
            "low": LearningPriority.LOW,
            "medium": LearningPriority.MEDIUM,
            "high": LearningPriority.HIGH,
            "critical": LearningPriority.CRITICAL
        }
        
        if tool_name == "record_error":
            entry = agent.record_error(
                error_content=arguments["error_content"],
                context=arguments.get("context", ""),
                command=arguments.get("command", ""),
                priority=priority_map.get(arguments.get("priority", "medium"), LearningPriority.MEDIUM)
            )
            return {"success": True, "entry_id": entry.entry_id}
        
        elif tool_name == "record_correction":
            entry = agent.record_correction(
                original=arguments["original"],
                correction=arguments["correction"],
                reason=arguments.get("reason", ""),
                priority=priority_map.get(arguments.get("priority", "high"), LearningPriority.HIGH)
            )
            return {"success": True, "entry_id": entry.entry_id, "elevated": bool(entry.elevated_to)}
        
        elif tool_name == "record_best_practice":
            entry = agent.record_best_practice(
                practice=arguments["practice"],
                context=arguments.get("context", ""),
                priority=priority_map.get(arguments.get("priority", "medium"), LearningPriority.MEDIUM)
            )
            return {"success": True, "entry_id": entry.entry_id, "elevated": bool(entry.elevated_to)}
        
        elif tool_name == "record_feature_request":
            entry = agent.record_feature_request(
                feature=arguments["feature"],
                description=arguments.get("description", ""),
                priority=priority_map.get(arguments.get("priority", "medium"), LearningPriority.MEDIUM)
            )
            return {"success": True, "entry_id": entry.entry_id}
        
        elif tool_name == "create_skill_from_learning":
            from core.skills import SkillManager
            skill_manager = SkillManager.get_instance()
            skill = skill_manager.create_skill(
                name=arguments["skill_name"],
                description=arguments["description"],
                instructions=arguments["instructions"],
                examples=arguments.get("examples", [])
            )
            return {"success": True, "skill_path": skill.skill_path}
        
        return {"success": False, "error": f"Unknown tool: {tool_name}"}
