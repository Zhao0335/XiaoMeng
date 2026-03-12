"""
XiaoMengCore 内置工具系统
兼容 OpenClaw 工具接口，让 AI 能真正执行操作
"""

import os
import re
import json
import shutil
import asyncio
import subprocess
from typing import Optional, Dict, List, Any, Callable, Awaitable
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from models import User, UserLevel


class ToolPermission(Enum):
    """工具权限级别"""
    OWNER_ONLY = "owner_only"
    WHITELIST_AND_ABOVE = "whitelist"
    EVERYONE = "everyone"


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
            "data": self.data
        }


class BaseTool:
    """工具基类"""
    
    name: str = "base"
    description: str = ""
    parameters: Dict = {}
    permission: ToolPermission = ToolPermission.EVERYONE
    
    async def execute(self, user: User, **kwargs) -> ToolResult:
        raise NotImplementedError
    
    def check_permission(self, user: User) -> bool:
        """检查权限"""
        if self.permission == ToolPermission.OWNER_ONLY:
            return user.level == UserLevel.OWNER
        elif self.permission == ToolPermission.WHITELIST_AND_ABOVE:
            return user.level in [UserLevel.OWNER, UserLevel.WHITELIST]
        return True
    
    def get_schema(self) -> Dict:
        """获取工具 schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ReadTool(BaseTool):
    """读取文件工具"""
    
    name = "read"
    description = "读取文件内容"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径"
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号（可选）"
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（可选）"
            }
        },
        "required": ["path"]
    }
    
    async def execute(self, user: User, path: str, start_line: int = None, end_line: int = None) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            
            if not file_path.exists():
                return ToolResult(False, "", f"文件不存在: {path}")
            
            if not file_path.is_file():
                return ToolResult(False, "", f"不是文件: {path}")
            
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            if start_line is not None or end_line is not None:
                start = (start_line or 1) - 1
                end = end_line or len(lines)
                lines = lines[start:end]
            
            content = "".join(lines)
            return ToolResult(True, content, metadata={"lines": len(lines)})
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class WriteTool(BaseTool):
    """写入文件工具"""
    
    name = "write"
    description = "写入或创建文件"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径"
            },
            "content": {
                "type": "string",
                "description": "文件内容"
            },
            "mode": {
                "type": "string",
                "enum": ["write", "append"],
                "description": "写入模式"
            }
        },
        "required": ["path", "content"]
    }
    
    async def execute(self, user: User, path: str, content: str, mode: str = "write") -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            write_mode = 'a' if mode == "append" else 'w'
            
            with open(file_path, write_mode, encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(True, f"文件已写入: {path}", metadata={"bytes": len(content.encode('utf-8'))})
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class ExecTool(BaseTool):
    """执行命令工具"""
    
    name = "exec"
    description = "执行 Shell 命令"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的命令"
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒）"
            },
            "cwd": {
                "type": "string",
                "description": "工作目录"
            }
        },
        "required": ["command"]
    }
    
    async def execute(self, user: User, command: str, timeout: int = 30, cwd: str = None) -> ToolResult:
        try:
            dangerous_commands = ["rm -rf", "mkfs", "dd if=", "> /dev/sd", "chmod 777"]
            for dangerous in dangerous_commands:
                if dangerous in command:
                    return ToolResult(False, "", f"危险命令被拒绝: {dangerous}")
            
            if command.startswith("mkdir "):
                dir_path = command[6:].strip()
                command = f"if not exist {dir_path} mkdir {dir_path}"
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(False, "", f"命令超时（{timeout}秒）")
            
            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace')
            
            if process.returncode == 0:
                return ToolResult(True, output or "命令执行成功", error if error else None)
            else:
                return ToolResult(False, output, error or f"退出码: {process.returncode}")
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class GrepTool(BaseTool):
    """搜索文件内容工具"""
    
    name = "grep"
    description = "在文件中搜索匹配的文本"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "搜索模式（正则表达式）"
            },
            "path": {
                "type": "string",
                "description": "搜索路径"
            },
            "file_pattern": {
                "type": "string",
                "description": "文件名模式（如 *.py）"
            }
        },
        "required": ["pattern", "path"]
    }
    
    async def execute(self, user: User, pattern: str, path: str, file_pattern: str = "*") -> ToolResult:
        try:
            search_path = Path(path).expanduser().resolve()
            
            if not search_path.exists():
                return ToolResult(False, "", f"路径不存在: {path}")
            
            matches = []
            regex = re.compile(pattern, re.IGNORECASE)
            
            if search_path.is_file():
                files = [search_path]
            else:
                files = list(search_path.rglob(file_pattern))
            
            for file_path in files:
                if not file_path.is_file():
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                matches.append(f"{file_path}:{line_num}: {line.strip()}")
                except:
                    continue
            
            if matches:
                return ToolResult(True, "\n".join(matches[:100]), metadata={"count": len(matches)})
            else:
                return ToolResult(True, "未找到匹配", metadata={"count": 0})
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class FindTool(BaseTool):
    """查找文件工具"""
    
    name = "find"
    description = "查找文件和目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "搜索起始路径"
            },
            "name": {
                "type": "string",
                "description": "文件名模式"
            },
            "type": {
                "type": "string",
                "enum": ["file", "dir", "all"],
                "description": "查找类型"
            }
        },
        "required": ["path"]
    }
    
    async def execute(self, user: User, path: str, name: str = "*", type: str = "all") -> ToolResult:
        try:
            search_path = Path(path).expanduser().resolve()
            
            if not search_path.exists():
                return ToolResult(False, "", f"路径不存在: {path}")
            
            results = []
            
            for item in search_path.rglob(name):
                if type == "file" and not item.is_file():
                    continue
                if type == "dir" and not item.is_dir():
                    continue
                results.append(str(item))
            
            if results:
                return ToolResult(True, "\n".join(results[:200]), metadata={"count": len(results)})
            else:
                return ToolResult(True, "未找到匹配的文件", metadata={"count": 0})
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class LsTool(BaseTool):
    """列出目录工具"""
    
    name = "ls"
    description = "列出目录内容"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录路径"
            },
            "show_hidden": {
                "type": "boolean",
                "description": "显示隐藏文件"
            }
        },
        "required": ["path"]
    }
    
    async def execute(self, user: User, path: str, show_hidden: bool = False) -> ToolResult:
        try:
            dir_path = Path(path).expanduser().resolve()
            
            if not dir_path.exists():
                return ToolResult(False, "", f"路径不存在: {path}")
            
            if not dir_path.is_dir():
                return ToolResult(False, "", f"不是目录: {path}")
            
            items = []
            for item in sorted(dir_path.iterdir()):
                if not show_hidden and item.name.startswith('.'):
                    continue
                
                if item.is_dir():
                    items.append(f"📁 {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"📄 {item.name} ({size} bytes)")
            
            return ToolResult(True, "\n".join(items), metadata={"count": len(items)})
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class DeleteTool(BaseTool):
    """删除文件工具"""
    
    name = "delete"
    description = "删除文件或目录"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要删除的路径"
            },
            "recursive": {
                "type": "boolean",
                "description": "递归删除目录"
            }
        },
        "required": ["path"]
    }
    
    async def execute(self, user: User, path: str, recursive: bool = False) -> ToolResult:
        try:
            target_path = Path(path).expanduser().resolve()
            
            if not target_path.exists():
                return ToolResult(False, "", f"路径不存在: {path}")
            
            protected_paths = ["/", "/etc", "/usr", "/bin", "/sbin", "/home"]
            for protected in protected_paths:
                if str(target_path) == protected or str(target_path).startswith(protected + "/"):
                    if str(target_path) != protected:
                        pass
                    else:
                        return ToolResult(False, "", f"受保护的路径: {path}")
            
            if target_path.is_file():
                target_path.unlink()
            elif target_path.is_dir():
                if recursive:
                    shutil.rmtree(target_path)
                else:
                    target_path.rmdir()
            
            return ToolResult(True, f"已删除: {path}")
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class UpdatePersonaTool(BaseTool):
    """更新人设工具 - 仅主人可用，修改核心人设文件"""
    
    name = "update_persona"
    description = "更新人设文件（SOUL.md, AGENTS.md, IDENTITY.md, USER.md, TOOLS.md, MEMORY.md, HEARTBEAT.md）- 仅主人可用"
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "enum": ["SOUL.md", "AGENTS.md", "IDENTITY.md", "USER.md", "TOOLS.md", "MEMORY.md", "HEARTBEAT.md"],
                "description": "要更新的文件"
            },
            "content": {
                "type": "string",
                "description": "新内容"
            },
            "mode": {
                "type": "string",
                "enum": ["replace", "append", "prepend"],
                "description": "更新模式"
            },
            "commit_message": {
                "type": "string",
                "description": "变更说明（用于 Git 提交和审计日志）"
            }
        },
        "required": ["file", "content"]
    }
    
    async def execute(self, user: User, file: str, content: str, mode: str = "append", commit_message: str = None) -> ToolResult:
        try:
            from core.memory import MemoryManager
            from core.version_control import VersionControl
            
            memory_manager = MemoryManager.get_instance()
            persona_dir = memory_manager._persona_loader.persona_dir
            
            file_path = persona_dir / file
            
            old_content = ""
            if file_path.exists():
                old_content = file_path.read_text(encoding='utf-8')
            
            if mode == "replace" or not file_path.exists():
                new_content = content
            elif mode == "append":
                new_content = old_content + "\n\n" + content
            elif mode == "prepend":
                new_content = content + "\n\n" + old_content
            
            file_path.write_text(new_content, encoding='utf-8')
            
            vc = VersionControl.get_instance()
            if vc.is_enabled():
                vc.commit(
                    file_path=str(file_path),
                    message=commit_message or f"Update {file}",
                    user_id=user.user_id,
                    old_content=old_content,
                    new_content=new_content
                )
            
            return ToolResult(
                True, 
                f"已更新 {file}", 
                metadata={
                    "file": file, 
                    "mode": mode,
                    "versioned": vc.is_enabled()
                }
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class CreateSkillTool(BaseTool):
    """创建技能工具 - 仅主人可用，创建新技能"""
    
    name = "create_skill"
    description = "创建新技能（SKILL.md）- 仅主人可用"
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "name": {
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
        "required": ["name", "description", "instructions"]
    }
    
    async def execute(self, user: User, name: str, description: str, instructions: str, examples: List[Dict] = None) -> ToolResult:
        try:
            from core.skills import SkillManager
            
            skill_manager = SkillManager.get_instance()
            skill = skill_manager.create_skill(
                name=name,
                description=description,
                instructions=instructions,
                examples=examples or []
            )
            
            return ToolResult(
                True, 
                f"已创建技能: {name}\n路径: {skill.skill_path}",
                metadata={"skill_name": name, "path": skill.skill_path}
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class MemorySearchTool(BaseTool):
    """记忆搜索工具 - 参考 OpenClaw memory_search，所有人可用但只能搜索自己的记忆"""
    
    name = "memory_search"
    description = """Mandatory recall step: semantically search MEMORY.md + memory/*.md (and optional session transcripts) before answering questions about prior work, decisions, dates, people, preferences, or todos; returns top snippets with path + lines.

Use this tool when:
- User asks about past conversations or decisions
- You need to recall user preferences or personal info
- Looking for specific dates, events, or facts
- Checking previous work or todos

注意：只能搜索当前用户的记忆，不能搜索其他用户的记忆。"""
    permission = ToolPermission.EVERYONE
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，描述你想找的记忆内容"
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数（默认5）",
                "default": 5
            },
            "min_score": {
                "type": "number",
                "description": "最小相关度分数（0-1，默认0.3）",
                "default": 0.3
            }
        },
        "required": ["query"]
    }
    
    async def execute(self, user: User, query: str, max_results: int = 5, min_score: float = 0.3) -> ToolResult:
        try:
            from core.memory import MemoryManager, create_hybrid_search
            
            memory_manager = MemoryManager.get_instance()
            
            results = memory_manager.search_memories(query, user, limit=max_results)
            
            if not results:
                return ToolResult(
                    True,
                    "没有找到相关记忆。这可能是因为：\n1. 记忆库为空\n2. 查询词不够精确\n3. 相关记忆尚未记录",
                    metadata={"query": query, "count": 0}
                )
            
            output_lines = ["# 记忆搜索结果\n"]
            for i, result in enumerate(results, 1):
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                timestamp = metadata.get("timestamp", "未知时间")
                tags = metadata.get("tags", "")
                
                output_lines.append(f"## 结果 {i}")
                output_lines.append(f"时间: {timestamp}")
                if tags:
                    output_lines.append(f"标签: {tags}")
                output_lines.append(f"内容: {content[:300]}{'...' if len(content) > 300 else ''}")
                output_lines.append("")
            
            return ToolResult(
                True,
                "\n".join(output_lines),
                metadata={
                    "query": query,
                    "count": len(results),
                    "max_results": max_results
                }
            )
            
        except Exception as e:
            return ToolResult(False, "", f"记忆搜索失败: {str(e)}")


class MemoryGetTool(BaseTool):
    """获取特定记忆文件工具 - 参考 OpenClaw memory_get，仅主人可用"""
    
    name = "memory_get"
    description = """Get specific memory file content (MEMORY.md or daily memory files) - 仅主人可用。

Use this when you need to:
- Read the full MEMORY.md file
- Read a specific day's memory file
- Get raw memory content for analysis"""
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "记忆文件路径（如 MEMORY.md 或 memory/2024-01-15.md）"
            },
            "from_line": {
                "type": "integer",
                "description": "起始行号（可选）"
            },
            "lines": {
                "type": "integer",
                "description": "读取行数（可选）"
            }
        },
        "required": ["path"]
    }
    
    async def execute(self, user: User, path: str, from_line: int = None, lines: int = None) -> ToolResult:
        try:
            from core.memory import MemoryManager
            
            memory_manager = MemoryManager.get_instance()
            persona_dir = memory_manager._persona_loader.persona_dir
            
            if path == "MEMORY.md" or path == "memory":
                file_path = persona_dir / "MEMORY.md"
            elif path.startswith("memory/"):
                file_path = persona_dir / path
            else:
                file_path = persona_dir / "memory" / path
            
            if not file_path.exists():
                return ToolResult(False, "", f"记忆文件不存在: {path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.readlines()
            
            if from_line is not None:
                content = content[from_line:]
            if lines is not None:
                content = content[:lines]
            
            return ToolResult(
                True,
                "".join(content),
                metadata={
                    "path": str(file_path),
                    "total_lines": len(content)
                }
            )
            
        except Exception as e:
            return ToolResult(False, "", f"获取记忆失败: {str(e)}")


class AddMemoryTool(BaseTool):
    """添加记忆工具 - 白名单及以上可用"""
    
    name = "add_memory"
    description = "添加长期记忆 - 白名单及以上用户可用"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "记忆内容"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签"
            },
            "importance": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "重要性（1-5）"
            }
        },
        "required": ["content"]
    }
    
    async def execute(self, user: User, content: str, tags: List[str] = None, importance: int = 1) -> ToolResult:
        try:
            from core.memory import MemoryManager
            
            memory_manager = MemoryManager.get_instance()
            memory_manager.add_memory(user, content, tags, importance)
            
            return ToolResult(
                True, 
                f"已添加记忆: {content[:50]}...",
                metadata={"tags": tags, "importance": importance}
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetHistoryTool(BaseTool):
    """获取变更历史工具"""
    
    name = "get_history"
    description = "获取文件的变更历史（Git 提交记录和审计日志）"
    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "文件名（如 SOUL.md）"
            },
            "limit": {
                "type": "integer",
                "description": "返回条数限制"
            }
        },
        "required": []
    }
    
    async def execute(self, user: User, file: str = None, limit: int = 20) -> ToolResult:
        try:
            from core.version_control import VersionControl
            from core.memory import MemoryManager
            
            vc = VersionControl.get_instance()
            
            if file:
                memory_manager = MemoryManager.get_instance()
                persona_dir = memory_manager._persona_loader.persona_dir
                file_path = persona_dir / file
                history = vc.get_history(str(file_path), limit=limit)
            else:
                history = vc.get_history(limit=limit)
            
            return ToolResult(
                True,
                f"找到 {len(history)} 条历史记录",
                metadata={"history": history, "file": file}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class RollbackTool(BaseTool):
    """回滚变更工具"""
    
    name = "rollback"
    description = "回滚文件到之前的版本"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "要回滚的文件名"
            },
            "entry_id": {
                "type": "string",
                "description": "审计日志条目 ID"
            },
            "commit_hash": {
                "type": "string",
                "description": "Git 提交哈希"
            }
        },
        "required": ["file"]
    }
    
    async def execute(self, user: User, file: str, entry_id: str = None, commit_hash: str = None) -> ToolResult:
        try:
            from core.version_control import VersionControl
            from core.memory import MemoryManager
            
            vc = VersionControl.get_instance()
            memory_manager = MemoryManager.get_instance()
            persona_dir = memory_manager._persona_loader.persona_dir
            file_path = persona_dir / file
            
            if not entry_id and not commit_hash:
                return ToolResult(False, "", "需要提供 entry_id 或 commit_hash")
            
            success = vc.rollback(str(file_path), entry_id=entry_id, commit_hash=commit_hash)
            
            if success:
                return ToolResult(
                    True,
                    f"已回滚 {file}",
                    metadata={"file": file, "entry_id": entry_id, "commit_hash": commit_hash}
                )
            else:
                return ToolResult(False, "", "回滚失败")
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetDiffTool(BaseTool):
    """查看差异工具"""
    
    name = "get_diff"
    description = "查看文件的变更差异"
    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "文件名"
            }
        },
        "required": []
    }
    
    async def execute(self, user: User, file: str = None) -> ToolResult:
        try:
            from core.version_control import VersionControl
            from core.memory import MemoryManager
            
            vc = VersionControl.get_instance()
            
            if file:
                memory_manager = MemoryManager.get_instance()
                persona_dir = memory_manager._persona_loader.persona_dir
                file_path = persona_dir / file
                diff = vc.get_diff(str(file_path))
            else:
                diff = vc.get_diff()
            
            return ToolResult(
                True,
                diff if diff else "没有差异",
                metadata={"diff": diff, "file": file}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetPendingChangesTool(BaseTool):
    """获取待确认变更工具"""
    
    name = "get_pending_changes"
    description = "获取待确认的变更列表"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    async def execute(self, user: User) -> ToolResult:
        try:
            from core.version_control import VersionControl
            
            vc = VersionControl.get_instance()
            pending = vc.get_pending_changes()
            
            return ToolResult(
                True,
                f"有 {len(pending)} 个待确认变更",
                metadata={"pending": [p.to_dict() for p in pending]}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class ConfirmChangeTool(BaseTool):
    """确认变更工具"""
    
    name = "confirm_change"
    description = "确认待定的变更"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "change_id": {
                "type": "string",
                "description": "变更 ID"
            }
        },
        "required": ["change_id"]
    }
    
    async def execute(self, user: User, change_id: str) -> ToolResult:
        try:
            from core.version_control import VersionControl
            
            vc = VersionControl.get_instance()
            success = vc.confirm_change(change_id)
            
            if success:
                return ToolResult(True, f"已确认变更 {change_id}")
            else:
                return ToolResult(False, "", f"变更 {change_id} 不存在或已过期")
        except Exception as e:
            return ToolResult(False, "", str(e))


class RejectChangeTool(BaseTool):
    """拒绝变更工具"""
    
    name = "reject_change"
    description = "拒绝待定的变更"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "change_id": {
                "type": "string",
                "description": "变更 ID"
            }
        },
        "required": ["change_id"]
    }
    
    async def execute(self, user: User, change_id: str) -> ToolResult:
        try:
            from core.version_control import VersionControl
            
            vc = VersionControl.get_instance()
            success = vc.reject_change(change_id)
            
            if success:
                return ToolResult(True, f"已拒绝变更 {change_id}")
            else:
                return ToolResult(False, "", f"变更 {change_id} 不存在")
        except Exception as e:
            return ToolResult(False, "", str(e))


class DownloadTool(BaseTool):
    """下载文件工具"""
    
    name = "download"
    description = "从网络下载文件"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "下载链接"
            },
            "save_path": {
                "type": "string",
                "description": "保存路径（可选，默认当前目录）"
            },
            "filename": {
                "type": "string",
                "description": "保存文件名（可选，自动从URL提取）"
            }
        },
        "required": ["url"]
    }
    
    async def execute(self, user: User, url: str, save_path: str = ".", filename: str = None) -> ToolResult:
        try:
            import aiohttp
            from urllib.parse import urlparse, unquote
            
            if not filename:
                parsed = urlparse(url)
                filename = unquote(Path(parsed.path).name) or "downloaded_file"
            
            save_dir = Path(save_path).expanduser().resolve()
            save_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = save_dir / filename
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status != 200:
                        return ToolResult(False, "", f"下载失败: HTTP {response.status}")
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                    
            size_kb = downloaded / 1024
            return ToolResult(
                True, 
                f"下载完成: {file_path}\n大小: {size_kb:.2f} KB",
                metadata={
                    "path": str(file_path),
                    "size": downloaded,
                    "url": url
                }
            )
            
        except ImportError:
            return ToolResult(False, "", "请安装 aiohttp: pip install aiohttp")
        except Exception as e:
            return ToolResult(False, "", str(e))


class WebFetchTool(BaseTool):
    """网页抓取工具"""
    
    name = "web_fetch"
    description = "获取网页内容"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "网页链接"
            },
            "selector": {
                "type": "string",
                "description": "CSS选择器（可选，提取特定内容）"
            }
        },
        "required": ["url"]
    }
    
    async def execute(self, user: User, url: str, selector: str = None) -> ToolResult:
        try:
            import aiohttp
            from bs4 import BeautifulSoup
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status != 200:
                        return ToolResult(False, "", f"请求失败: HTTP {response.status}")
                    
                    html = await response.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            if selector:
                elements = soup.select(selector)
                text = "\n".join([el.get_text(strip=True) for el in elements])
            else:
                text = soup.get_text(separator='\n', strip=True)
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                text = '\n'.join(lines[:100])
            
            return ToolResult(
                True,
                text[:5000],
                metadata={"url": url, "length": len(text)}
            )
            
        except ImportError:
            return ToolResult(False, "", "请安装 aiohttp 和 beautifulsoup4: pip install aiohttp beautifulsoup4")
        except Exception as e:
            return ToolResult(False, "", str(e))


class WebSearchTool(BaseTool):
    """网络搜索工具"""
    
    name = "web_search"
    description = "在网络上搜索信息"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "num_results": {
                "type": "integer",
                "description": "返回结果数量（默认5）"
            }
        },
        "required": ["query"]
    }
    
    async def execute(self, user: User, query: str, num_results: int = 5) -> ToolResult:
        try:
            import aiohttp
            import urllib.parse
            
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }) as response:
                    html = await response.text()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            results = []
            for result in soup.select('.result')[:num_results]:
                title_elem = result.select_one('.result__a')
                snippet_elem = result.select_one('.result__snippet')
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    results.append(f"标题: {title}\n链接: {link}\n摘要: {snippet}\n")
            
            if results:
                return ToolResult(
                    True,
                    "\n---\n".join(results),
                    metadata={"query": query, "count": len(results)}
                )
            else:
                return ToolResult(True, "未找到相关结果", metadata={"query": query, "count": 0})
                
        except ImportError:
            return ToolResult(False, "", "请安装 aiohttp 和 beautifulsoup4: pip install aiohttp beautifulsoup4")
        except Exception as e:
            return ToolResult(False, "", str(e))


class RecordErrorTool(BaseTool):
    """记录错误工具 - 自我改进系统"""
    
    name = "record_error"
    description = "记录操作错误或失败，用于持续学习和改进"
    requires_owner = True
    parameters = {
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
    
    async def execute(self, user: User, error_content: str, context: str = "", command: str = "", priority: str = "medium") -> ToolResult:
        try:
            from core.self_improving import SelfImprovingAgent, LearningPriority
            
            agent = SelfImprovingAgent.get_instance()
            priority_enum = {
                "low": LearningPriority.LOW,
                "medium": LearningPriority.MEDIUM,
                "high": LearningPriority.HIGH,
                "critical": LearningPriority.CRITICAL
            }.get(priority, LearningPriority.MEDIUM)
            
            entry = agent.record_error(
                error_content=error_content,
                context=context,
                command=command,
                priority=priority_enum
            )
            
            return ToolResult(
                True,
                f"已记录错误: {entry.entry_id}",
                metadata={"entry_id": entry.entry_id}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class RecordCorrectionTool(BaseTool):
    """记录纠正工具 - 自我改进系统"""
    
    name = "record_correction"
    description = "记录用户纠正（用户指出你的错误并给出正确答案）"
    requires_owner = True
    parameters = {
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
            }
        },
        "required": ["original", "correction"]
    }
    
    async def execute(self, user: User, original: str, correction: str, reason: str = "") -> ToolResult:
        try:
            from core.self_improving import SelfImprovingAgent, LearningPriority
            
            agent = SelfImprovingAgent.get_instance()
            entry = agent.record_correction(
                original=original,
                correction=correction,
                reason=reason,
                priority=LearningPriority.HIGH
            )
            
            elevated_msg = " (已提升到核心文件)" if entry.elevated_to else ""
            return ToolResult(
                True,
                f"已记录纠正: {entry.entry_id}{elevated_msg}",
                metadata={"entry_id": entry.entry_id, "elevated_to": entry.elevated_to}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class RecordBestPracticeTool(BaseTool):
    """记录最佳实践工具 - 自我改进系统"""
    
    name = "record_best_practice"
    description = "记录发现的最佳实践，会被提升到核心文件"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "practice": {
                "type": "string",
                "description": "最佳实践内容"
            },
            "context": {
                "type": "string",
                "description": "应用场景"
            }
        },
        "required": ["practice"]
    }
    
    async def execute(self, user: User, practice: str, context: str = "") -> ToolResult:
        try:
            from core.self_improving import SelfImprovingAgent, LearningPriority
            
            agent = SelfImprovingAgent.get_instance()
            entry = agent.record_best_practice(
                practice=practice,
                context=context,
                priority=LearningPriority.HIGH
            )
            
            return ToolResult(
                True,
                f"已记录最佳实践: {entry.entry_id}，已提升到 {entry.elevated_to}",
                metadata={"entry_id": entry.entry_id, "elevated_to": entry.elevated_to}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class RecordFeatureRequestTool(BaseTool):
    """记录功能请求工具"""
    
    name = "record_feature_request"
    description = "记录用户提出的新功能需求"
    parameters = {
        "type": "object",
        "properties": {
            "feature": {
                "type": "string",
                "description": "功能名称"
            },
            "description": {
                "type": "string",
                "description": "功能描述"
            }
        },
        "required": ["feature"]
    }
    
    async def execute(self, user: User, feature: str, description: str = "") -> ToolResult:
        try:
            from core.self_improving import SelfImprovingAgent, LearningPriority
            
            agent = SelfImprovingAgent.get_instance()
            entry = agent.record_feature_request(
                feature=feature,
                description=description,
                user_id=user.user_id,
                priority=LearningPriority.MEDIUM
            )
            
            return ToolResult(
                True,
                f"已记录功能请求: {entry.entry_id}",
                metadata={"entry_id": entry.entry_id}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetLearningsTool(BaseTool):
    """获取学习记录工具"""
    
    name = "get_learnings"
    description = "获取最近的学习记录、错误和功能请求"
    parameters = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["errors", "learnings", "features", "all"],
                "description": "要获取的类型"
            },
            "limit": {
                "type": "integer",
                "description": "返回条数限制"
            }
        },
        "required": ["type"]
    }
    
    async def execute(self, user: User, type: str = "all", limit: int = 10) -> ToolResult:
        try:
            from core.self_improving import SelfImprovingAgent
            
            agent = SelfImprovingAgent.get_instance()
            
            result = {}
            if type in ["errors", "all"]:
                result["errors"] = [e.to_markdown() for e in agent.get_pending_errors(limit)]
            if type in ["learnings", "all"]:
                result["learnings"] = [l.to_markdown() for l in agent.get_recent_learnings(limit)]
            if type in ["features", "all"]:
                result["features"] = [f.to_markdown() for f in agent.get_feature_requests(limit)]
            
            return ToolResult(
                True,
                json.dumps(result, ensure_ascii=False, indent=2),
                metadata=result
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class RegisterModelTool(BaseTool):
    """注册模型工具 - 多模型调度系统"""
    
    name = "register_model"
    description = "注册新模型到调度系统（Basic/Brain/Special三层）"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "model_id": {
                "type": "string",
                "description": "模型唯一ID"
            },
            "layer": {
                "type": "string",
                "enum": ["basic", "brain", "special"],
                "description": "模型层级"
            },
            "role": {
                "type": "string",
                "enum": ["chat", "reasoning", "code", "vision", "embedding"],
                "description": "模型角色"
            },
            "endpoint": {
                "type": "string",
                "description": "API端点URL"
            },
            "model_name": {
                "type": "string",
                "description": "模型名称"
            },
            "api_key": {
                "type": "string",
                "description": "API密钥（可选）"
            }
        },
        "required": ["model_id", "layer", "role", "endpoint", "model_name"]
    }
    
    async def execute(self, user: User, model_id: str, layer: str, role: str, endpoint: str, model_name: str, api_key: str = None) -> ToolResult:
        try:
            from core.model_layer import ModelLayerRouter, ModelEndpoint, ModelLayer, ModelRole
            
            router = ModelLayerRouter.get_instance()
            
            endpoint_obj = ModelEndpoint(
                model_id=model_id,
                layer=ModelLayer(layer),
                role=ModelRole(role),
                endpoint=endpoint,
                model_name=model_name,
                api_key=api_key
            )
            
            registered_id = router.register_model(endpoint_obj)
            
            return ToolResult(
                True,
                f"已注册模型: {registered_id} ({layer}/{role})",
                metadata={"model_id": registered_id, "layer": layer, "role": role}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class UnregisterModelTool(BaseTool):
    """注销模型工具"""
    
    name = "unregister_model"
    description = "从调度系统注销模型"
    requires_owner = True
    parameters = {
        "type": "object",
        "properties": {
            "model_id": {
                "type": "string",
                "description": "要注销的模型ID"
            }
        },
        "required": ["model_id"]
    }
    
    async def execute(self, user: User, model_id: str) -> ToolResult:
        try:
            from core.model_layer import ModelLayerRouter
            
            router = ModelLayerRouter.get_instance()
            success = router.unregister_model(model_id)
            
            if success:
                return ToolResult(True, f"已注销模型: {model_id}")
            else:
                return ToolResult(False, "", f"模型不存在: {model_id}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetModelsStatusTool(BaseTool):
    """获取模型状态工具"""
    
    name = "get_models_status"
    description = "获取所有模型的当前状态"
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    async def execute(self, user: User) -> ToolResult:
        try:
            from core.model_layer import ModelLayerRouter
            
            router = ModelLayerRouter.get_instance()
            status = router.get_status()
            
            return ToolResult(
                True,
                json.dumps(status, ensure_ascii=False, indent=2),
                metadata=status
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class AddScheduleTool(BaseTool):
    """添加日程工具 - 白名单及以上可用"""
    
    name = "add_schedule"
    description = "添加一个日程安排，如会议、约会、提醒等 - 白名单及以上用户可用"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "日程标题"
            },
            "time": {
                "type": "string",
                "description": "日程时间，如'明天下午3点'、'2024-06-15 14:00'"
            },
            "duration": {
                "type": "integer",
                "description": "持续时长（分钟）"
            },
            "description": {
                "type": "string",
                "description": "日程描述"
            },
            "location": {
                "type": "string",
                "description": "地点"
            },
            "type": {
                "type": "string",
                "enum": ["meeting", "appointment", "task", "reminder", "event", "deadline"],
                "description": "日程类型"
            }
        },
        "required": ["title", "time"]
    }
    
    async def execute(self, user: User, title: str, time: str, duration: int = 60,
                     description: str = "", location: str = "", type: str = "task") -> ToolResult:
        try:
            from core.schedule import ScheduleManager, ScheduleType
            from datetime import datetime, timedelta
            
            mgr = ScheduleManager()
            
            parsed_time = mgr.parse_natural_time(time)
            if not parsed_time:
                try:
                    parsed_time = datetime.fromisoformat(time.replace(" ", "T"))
                except:
                    return ToolResult(False, "", f"无法解析时间: {time}")
            
            end_time = parsed_time + timedelta(minutes=duration) if duration else None
            
            schedule_type = ScheduleType(type) if type in [t.value for t in ScheduleType] else ScheduleType.TASK
            
            schedule = mgr.add_schedule(
                title=title,
                start_time=parsed_time,
                end_time=end_time,
                schedule_type=schedule_type,
                description=description,
                location=location
            )
            
            return ToolResult(
                True,
                f"已添加日程: {title}\n时间: {parsed_time.strftime('%Y-%m-%d %H:%M')}\n地点: {location or '未指定'}",
                metadata={"schedule_id": schedule.id}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetScheduleTool(BaseTool):
    """查询日程工具"""
    
    name = "get_schedule"
    description = "查询日程安排，可以查询今天、明天或指定日期的日程"
    parameters = {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "查询日期，如'今天'、'明天'、'2024-06-15'，不填则查询今天"
            }
        },
        "required": []
    }
    
    async def execute(self, user: User, date: str = "今天") -> ToolResult:
        try:
            from core.schedule import ScheduleManager
            from datetime import datetime, date as date_type
            
            mgr = ScheduleManager()
            
            if date in ["今天", "today", ""]:
                target_date = date_type.today()
            elif date in ["明天", "tomorrow"]:
                target_date = date_type.today() + timedelta(days=1)
            elif date in ["后天"]:
                target_date = date_type.today() + timedelta(days=2)
            else:
                try:
                    target_date = datetime.strptime(date, "%Y-%m-%d").date()
                except:
                    return ToolResult(False, "", f"无法解析日期: {date}")
            
            schedules = mgr.get_schedules_by_date(target_date)
            
            if not schedules:
                return ToolResult(True, f"{target_date} 没有日程安排")
            
            result = f"📅 {target_date} 的日程安排:\n\n"
            for i, s in enumerate(schedules, 1):
                time_str = s.start_time.strftime("%H:%M")
                end_str = f" - {s.end_time.strftime('%H:%M')}" if s.end_time else ""
                result += f"{i}. [{time_str}{end_str}] {s.title}"
                if s.location:
                    result += f" @ {s.location}"
                result += "\n"
            
            return ToolResult(True, result, metadata={"count": len(schedules)})
        except Exception as e:
            return ToolResult(False, "", str(e))


class AddTodoTool(BaseTool):
    """添加待办事项工具 - 白名单及以上可用"""
    
    name = "add_todo"
    description = "添加一个待办事项 - 白名单及以上用户可用"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "待办事项标题"
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "urgent"],
                "description": "优先级"
            },
            "due_date": {
                "type": "string",
                "description": "截止日期，如'明天'、'2024-06-15'"
            },
            "category": {
                "type": "string",
                "enum": ["work", "personal", "study", "health", "finance", "shopping", "other"],
                "description": "分类"
            },
            "notes": {
                "type": "string",
                "description": "备注"
            }
        },
        "required": ["title"]
    }
    
    async def execute(self, user: User, title: str, priority: str = "medium",
                     due_date: str = "", category: str = "other", notes: str = "") -> ToolResult:
        try:
            from core.todo import TodoManager, TodoPriority, TodoCategory
            from datetime import datetime, date as date_type, timedelta
            
            mgr = TodoManager()
            
            priority_map = {
                "low": TodoPriority.LOW,
                "medium": TodoPriority.MEDIUM,
                "high": TodoPriority.HIGH,
                "urgent": TodoPriority.URGENT
            }
            
            category_map = {
                "work": TodoCategory.WORK,
                "personal": TodoCategory.PERSONAL,
                "study": TodoCategory.STUDY,
                "health": TodoCategory.HEALTH,
                "finance": TodoCategory.FINANCE,
                "shopping": TodoCategory.SHOPPING,
                "other": TodoCategory.OTHER
            }
            
            parsed_due = None
            if due_date:
                if due_date in ["今天", "today"]:
                    parsed_due = date_type.today()
                elif due_date in ["明天", "tomorrow"]:
                    parsed_due = date_type.today() + timedelta(days=1)
                else:
                    try:
                        parsed_due = datetime.strptime(due_date, "%Y-%m-%d").date()
                    except:
                        pass
            
            todo = mgr.add_todo(
                title=title,
                priority=priority_map.get(priority, TodoPriority.MEDIUM),
                category=category_map.get(category, TodoCategory.OTHER),
                due_date=parsed_due,
                notes=notes
            )
            
            result = f"✅ 已添加待办: {title}"
            if parsed_due:
                result += f"\n截止日期: {parsed_due}"
            
            return ToolResult(True, result, metadata={"todo_id": todo.id})
        except Exception as e:
            return ToolResult(False, "", str(e))


class ListTodoTool(BaseTool):
    """列出待办事项工具"""
    
    name = "list_todos"
    description = "列出待办事项，可以筛选未完成、已完成或即将到期的"
    parameters = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "enum": ["pending", "completed", "overdue", "all"],
                "description": "筛选条件：pending=未完成，completed=已完成，overdue=已过期，all=全部"
            }
        },
        "required": []
    }
    
    async def execute(self, user: User, filter: str = "pending") -> ToolResult:
        try:
            from core.todo import TodoManager, TodoStatus
            
            mgr = TodoManager()
            
            if filter == "pending":
                todos = mgr.get_pending_todos()
                title = "📋 待办事项"
            elif filter == "completed":
                todos = mgr.get_completed_todos()
                title = "✅ 已完成"
            elif filter == "overdue":
                todos = mgr.get_overdue_todos()
                title = "⚠️ 已过期"
            else:
                todos = mgr.get_all_todos()
                title = "📋 所有待办"
            
            if not todos:
                return ToolResult(True, f"{title}: 无")
            
            result = f"{title}:\n\n"
            priority_icons = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "URGENT": "🔴"}
            
            for i, t in enumerate(todos[:10], 1):
                icon = priority_icons.get(t.priority.name, "⚪")
                status = "✓" if t.status.name == "COMPLETED" else "○"
                result += f"{i}. {icon} [{status}] {t.title}"
                if t.due_date:
                    result += f" (截止: {t.due_date})"
                result += "\n"
            
            if len(todos) > 10:
                result += f"\n... 还有 {len(todos) - 10} 项"
            
            return ToolResult(True, result, metadata={"count": len(todos)})
        except Exception as e:
            return ToolResult(False, "", str(e))


class CompleteTodoTool(BaseTool):
    """完成待办事项工具"""
    
    name = "complete_todo"
    description = "将一个待办事项标记为已完成"
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "待办事项标题（模糊匹配）"
            }
        },
        "required": ["title"]
    }
    
    async def execute(self, user: User, title: str) -> ToolResult:
        try:
            from core.todo import TodoManager
            
            mgr = TodoManager()
            todos = mgr.search_todos(title)
            
            if not todos:
                return ToolResult(False, "", f"未找到待办: {title}")
            
            todo = todos[0]
            mgr.complete_todo(todo.id)
            
            return ToolResult(True, f"✅ 已完成: {todo.title}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetWeatherTool(BaseTool):
    """获取天气工具"""
    
    name = "get_weather"
    description = "获取指定城市的天气信息"
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如'北京'、'上海'"
            }
        },
        "required": []
    }
    
    async def execute(self, user: User, city: str = "") -> ToolResult:
        try:
            from core.realtime_info import RealtimeInfoService
            
            service = RealtimeInfoService()
            weather = await service.get_weather(city or None)
            
            if not weather:
                return ToolResult(False, "", "获取天气失败，请稍后重试")
            
            response = service.format_weather_response(weather)
            return ToolResult(True, response, metadata=weather.to_dict())
        except Exception as e:
            return ToolResult(False, "", str(e))


class GetNewsTool(BaseTool):
    """获取新闻工具"""
    
    name = "get_news"
    description = "获取最新新闻"
    parameters = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["general", "technology", "business", "entertainment", "sports", "science", "health"],
                "description": "新闻类别"
            },
            "count": {
                "type": "integer",
                "description": "新闻数量（1-10）"
            }
        },
        "required": []
    }
    
    async def execute(self, user: User, category: str = "general", count: int = 5) -> ToolResult:
        try:
            from core.realtime_info import RealtimeInfoService
            
            service = RealtimeInfoService()
            news = await service.get_news(category, min(count, 10))
            
            if not news:
                return ToolResult(True, "暂无新闻")
            
            response = service.format_news_response(news)
            return ToolResult(True, response, metadata={"count": len(news)})
        except Exception as e:
            return ToolResult(False, "", str(e))


class AddSpecialDayTool(BaseTool):
    """添加特殊日子工具"""
    
    name = "add_special_day"
    description = "添加一个特殊日子，如生日、纪念日等"
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "日子名称，如'妈妈生日'、'结婚纪念日'"
            },
            "date": {
                "type": "string",
                "description": "日期，如'06-15'（每年）或'2024-06-15'（特定年份）"
            },
            "type": {
                "type": "string",
                "enum": ["birthday", "anniversary", "holiday", "memorial", "other"],
                "description": "日子类型"
            },
            "description": {
                "type": "string",
                "description": "描述或备注"
            }
        },
        "required": ["name", "date"]
    }
    
    async def execute(self, user: User, name: str, date: str, 
                     type: str = "other", description: str = "") -> ToolResult:
        try:
            from core.care import ProactiveCareSystem
            
            system = ProactiveCareSystem()
            system.add_special_day(name, date, type, description)
            
            return ToolResult(True, f"✅ 已添加特殊日子: {name} ({date})")
        except Exception as e:
            return ToolResult(False, "", str(e))


class SetPreferenceTool(BaseTool):
    """设置用户偏好工具"""
    
    name = "set_preference"
    description = "设置用户的个人偏好，如称呼、问候时间等"
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "偏好键名，如'nickname'、'morning_time'、'evening_time'"
            },
            "value": {
                "type": "string",
                "description": "偏好值"
            }
        },
        "required": ["key", "value"]
    }
    
    async def execute(self, user: User, key: str, value: str) -> ToolResult:
        try:
            from core.personalization import PersonalizationEngine
            
            engine = PersonalizationEngine()
            
            valid_keys = ["nickname", "morning_time", "evening_time", "communication_style"]
            if key not in valid_keys:
                return ToolResult(False, "", f"未知偏好: {key}。可用: {', '.join(valid_keys)}")
            
            engine.set_preference(key, value)
            
            return ToolResult(True, f"✅ 已设置 {key} = {value}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class SessionsListTool(BaseTool):
    """列出活跃会话工具 - 参考 OpenClaw sessions_list"""
    
    name = "sessions_list"
    description = "列出活跃会话，可以按身份ID或活跃时间筛选"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "identity_id": {
                "type": "string",
                "description": "按统一身份ID筛选"
            },
            "active_within_minutes": {
                "type": "integer",
                "description": "最近N分钟内活跃的会话"
            }
        }
    }
    
    async def execute(self, user: User, identity_id: str = None, active_within_minutes: int = None) -> ToolResult:
        try:
            from core.session_manager import SessionManager
            from datetime import datetime, timedelta
            
            sm = SessionManager.get_instance()
            sessions = sm.list_sessions()
            
            if identity_id:
                sessions = [s for s in sessions if s.get("identity_id") == identity_id]
            
            if active_within_minutes:
                cutoff = datetime.now() - timedelta(minutes=active_within_minutes)
                sessions = [s for s in sessions if s.get("last_active", datetime.min) > cutoff]
            
            result = []
            for s in sessions[:20]:
                result.append({
                    "session_key": s.get("session_key"),
                    "identity_id": s.get("identity_id"),
                    "channel": s.get("channel"),
                    "message_count": s.get("message_count", 0),
                    "last_active": s.get("last_active").isoformat() if s.get("last_active") else None
                })
            
            return ToolResult(True, f"找到 {len(result)} 个会话", data={"sessions": result})
        except Exception as e:
            return ToolResult(False, "", str(e))


class SessionsHistoryTool(BaseTool):
    """获取会话历史工具 - 参考 OpenClaw sessions_history"""
    
    name = "sessions_history"
    description = "获取指定会话的历史消息记录"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "session_key": {
                "type": "string",
                "description": "会话标识"
            },
            "limit": {
                "type": "integer",
                "description": "返回的消息数量限制（默认20）"
            }
        },
        "required": ["session_key"]
    }
    
    async def execute(self, user: User, session_key: str, limit: int = 20) -> ToolResult:
        try:
            from core.session_manager import SessionManager
            
            sm = SessionManager.get_instance()
            history = sm.get_history(session_key, limit)
            
            messages = []
            for msg in history:
                messages.append({
                    "role": msg.get("role"),
                    "content": msg.get("content"),
                    "created_at": msg.get("timestamp").isoformat() if msg.get("timestamp") else None
                })
            
            return ToolResult(True, f"获取到 {len(messages)} 条记录", data={"messages": messages})
        except Exception as e:
            return ToolResult(False, "", str(e))


class SessionsSendTool(BaseTool):
    """跨会话发送消息工具 - 参考 OpenClaw sessions_send"""
    
    name = "sessions_send"
    description = "向其他会话发送消息，用于跨会话通信"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "session_key": {
                "type": "string",
                "description": "目标会话标识"
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容"
            }
        },
        "required": ["session_key", "message"]
    }
    
    async def execute(self, user: User, session_key: str, message: str) -> ToolResult:
        try:
            from core.session_manager import SessionManager
            from models import Message, Source, User as MsgUser, UserLevel
            
            sm = SessionManager.get_instance()
            
            target_session = sm.get_session(session_key)
            if not target_session:
                return ToolResult(False, "", f"会话不存在: {session_key}")
            
            system_user = MsgUser(user_id="system", level=UserLevel.OWNER)
            system_message = Message(
                message_id=f"sys_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                content=f"[跨会话消息] {user.user_id}: {message}",
                user=system_user,
                source=Source.CLI
            )
            
            sm.add_message(session_key, system_message)
            
            return ToolResult(True, f"消息已发送到会话: {session_key}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class SessionStatusTool(BaseTool):
    """会话状态工具 - 参考 OpenClaw session_status"""
    
    name = "session_status"
    description = "显示当前会话的状态信息（使用量、时间、模型等）"
    parameters = {
        "type": "object",
        "properties": {}
    }
    
    async def execute(self, user: User) -> ToolResult:
        try:
            from core.session_manager import SessionManager
            from datetime import datetime
            
            sm = SessionManager.get_instance()
            current_session = sm.get_current_session(user.user_id)
            
            if not current_session:
                return ToolResult(True, "当前无活跃会话", data={"active": False})
            
            status = {
                "active": True,
                "session_key": current_session.get("session_key"),
                "identity_id": current_session.get("identity_id"),
                "message_count": current_session.get("message_count", 0),
                "created_at": current_session.get("created_at").isoformat() if current_session.get("created_at") else None,
                "last_active": current_session.get("last_active").isoformat() if current_session.get("last_active") else None,
                "user_level": user.level.value if user.level else "stranger"
            }
            
            return ToolResult(True, "会话状态", data=status)
        except Exception as e:
            return ToolResult(False, "", str(e))


class CronTool(BaseTool):
    """定时任务工具 - 参考 OpenClaw cron"""
    
    name = "cron"
    description = "管理定时任务和提醒。用于设置提醒时，将systemEvent文本写成提醒内容，包含相关上下文"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "remove", "clear"],
                "description": "操作类型：list列出任务，add添加任务，remove删除任务，clear清空任务"
            },
            "time": {
                "type": "string",
                "description": "触发时间（仅add时需要），如'2024-06-15 14:00'或'tomorrow 9am'"
            },
            "message": {
                "type": "string",
                "description": "提醒内容（仅add时需要）"
            },
            "job_id": {
                "type": "string",
                "description": "任务ID（仅remove时需要）"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, user: User, action: str, time: str = None, message: str = None, job_id: str = None) -> ToolResult:
        try:
            from core.heartbeat import HeartbeatManager
            
            hm = HeartbeatManager.get_instance()
            
            if action == "list":
                jobs = hm.list_jobs(user.user_id)
                return ToolResult(True, f"当前有 {len(jobs)} 个定时任务", data={"jobs": jobs})
            
            elif action == "add":
                if not time or not message:
                    return ToolResult(False, "", "添加任务需要 time 和 message 参数")
                
                job = hm.add_job(user.user_id, time, message)
                return ToolResult(True, f"✅ 已添加定时任务，将在 {time} 提醒", data={"job_id": job.job_id})
            
            elif action == "remove":
                if not job_id:
                    return ToolResult(False, "", "删除任务需要 job_id 参数")
                
                hm.remove_job(job_id)
                return ToolResult(True, f"✅ 已删除定时任务: {job_id}")
            
            elif action == "clear":
                hm.clear_jobs(user.user_id)
                return ToolResult(True, "✅ 已清空所有定时任务")
            
            else:
                return ToolResult(False, "", f"未知操作: {action}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class MessageTool(BaseTool):
    """消息发送工具 - 参考 OpenClaw message"""
    
    name = "message"
    description = "发送消息到指定渠道，支持主动发送和渠道操作"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send", "reply"],
                "description": "操作类型：send发送新消息，reply回复消息"
            },
            "to": {
                "type": "string",
                "description": "目标用户或群组ID"
            },
            "message": {
                "type": "string",
                "description": "消息内容"
            },
            "channel": {
                "type": "string",
                "description": "目标渠道（如cli、qq、telegram），不填则使用当前渠道"
            }
        },
        "required": ["action", "message"]
    }
    
    async def execute(self, user: User, action: str, message: str, to: str = None, channel: str = None) -> ToolResult:
        try:
            from core.gateway import UnifiedGateway
            
            gateway = UnifiedGateway.get_instance()
            
            if action == "send":
                if not to:
                    return ToolResult(False, "", "发送消息需要 to 参数")
                
                await gateway.send_message(
                    channel=channel or "cli",
                    target=to,
                    content=message
                )
                return ToolResult(True, f"✅ 消息已发送到 {to}")
            
            elif action == "reply":
                return ToolResult(True, "消息将在当前会话中回复")
            
            else:
                return ToolResult(False, "", f"未知操作: {action}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class GatewayTool(BaseTool):
    """网关控制工具 - 参考 OpenClaw gateway"""
    
    name = "gateway"
    description = "重启、应用配置或更新运行中的XiaoMengCore进程 - 仅主人可用"
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "restart", "reload_config"],
                "description": "操作类型：status查看状态，restart重启，reload_config重载配置"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, user: User, action: str) -> ToolResult:
        try:
            if action == "status":
                return ToolResult(True, "网关运行中", data={"status": "running"})
            
            elif action == "restart":
                return ToolResult(True, "⚠️ 重启请求已记录，需要手动执行")
            
            elif action == "reload_config":
                from config import ConfigManager
                ConfigManager.get_instance().reload()
                return ToolResult(True, "✅ 配置已重新加载")
            
            else:
                return ToolResult(False, "", f"未知操作: {action}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class ImageTool(BaseTool):
    """图像分析工具 - 参考 OpenClaw image"""
    
    name = "image"
    description = "使用配置的图像模型分析图片"
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "图片路径或URL"
            },
            "prompt": {
                "type": "string",
                "description": "分析提示词（可选）"
            }
        },
        "required": ["image_path"]
    }
    
    async def execute(self, user: User, image_path: str, prompt: str = "描述这张图片") -> ToolResult:
        try:
            from core.model_layer import ModelLayerRouter, ModelLayer, ModelRole
            
            router = ModelLayerRouter.get_instance()
            adapter = router.get_available_adapter(ModelLayer.SPECIAL, ModelRole.VISION)
            
            if not adapter:
                return ToolResult(False, "", "没有可用的视觉模型")
            
            import base64
            from pathlib import Path
            
            if image_path.startswith("http"):
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_path) as resp:
                        image_data = await resp.read()
                image_base64 = base64.b64encode(image_data).decode()
            else:
                path = Path(image_path).expanduser()
                if not path.exists():
                    return ToolResult(False, "", f"图片不存在: {image_path}")
                with open(path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode()
            
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            }]
            
            response = await adapter.chat(messages, "你是一个图像分析专家。")
            
            return ToolResult(True, response.content, data={"model": response.model_name})
        except Exception as e:
            return ToolResult(False, "", str(e))


class SessionsSpawnTool(BaseTool):
    """创建子Agent会话工具 - 参考 OpenClaw sessions_spawn"""
    
    name = "sessions_spawn"
    description = """Spawn a sub-agent session for parallel or complex work.

Sub-agent types:
- thinker: Deep analysis, complex reasoning (Brain layer)
- coder: Code generation, debugging, refactoring (Special layer)
- vision: Image analysis, OCR (Special layer)
- reasoning: Step-by-step problem solving (Special layer)

Use subagents tool to check status, steer, or kill spawned agents."""
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "agent_type": {
                "type": "string",
                "enum": ["thinker", "coder", "vision", "reasoning"],
                "description": "Type of sub-agent to spawn"
            },
            "task": {
                "type": "string",
                "description": "Task description for the sub-agent"
            },
            "context": {
                "type": "object",
                "description": "Optional context (files, data) for the task"
            }
        },
        "required": ["agent_type", "task"]
    }
    
    async def execute(self, user: User, agent_type: str, task: str, context: Dict = None) -> ToolResult:
        try:
            from core.subagent import SubagentRegistry, SubagentType, SubagentExecutor
            
            registry = SubagentRegistry.get_instance()
            executor = SubagentExecutor(registry)
            
            type_map = {
                "thinker": SubagentType.THINKER,
                "coder": SubagentType.CODER,
                "vision": SubagentType.VISION,
                "reasoning": SubagentType.REASONING
            }
            
            subagent_type = type_map.get(agent_type)
            if not subagent_type:
                return ToolResult(False, "", f"Unknown agent type: {agent_type}")
            
            session_key = f"main:{user.user_id}"
            
            run = await executor.spawn_and_execute(
                agent_type=subagent_type,
                task=task,
                parent_session_key=session_key,
                context=context
            )
            
            return ToolResult(
                True,
                f"✅ 已创建子Agent ({agent_type})，正在后台执行任务",
                data={
                    "run_id": run.run_id,
                    "agent_type": agent_type,
                    "status": run.status.value,
                    "task_preview": task[:100] + "..." if len(task) > 100 else task
                }
            )
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", str(e))


class SubagentsTool(BaseTool):
    """子Agent管理工具 - 参考 OpenClaw subagents"""
    
    name = "subagents"
    description = """List, steer, or kill sub-agent runs for this session.

Actions:
- list: Show all active sub-agents and their status
- steer: Send guidance to a running sub-agent
- kill: Terminate a sub-agent

Do NOT poll `subagents list` in a loop; only check status on-demand."""
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "steer", "kill"],
                "description": "Action to perform"
            },
            "run_id": {
                "type": "string",
                "description": "Run ID (required for steer/kill)"
            },
            "message": {
                "type": "string",
                "description": "Guidance message (required for steer)"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, user: User, action: str, run_id: str = None, message: str = None) -> ToolResult:
        try:
            from core.subagent import SubagentRegistry, SubagentStatus, SubagentExecutor
            
            registry = SubagentRegistry.get_instance()
            session_key = f"main:{user.user_id}"
            
            if action == "list":
                runs = registry.list_runs(parent_session_key=session_key)
                active_runs = [r for r in runs if r.status in (SubagentStatus.PENDING, SubagentStatus.RUNNING)]
                
                if not active_runs:
                    return ToolResult(True, "没有活跃的子Agent", data={"runs": []})
                
                return ToolResult(
                    True,
                    f"当前有 {len(active_runs)} 个活跃的子Agent",
                    data={"runs": [r.to_dict() for r in active_runs]}
                )
            
            elif action == "steer":
                if not run_id or not message:
                    return ToolResult(False, "", "steer 需要 run_id 和 message 参数")
                
                run = registry.get(run_id)
                if not run:
                    return ToolResult(False, "", f"子Agent不存在: {run_id}")
                
                if run.status != SubagentStatus.RUNNING:
                    return ToolResult(False, "", f"子Agent状态不是运行中: {run.status.value}")
                
                run.metadata["steer_message"] = message
                
                return ToolResult(True, f"✅ 已向子Agent发送引导消息")
            
            elif action == "kill":
                if not run_id:
                    return ToolResult(False, "", "kill 需要 run_id 参数")
                
                run = registry.get(run_id)
                if not run:
                    return ToolResult(False, "", f"子Agent不存在: {run_id}")
                
                executor = SubagentExecutor(registry)
                executor.cancel(run_id)
                registry.kill(run_id)
                
                return ToolResult(True, f"✅ 已终止子Agent: {run_id}")
            
            else:
                return ToolResult(False, "", f"未知操作: {action}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class EditTool(BaseTool):
    """编辑文件工具 - 参考 OpenClaw edit"""
    
    name = "edit"
    description = "编辑文件，支持搜索替换和行编辑"
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径"
            },
            "old_str": {
                "type": "string",
                "description": "要替换的内容（精确匹配）"
            },
            "new_str": {
                "type": "string",
                "description": "替换后的内容"
            },
            "insert_line": {
                "type": "integer",
                "description": "在指定行号插入内容（不使用搜索替换时）"
            },
            "content": {
                "type": "string",
                "description": "要插入的内容（与insert_line配合使用）"
            }
        },
        "required": ["path"]
    }
    
    async def execute(self, user: User, path: str, old_str: str = None, new_str: str = None,
                     insert_line: int = None, content: str = None) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            
            if not file_path.exists():
                return ToolResult(False, "", f"文件不存在: {path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            if old_str is not None and new_str is not None:
                if old_str not in file_content:
                    return ToolResult(False, "", f"未找到要替换的内容")
                
                new_content = file_content.replace(old_str, new_str, 1)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                return ToolResult(True, f"已编辑文件: {path}")
            
            elif insert_line is not None and content is not None:
                lines = file_content.split('\n')
                
                if insert_line < 0:
                    insert_line = len(lines) + insert_line + 1
                
                lines.insert(insert_line, content)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                
                return ToolResult(True, f"已在第 {insert_line} 行插入内容")
            
            else:
                return ToolResult(False, "", "需要提供 (old_str, new_str) 或 (insert_line, content)")
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class ApplyPatchTool(BaseTool):
    """多文件补丁工具 - 参考 OpenClaw apply_patch"""
    
    name = "apply_patch"
    description = """Apply a multi-file patch. Creates files if they don't exist.

The patch format follows unified diff style:
--- path/to/old_file
+++ path/to/new_file
@@ -start,count +start,count @@
 context
-removed line
+added line
 context

Multiple files can be included in one patch."""
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "patch": {
                "type": "string",
                "description": "Unified diff format patch content"
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without applying"
            }
        },
        "required": ["patch"]
    }
    
    async def execute(self, user: User, patch: str, dry_run: bool = False) -> ToolResult:
        try:
            results = []
            current_file = None
            current_hunks = []
            file_changes = {}
            
            lines = patch.split('\n')
            i = 0
            
            while i < len(lines):
                line = lines[i]
                
                if line.startswith('--- '):
                    old_path = line[4:].strip()
                    if old_path.startswith('a/'):
                        old_path = old_path[2:]
                    i += 1
                    
                    if i < len(lines) and lines[i].startswith('+++ '):
                        new_path = lines[i][4:].strip()
                        if new_path.startswith('b/'):
                            new_path = new_path[2:]
                        current_file = new_path
                        current_hunks = []
                        i += 1
                    continue
                
                elif line.startswith('@@ '):
                    match = re.match(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
                    if match:
                        old_start = int(match.group(1))
                        new_start = int(match.group(2))
                        hunk = {
                            'old_start': old_start,
                            'new_start': new_start,
                            'lines': []
                        }
                        i += 1
                        
                        while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('---'):
                            hunk_line = lines[i]
                            if hunk_line.startswith(' ') or hunk_line.startswith('-') or hunk_line.startswith('+'):
                                hunk['lines'].append(hunk_line)
                            i += 1
                        
                        current_hunks.append(hunk)
                        
                        if current_file:
                            file_changes[current_file] = current_hunks
                        continue
                
                i += 1
            
            if not file_changes:
                return ToolResult(False, "", "无法解析补丁格式")
            
            if dry_run:
                preview = []
                for file_path, hunks in file_changes.items():
                    preview.append(f"文件: {file_path}")
                    for hunk in hunks:
                        preview.append(f"  行 {hunk['new_start']}: {len([l for l in hunk['lines'] if l.startswith('+')])} 添加, {len([l for l in hunk['lines'] if l.startswith('-')])} 删除")
                return ToolResult(True, "预览模式:\n" + "\n".join(preview), data={"files": list(file_changes.keys())})
            
            for file_path, hunks in file_changes.items():
                path = Path(file_path).expanduser().resolve()
                
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    lines = content.split('\n')
                else:
                    lines = []
                    path.parent.mkdir(parents=True, exist_ok=True)
                
                for hunk in reversed(hunks):
                    new_lines = []
                    for hunk_line in hunk['lines']:
                        if hunk_line.startswith(' '):
                            new_lines.append(hunk_line[1:])
                        elif hunk_line.startswith('+'):
                            new_lines.append(hunk_line[1:])
                    
                    start = hunk['new_start'] - 1
                    lines = lines[:start] + new_lines + lines[start + len([l for l in hunk['lines'] if l.startswith('-')]):]
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                
                results.append(f"✅ {file_path}")
            
            return ToolResult(True, f"补丁已应用:\n" + "\n".join(results), data={"files": list(file_changes.keys())})
            
        except Exception as e:
            return ToolResult(False, "", f"应用补丁失败: {str(e)}")


class ProcessTool(BaseTool):
    """后台进程管理工具 - 参考 OpenClaw process"""
    
    name = "process"
    description = """Manage background processes.

Actions:
- start: Start a new background process
- list: List all running processes
- output: Get stdout/stderr from a process
- kill: Terminate a process
- wait: Wait for process to complete"""
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "list", "output", "kill", "wait"],
                "description": "Action to perform"
            },
            "command": {
                "type": "string",
                "description": "Command to run (for start)"
            },
            "process_id": {
                "type": "string",
                "description": "Process ID (for output/kill/wait)"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (for wait)"
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (for start)"
            }
        },
        "required": ["action"]
    }
    
    _processes: Dict[str, Dict] = {}
    _process_counter: int = 0
    
    async def execute(self, user: User, action: str, command: str = None, 
                     process_id: str = None, timeout: int = 30, cwd: str = None) -> ToolResult:
        try:
            if action == "start":
                if not command:
                    return ToolResult(False, "", "start 需要 command 参数")
                
                ProcessTool._process_counter += 1
                pid = f"proc_{ProcessTool._process_counter}"
                
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd
                )
                
                ProcessTool._processes[pid] = {
                    "process": process,
                    "command": command,
                    "started_at": datetime.now().isoformat(),
                    "status": "running"
                }
                
                return ToolResult(
                    True, 
                    f"✅ 已启动进程: {pid}\n命令: {command}",
                    data={"process_id": pid, "command": command}
                )
            
            elif action == "list":
                processes = []
                for pid, info in ProcessTool._processes.items():
                    proc = info["process"]
                    status = "running" if proc.returncode is None else f"exited({proc.returncode})"
                    processes.append({
                        "process_id": pid,
                        "command": info["command"],
                        "started_at": info["started_at"],
                        "status": status
                    })
                
                return ToolResult(
                    True,
                    f"当前有 {len(processes)} 个进程",
                    data={"processes": processes}
                )
            
            elif action == "output":
                if not process_id or process_id not in ProcessTool._processes:
                    return ToolResult(False, "", f"进程不存在: {process_id}")
                
                info = ProcessTool._processes[process_id]
                proc = info["process"]
                
                try:
                    stdout = ""
                    stderr = ""
                    
                    if proc.stdout:
                        try:
                            data = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.1)
                            stdout = data.decode('utf-8', errors='replace')
                        except asyncio.TimeoutError:
                            pass
                    
                    if proc.stderr:
                        try:
                            data = await asyncio.wait_for(proc.stderr.read(4096), timeout=0.1)
                            stderr = data.decode('utf-8', errors='replace')
                        except asyncio.TimeoutError:
                            pass
                    
                    return ToolResult(
                        True,
                        f"stdout:\n{stdout}\nstderr:\n{stderr}" if stdout or stderr else "暂无输出",
                        data={"stdout": stdout, "stderr": stderr}
                    )
                except Exception as e:
                    return ToolResult(False, "", str(e))
            
            elif action == "kill":
                if not process_id or process_id not in ProcessTool._processes:
                    return ToolResult(False, "", f"进程不存在: {process_id}")
                
                info = ProcessTool._processes[process_id]
                proc = info["process"]
                
                if proc.returncode is None:
                    proc.kill()
                    info["status"] = "killed"
                    return ToolResult(True, f"✅ 已终止进程: {process_id}")
                else:
                    return ToolResult(True, f"进程已结束: {process_id}")
            
            elif action == "wait":
                if not process_id or process_id not in ProcessTool._processes:
                    return ToolResult(False, "", f"进程不存在: {process_id}")
                
                info = ProcessTool._processes[process_id]
                proc = info["process"]
                
                try:
                    returncode = await asyncio.wait_for(proc.wait(), timeout=timeout)
                    info["status"] = f"exited({returncode})"
                    
                    stdout, stderr = await proc.communicate()
                    
                    return ToolResult(
                        True,
                        f"进程结束，退出码: {returncode}\n输出:\n{stdout.decode('utf-8', errors='replace')}",
                        data={
                            "returncode": returncode,
                            "stdout": stdout.decode('utf-8', errors='replace'),
                            "stderr": stderr.decode('utf-8', errors='replace')
                        }
                    )
                except asyncio.TimeoutError:
                    return ToolResult(True, f"进程仍在运行，等待超时（{timeout}秒）")
            
            else:
                return ToolResult(False, "", f"未知操作: {action}")
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class BrowserTool(BaseTool):
    """浏览器控制工具 - 参考 OpenClaw browser"""
    
    name = "browser"
    description = """Control a web browser for navigation, interaction, and scraping.

Actions:
- navigate: Go to a URL
- click: Click an element
- type: Type text into an element
- screenshot: Take a screenshot
- content: Get page content
- wait: Wait for element or condition"""
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["navigate", "click", "type", "screenshot", "content", "wait"],
                "description": "Action to perform"
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to"
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for element"
            },
            "text": {
                "type": "string",
                "description": "Text to type"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds"
            }
        },
        "required": ["action"]
    }
    
    _browser_instance = None
    _current_url = None
    
    async def execute(self, user: User, action: str, url: str = None, selector: str = None,
                     text: str = None, timeout: int = 30) -> ToolResult:
        try:
            if action == "navigate":
                if not url:
                    return ToolResult(False, "", "navigate 需要 url 参数")
                
                try:
                    import aiohttp
                    from bs4 import BeautifulSoup
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }) as response:
                            if response.status != 200:
                                return ToolResult(False, "", f"请求失败: HTTP {response.status}")
                            
                            html = await response.text()
                    
                    BrowserTool._current_url = url
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    for script in soup(["script", "style", "nav", "footer"]):
                        script.decompose()
                    
                    content = soup.get_text(separator='\n', strip=True)
                    lines = [line.strip() for line in content.split('\n') if line.strip()]
                    
                    return ToolResult(
                        True,
                        f"已导航到: {url}\n\n内容预览:\n" + '\n'.join(lines[:50]),
                        data={"url": url, "title": soup.title.string if soup.title else None}
                    )
                    
                except ImportError:
                    return ToolResult(False, "", "请安装 aiohttp 和 beautifulsoup4")
            
            elif action == "content":
                if not BrowserTool._current_url:
                    return ToolResult(False, "", "没有当前页面，请先使用 navigate")
                
                import aiohttp
                from bs4 import BeautifulSoup
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(BrowserTool._current_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }) as response:
                        html = await response.text()
                
                soup = BeautifulSoup(html, 'html.parser')
                
                if selector:
                    elements = soup.select(selector)
                    content = '\n'.join([el.get_text(strip=True) for el in elements])
                else:
                    for script in soup(["script", "style"]):
                        script.decompose()
                    content = soup.get_text(separator='\n', strip=True)
                
                return ToolResult(True, content[:5000], data={"url": BrowserTool._current_url})
            
            elif action == "screenshot":
                return ToolResult(
                    True, 
                    "截图功能需要安装 playwright 或 selenium。\n"
                    "请运行: pip install playwright && playwright install",
                    data={"note": "screenshot requires playwright"}
                )
            
            elif action == "click" or action == "type":
                return ToolResult(
                    True,
                    f"{action} 操作需要安装 playwright 或 selenium。\n"
                    "当前仅支持 navigate 和 content 操作。",
                    data={"note": "interactive actions require playwright"}
                )
            
            elif action == "wait":
                return ToolResult(True, f"等待 {timeout} 秒...", data={"waited": timeout})
            
            else:
                return ToolResult(False, "", f"未知操作: {action}")
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class AgentsListTool(BaseTool):
    """列出所有Agent工具 - 参考 OpenClaw agents_list"""
    
    name = "agents_list"
    description = "列出所有活跃的Agent实例，包括主Agent和子Agent"
    permission = ToolPermission.WHITELIST_AND_ABOVE
    parameters = {
        "type": "object",
        "properties": {
            "include_completed": {
                "type": "boolean",
                "description": "是否包含已完成的Agent"
            }
        }
    }
    
    async def execute(self, user: User, include_completed: bool = False) -> ToolResult:
        try:
            from core.subagent import SubagentRegistry, SubagentStatus
            
            registry = SubagentRegistry.get_instance()
            all_runs = registry.list_runs()
            
            if not include_completed:
                active_statuses = [SubagentStatus.PENDING, SubagentStatus.RUNNING]
                all_runs = [r for r in all_runs if r.status in active_statuses]
            
            agents = []
            
            agents.append({
                "agent_id": "main",
                "type": "main",
                "status": "running",
                "session_key": f"main:{user.user_id}",
                "created_at": None,
                "task": "主Agent实例"
            })
            
            for run in all_runs:
                agents.append({
                    "agent_id": run.run_id,
                    "type": run.agent_type.value,
                    "status": run.status.value,
                    "session_key": run.parent_session_key,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "task": run.task[:100] + "..." if len(run.task) > 100 else run.task
                })
            
            return ToolResult(
                True,
                f"找到 {len(agents)} 个Agent实例",
                data={"agents": agents, "count": len(agents)}
            )
            
        except Exception as e:
            return ToolResult(False, "", str(e))


class NodesTool(BaseTool):
    """节点管理工具 - 参考 OpenClaw nodes"""
    
    name = "nodes"
    description = """List or manage XiaoMengCore nodes.

Actions:
- list: List all available nodes
- status: Get status of a specific node
- connect: Connect to a remote node"""
    permission = ToolPermission.OWNER_ONLY
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "status", "connect"],
                "description": "Action to perform"
            },
            "node_id": {
                "type": "string",
                "description": "Node ID (for status/connect)"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, user: User, action: str, node_id: str = None) -> ToolResult:
        try:
            if action == "list":
                nodes = [
                    {
                        "node_id": "local",
                        "type": "local",
                        "status": "online",
                        "models": ["basic", "brain", "special"]
                    }
                ]
                
                return ToolResult(
                    True,
                    f"找到 {len(nodes)} 个节点",
                    data={"nodes": nodes}
                )
            
            elif action == "status":
                if not node_id:
                    return ToolResult(False, "", "status 需要 node_id 参数")
                
                if node_id == "local":
                    from core.model_layer import ModelLayerRouter
                    router = ModelLayerRouter.get_instance()
                    status = router.get_status()
                    
                    return ToolResult(
                        True,
                        "本地节点状态",
                        data={"node_id": "local", "status": "online", "models": status}
                    )
                else:
                    return ToolResult(False, "", f"节点不存在: {node_id}")
            
            elif action == "connect":
                return ToolResult(True, "远程节点连接功能尚未实现")
            
            else:
                return ToolResult(False, "", f"未知操作: {action}")
                
        except Exception as e:
            return ToolResult(False, "", str(e))


SILENT_REPLY_TOKEN = "..."


class ToolRegistry:
    """
    工具注册表
    
    管理所有可用工具
    """
    
    _instance: Optional["ToolRegistry"] = None
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """注册内置工具"""
        builtin_tools = [
            ReadTool(),
            WriteTool(),
            EditTool(),
            ApplyPatchTool(),
            ExecTool(),
            ProcessTool(),
            GrepTool(),
            FindTool(),
            LsTool(),
            DeleteTool(),
            UpdatePersonaTool(),
            CreateSkillTool(),
            MemorySearchTool(),
            MemoryGetTool(),
            AddMemoryTool(),
            GetHistoryTool(),
            RollbackTool(),
            GetDiffTool(),
            GetPendingChangesTool(),
            ConfirmChangeTool(),
            RejectChangeTool(),
            DownloadTool(),
            WebFetchTool(),
            WebSearchTool(),
            BrowserTool(),
            RecordErrorTool(),
            RecordCorrectionTool(),
            RecordBestPracticeTool(),
            RecordFeatureRequestTool(),
            GetLearningsTool(),
            RegisterModelTool(),
            UnregisterModelTool(),
            GetModelsStatusTool(),
            AddScheduleTool(),
            GetScheduleTool(),
            AddTodoTool(),
            ListTodoTool(),
            CompleteTodoTool(),
            GetWeatherTool(),
            GetNewsTool(),
            AddSpecialDayTool(),
            SetPreferenceTool(),
            SessionsListTool(),
            SessionsHistoryTool(),
            SessionsSendTool(),
            SessionStatusTool(),
            SessionsSpawnTool(),
            SubagentsTool(),
            AgentsListTool(),
            CronTool(),
            MessageTool(),
            GatewayTool(),
            ImageTool(),
            NodesTool()
        ]
        
        for tool in builtin_tools:
            self._tools[tool.name] = tool
    
    def register(self, tool: BaseTool):
        """注册工具"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def get_all_tools(self) -> List[BaseTool]:
        """获取所有工具"""
        return list(self._tools.values())
    
    def get_tools_for_user(self, user: User) -> List[BaseTool]:
        """获取用户可用的工具"""
        return [t for t in self._tools.values() if t.check_permission(user)]
    
    def get_tools_schema(self, user: User) -> List[Dict]:
        """获取用户可用工具的 schema"""
        return [t.get_schema() for t in self.get_tools_for_user(user)]
    
    def get_tools_schema_by_names(self, tool_names: List[str]) -> List[Dict]:
        """根据工具名称列表获取工具 schema"""
        schemas = []
        for name in tool_names:
            tool = self._tools.get(name)
            if tool:
                schemas.append(tool.get_schema())
        return schemas
    
    def get_tools_by_profile(self, user: User, profile_name: str = "full") -> List[BaseTool]:
        """根据工具策略获取工具"""
        from core.tool_policy import ToolPolicy, ToolPolicyConfig, ToolProfile
        
        available_tools = self.get_tools_for_user(user)
        tool_names = [t.name for t in available_tools]
        
        try:
            profile = ToolProfile(profile_name)
        except ValueError:
            profile = ToolProfile.FULL
        
        config = ToolPolicyConfig(profile=profile)
        policy = ToolPolicy(config)
        
        allowed_names = policy.get_allowed_tools(tool_names)
        
        return [t for t in available_tools if t.name in allowed_names]
    
    def get_tools_schema_by_profile(self, user: User, profile_name: str = "full") -> List[Dict]:
        """根据工具策略获取工具 schema"""
        tools = self.get_tools_by_profile(user, profile_name)
        return [t.get_schema() for t in tools]
    
    async def execute_with_loop_detection(
        self, 
        name: str, 
        user: User, 
        session_key: str,
        **kwargs
    ) -> ToolResult:
        """执行工具并进行循环检测"""
        from core.tool_policy import get_tool_loop_detector, ToolPolicyConfig
        
        detector = get_tool_loop_detector()
        
        is_loop, reason = detector.check_session_loop(session_key)
        if is_loop:
            return ToolResult(
                False, 
                f"⚠️ 工具调用循环检测: {reason}\n请尝试不同的方法或简化任务。",
                error="loop_detected"
            )
        
        detector.record_call(session_key, name, kwargs)
        
        result = await self.execute(name, user, **kwargs)
        
        return result
    
    def get_tool_groups(self) -> Dict[str, List[str]]:
        """获取所有工具组"""
        from core.tool_policy import TOOL_GROUPS
        return TOOL_GROUPS
    
    def get_tool_profiles(self) -> Dict[str, Dict]:
        """获取所有工具策略"""
        from core.tool_policy import TOOL_PROFILES
        return TOOL_PROFILES
    
    async def execute(self, name: str, user: User, **kwargs) -> ToolResult:
        """执行工具"""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(False, "", f"工具不存在: {name}")
        
        if not tool.check_permission(user):
            return ToolResult(False, "", "权限不足")
        
        return await tool.execute(user, **kwargs)
    
    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
