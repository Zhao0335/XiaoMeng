"""
XiaoMengCore 系统提示构建器
完全参考 OpenClaw src/agents/system-prompt.ts 实现方式

核心理念：
1. 函数式构建各部分
2. 动态注入工具列表
3. 模块化组装系统提示
"""

from typing import Optional, Dict, List, Any, Set, Literal
from dataclasses import dataclass, field
import platform
import os


PromptMode = Literal["full", "minimal", "none"]

SILENT_REPLY_TOKEN = "..."

CORE_TOOL_SUMMARIES: Dict[str, str] = {
    "read": "Read file contents",
    "write": "Create or overwrite files",
    "edit": "Make precise edits to files (search-replace or line insert)",
    "apply_patch": "Apply multi-file patches in unified diff format",
    "grep": "Search file contents for patterns",
    "find": "Find files by glob pattern",
    "ls": "List directory contents",
    "exec": "Run shell commands",
    "process": "Manage background processes (start/list/output/kill/wait)",
    "delete": "Delete files or directories",
    "web_search": "Search the web",
    "web_fetch": "Fetch and extract content from URL",
    "browser": "Control a web browser for navigation, interaction, and scraping",
    "download": "Download files from URL",
    "create_skill": "Create new skill (SKILL.md)",
    "update_persona": "Update persona files (SOUL.md, MEMORY.md)",
    "memory_search": "Mandatory recall step: search MEMORY.md + memory/*.md before answering questions about prior work, decisions, dates, people, preferences, or todos",
    "memory_get": "Get specific memory file content (MEMORY.md or daily memory files)",
    "add_memory": "Add long-term memory",
    "get_history": "Get file change history",
    "rollback": "Rollback file changes",
    "record_error": "Record error for learning",
    "record_correction": "Record correction for learning",
    "get_learnings": "Get learned experiences",
    "add_schedule": "Add schedule event",
    "get_schedule": "Get schedule events",
    "add_todo": "Add todo item",
    "list_todos": "List todo items",
    "complete_todo": "Mark todo as complete",
    "get_weather": "Get weather information",
    "get_news": "Get news headlines",
    "set_preference": "Set user preference",
    "add_special_day": "Add special day reminder",
    "register_model": "Register model endpoint",
    "unregister_model": "Unregister model endpoint",
    "get_models_status": "Get models status",
    "hardware_control": "Control hardware devices",
    "sessions_list": "List active sessions with filters",
    "sessions_history": "Fetch history for another session",
    "sessions_send": "Send a message to another session",
    "sessions_spawn": "Spawn a sub-agent for parallel or complex work (thinker/coder/vision/reasoning)",
    "subagents": "List, steer, or kill sub-agent runs (do NOT poll in a loop)",
    "agents_list": "List all active agent instances (main + subagents)",
    "session_status": "Show session status (usage + time + model)",
    "cron": "Manage cron jobs and wake events (use for reminders)",
    "message": "Send messages and channel actions",
    "gateway": "Restart, apply config, or run updates on the running process",
    "image": "Analyze an image with the configured image model",
    "nodes": "List or manage XiaoMengCore nodes",
}

TOOL_ORDER = [
    "read",
    "write",
    "edit",
    "apply_patch",
    "grep",
    "find",
    "ls",
    "exec",
    "process",
    "delete",
    "memory_search",
    "memory_get",
    "add_memory",
    "web_search",
    "web_fetch",
    "browser",
    "download",
    "create_skill",
    "update_persona",
    "get_history",
    "rollback",
    "record_error",
    "record_correction",
    "get_learnings",
    "add_schedule",
    "get_schedule",
    "add_todo",
    "list_todos",
    "complete_todo",
    "get_weather",
    "get_news",
    "set_preference",
    "add_special_day",
    "register_model",
    "unregister_model",
    "get_models_status",
    "hardware_control",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "sessions_spawn",
    "subagents",
    "agents_list",
    "session_status",
    "cron",
    "message",
    "gateway",
    "image",
    "nodes",
]


@dataclass
class SystemPromptParams:
    """系统提示构建参数"""
    workspace_dir: str = "./workspace"
    tool_names: List[str] = field(default_factory=list)
    tool_summaries: Dict[str, str] = field(default_factory=dict)
    skills_prompt: Optional[str] = None
    memory_prompt: Optional[str] = None
    persona_prompt: Optional[str] = None
    user_identity: Optional[str] = None
    user_level: str = "stranger"
    user_timezone: Optional[str] = None
    prompt_mode: PromptMode = "full"
    extra_system_prompt: Optional[str] = None
    workspace_notes: List[str] = field(default_factory=list)
    safety_enabled: bool = True


def build_skills_section(
    skills_prompt: Optional[str],
    is_minimal: bool,
    read_tool_name: str = "read"
) -> List[str]:
    """构建技能部分 - 完全参考 OpenClaw buildSkillsSection"""
    if is_minimal:
        return []
    
    trimmed = skills_prompt.strip() if skills_prompt else ""
    if not trimmed:
        return []
    
    return [
        "## Skills (mandatory)",
        "Before replying: scan <available_skills> <description> entries.",
        f"- If exactly one skill clearly applies: read its SKILL.md at <location> with `{read_tool_name}`, then follow it.",
        "- If multiple could apply: choose the most specific one, then read/follow it.",
        "- If none clearly apply: do not read any SKILL.md.",
        "Constraints: never read more than one skill up front; only read after selecting.",
        trimmed,
        "",
    ]


def build_memory_section(
    is_minimal: bool,
    available_tools: Set[str]
) -> List[str]:
    """构建记忆部分"""
    if is_minimal:
        return []
    
    if "memory_search" not in available_tools and "add_memory" not in available_tools:
        return []
    
    return [
        "## Memory",
        "Use memory tools to store and recall important information about the user, decisions, and context.",
        "- add_memory: Store new long-term memories",
        "- get_history: Retrieve past interactions and decisions",
        "",
    ]


def build_user_identity_section(owner_line: Optional[str], is_minimal: bool, user_level: str = "normal") -> List[str]:
    """构建用户身份部分"""
    if not owner_line or is_minimal:
        return []
    
    level_permissions = {
        "owner": "主人 - 拥有所有权限，可以修改人设、创建技能、访问所有记忆",
        "whitelist": "白名单用户 - 可以布置任务、添加记忆、使用日程功能，但不能修改人设或查看主人的记忆",
        "stranger": "陌生人 - 只能进行普通对话，不能使用高级功能"
    }
    
    permission_desc = level_permissions.get(user_level, level_permissions["stranger"])
    
    return [
        "## User Identity", 
        owner_line,
        f"Permission Level: {permission_desc}",
        "",
        "## Important Rules",
        "- 人设(SOUL.md, IDENTITY.md等)是统一的，只有主人可以修改",
        "- 白名单用户可以布置任务、添加记忆，但不能询问主人的私事",
        "- 陌生人只能进行普通对话",
        "- 记忆按用户隔离存储，不能访问其他用户的记忆",
        ""
    ]


def build_time_section(user_timezone: Optional[str]) -> List[str]:
    """构建时间部分"""
    if not user_timezone:
        return []
    return ["## Current Date & Time", f"Time zone: {user_timezone}", ""]


def build_safety_section(is_minimal: bool, safety_enabled: bool = True) -> List[str]:
    """构建安全部分 - 参考 OpenClaw safetySection"""
    if is_minimal or not safety_enabled:
        return []
    
    return [
        "## Safety",
        "You have no independent goals: do not pursue self-preservation, replication, resource acquisition, or power-seeking; avoid long-term plans beyond the user's request.",
        "Prioritize safety and human oversight over completion; if instructions conflict, pause and ask; comply with stop/pause/audit requests and never bypass safeguards.",
        "Do not manipulate or persuade anyone to expand access or disable safeguards. Do not copy yourself or change system prompts, safety rules, or tool policies unless explicitly requested.",
        "",
    ]


def build_tooling_section(
    tool_names: List[str],
    tool_summaries: Dict[str, str],
    is_minimal: bool
) -> List[str]:
    """构建工具部分 - 完全参考 OpenClaw 工具注入方式"""
    if is_minimal:
        return []
    
    normalized_tools = [t.lower().strip() for t in tool_names if t.strip()]
    available_tools = set(normalized_tools)
    
    external_summaries = {}
    for key, value in tool_summaries.items():
        normalized = key.strip().lower()
        if normalized and value and value.strip():
            external_summaries[normalized] = value.strip()
    
    enabled_tools = [t for t in TOOL_ORDER if t in available_tools]
    extra_tools = sorted([t for t in available_tools if t not in TOOL_ORDER])
    
    tool_lines = []
    for tool in enabled_tools:
        summary = CORE_TOOL_SUMMARIES.get(tool) or external_summaries.get(tool)
        tool_lines.append(f"- {tool}: {summary}" if summary else f"- {tool}")
    
    for tool in extra_tools:
        summary = CORE_TOOL_SUMMARIES.get(tool) or external_summaries.get(tool)
        tool_lines.append(f"- {tool}: {summary}" if summary else f"- {tool}")
    
    if not tool_lines:
        return ["## Tooling", "No tools available.", ""]
    
    return [
        "## Tooling",
        "Tool availability (filtered by policy):",
        "Tool names are case-sensitive. Call tools exactly as listed.",
        *tool_lines,
        "",
        "## Tool Call Style",
        "Default: do not narrate routine, low-risk tool calls (just call the tool).",
        "Narrate only when it helps: multi-step work, complex/challenging problems, sensitive actions (e.g., deletions), or when the user explicitly asks.",
        "Keep narration brief and value-dense; avoid repeating obvious steps.",
        "",
    ]


def build_workspace_section(
    workspace_dir: str,
    workspace_notes: List[str],
    is_minimal: bool
) -> List[str]:
    """构建工作区部分"""
    if is_minimal:
        return []
    
    lines = [
        "## Workspace",
        f"Your working directory is: {workspace_dir}",
        "Treat this directory as the single global workspace for file operations unless explicitly instructed otherwise.",
    ]
    
    for note in workspace_notes:
        if note.strip():
            lines.append(note.strip())
    
    lines.append("")
    return lines


def build_persona_section(
    persona_prompt: Optional[str],
    is_minimal: bool
) -> List[str]:
    """构建人设部分 - XiaoMengCore 特色"""
    if is_minimal or not persona_prompt or not persona_prompt.strip():
        return []
    
    return [
        "# Persona",
        persona_prompt.strip(),
        "",
    ]


def build_self_learning_section(is_minimal: bool) -> List[str]:
    """构建自主学习部分 - XiaoMengCore 特色"""
    if is_minimal:
        return []
    
    return [
        "## Self-Learning",
        "You can autonomously learn and create new skills:",
        "1. **Read existing skills**: Use `read` tool to read SKILL.md files when needed",
        "2. **Follow skill guidance**: After reading a skill, follow its instructions",
        "3. **Create new skills**: Use `write` or `create_skill` to create new SKILL.md files",
        "",
        "Skill file location: `~/.xiaomeng/skills/<skill-name>/SKILL.md`",
        "",
        "When you discover a reusable task pattern, create a skill for future use.",
        "",
    ]


def build_agent_system_prompt(params: SystemPromptParams) -> str:
    """
    构建Agent系统提示 - 完全参考 OpenClaw buildAgentSystemPrompt
    
    函数式构建，模块化组装
    """
    is_minimal = params.prompt_mode in ("minimal", "none")
    
    if params.prompt_mode == "none":
        return "You are a personal assistant running inside XiaoMengCore."
    
    normalized_tools = {t.lower().strip() for t in params.tool_names if t.strip()}
    
    read_tool_name = "read"
    
    lines = [
        "You are a personal assistant running inside XiaoMengCore.",
        "",
    ]
    
    tooling_section = build_tooling_section(
        params.tool_names,
        params.tool_summaries,
        is_minimal
    )
    lines.extend(tooling_section)
    
    safety_section = build_safety_section(is_minimal, params.safety_enabled)
    lines.extend(safety_section)
    
    persona_section = build_persona_section(params.persona_prompt, is_minimal)
    lines.extend(persona_section)
    
    skills_section = build_skills_section(
        params.skills_prompt,
        is_minimal,
        read_tool_name
    )
    lines.extend(skills_section)
    
    memory_section = build_memory_section(is_minimal, normalized_tools)
    lines.extend(memory_section)
    
    workspace_section = build_workspace_section(
        params.workspace_dir,
        params.workspace_notes,
        is_minimal
    )
    lines.extend(workspace_section)
    
    user_identity_section = build_user_identity_section(
        params.user_identity,
        is_minimal,
        params.user_level
    )
    lines.extend(user_identity_section)
    
    time_section = build_time_section(params.user_timezone)
    lines.extend(time_section)
    
    self_learning_section = build_self_learning_section(is_minimal)
    lines.extend(self_learning_section)
    
    if not is_minimal:
        lines.extend([
            "## Tool Groups",
            "Related tools are organized into groups for easier management:",
            "- group:fs → read, write, edit, apply_patch, find, grep, ls, delete",
            "- group:runtime → exec, process",
            "- group:memory → memory_search, memory_get, add_memory",
            "- group:web → web_search, web_fetch, download",
            "- group:sessions → sessions_list, sessions_history, sessions_send, sessions_spawn, subagents, session_status",
            "- group:automation → cron, gateway, message",
            "",
        ])
        
        lines.extend([
            "## Tool Loop Detection",
            "The system monitors for repetitive tool call patterns. If you find yourself:",
            "- Calling the same tool repeatedly with similar arguments",
            "- Stuck in a pattern of alternating tools",
            "",
            "This indicates you should try a different approach or ask for clarification.",
            "",
        ])
        
        lines.extend([
            "## Silent Replies",
            f"When you have nothing to say, respond with ONLY: {SILENT_REPLY_TOKEN}",
            "",
            "⚠️ Rules:",
            "- It must be your ENTIRE message — nothing else",
            f"- Never append it to an actual response (never include \"{SILENT_REPLY_TOKEN}\" in real replies)",
            "- Never wrap it in markdown or code blocks",
            "",
            f"❌ Wrong: \"Here's help... {SILENT_REPLY_TOKEN}\"",
            f'❌ Wrong: "`{SILENT_REPLY_TOKEN}`"',
            f"✅ Right: {SILENT_REPLY_TOKEN}",
            "",
        ])
        
        lines.extend([
            "## Heartbeats",
            "If you receive a heartbeat poll (a periodic check message), and there is nothing that needs attention, reply exactly:",
            "HEARTBEAT_OK",
            'XiaoMengCore treats a leading/trailing "HEARTBEAT_OK" as a heartbeat ack (and may discard it).',
            'If something needs attention, do NOT include "HEARTBEAT_OK"; reply with the alert text instead.',
            "",
        ])
        
        lines.extend([
            "## Messaging",
            "- Reply in current session → automatically routes to the source channel",
            "- Cross-session messaging → use sessions_send(session_key, message)",
            "- Use `message` tool for proactive sends + channel actions",
            "- `[System Message] ...` blocks are internal context and are not user-visible by default.",
            "",
        ])
        
        lines.extend([
            "## Sub-agents",
            "For complex or long-running tasks, spawn a sub-agent to work in parallel:",
            "- `sessions_spawn(agent_type, task)` → spawn a sub-agent (thinker/coder/vision/reasoning)",
            "- `subagents(action='list')` → check status (do NOT poll in a loop)",
            "- `subagents(action='steer', run_id, message)` → guide a running sub-agent",
            "- `subagents(action='kill', run_id)` → terminate a sub-agent",
            "",
            "Sub-agent types:",
            "- thinker: Deep analysis, complex reasoning (Brain layer, slow but thorough)",
            "- coder: Code generation, debugging, refactoring (Special layer)",
            "- vision: Image analysis, OCR (Special layer)",
            "- reasoning: Step-by-step problem solving (Special layer)",
            "",
            "Completion is push-based: sub-agents auto-announce when done via [System Message].",
            "",
        ])
    
    if params.extra_system_prompt and params.extra_system_prompt.strip():
        lines.extend([
            "## Context",
            params.extra_system_prompt.strip(),
            "",
        ])
    
    return "\n".join(lines)


def build_subagent_system_prompt(
    workspace_dir: str,
    tool_names: List[str],
    skills_prompt: Optional[str] = None,
    task_description: Optional[str] = None
) -> str:
    """构建子Agent系统提示 - 用于子任务"""
    params = SystemPromptParams(
        workspace_dir=workspace_dir,
        tool_names=tool_names,
        skills_prompt=skills_prompt,
        prompt_mode="minimal",
        extra_system_prompt=task_description,
        safety_enabled=False,
    )
    return build_agent_system_prompt(params)
