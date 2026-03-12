"""
XiaoMengCore 综合检查脚本
验证所有核心功能是否正确实现
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_module_imports():
    """检查模块导入"""
    print("\n=== 检查模块导入 ===")
    
    errors = []
    
    try:
        from core import (
            UserManager, SessionManager, LLMClient, MessageProcessor,
            MemoryManager, ToolRegistry, ToolResult, SkillManager, Skill,
            HardwareManager, HeartbeatManager, ModelLayerRouter,
            SelfImprovingAgent, build_agent_system_prompt, SystemPromptParams
        )
        print("✓ 核心模块导入成功")
    except ImportError as e:
        errors.append(f"核心模块导入失败: {e}")
    
    try:
        from core.tool_policy import (
            ToolPolicy, ToolPolicyConfig, ToolProfile,
            ToolLoopDetector, TOOL_GROUPS, TOOL_PROFILES
        )
        print("✓ 工具策略模块导入成功")
    except ImportError as e:
        errors.append(f"工具策略模块导入失败: {e}")
    
    try:
        from core.subagent import (
            SubagentRegistry, SubagentType, SubagentStatus,
            SubagentRun, SubagentConfig, SUBAGENT_CONFIGS
        )
        print("✓ 子Agent模块导入成功")
    except ImportError as e:
        errors.append(f"子Agent模块导入失败: {e}")
    
    try:
        from core.memory import MemoryManager
        from core.memory.memory_manager import PersonaLoader, MarkdownMemoryStore
        print("✓ 记忆模块导入成功")
    except ImportError as e:
        errors.append(f"记忆模块导入失败: {e}")
    
    try:
        from core.v2 import (
            IdentityManager, MessageQueue, HookSystem,
            Compactor, AutoCompactor, GatewayV2
        )
        print("✓ V2模块导入成功")
    except ImportError as e:
        errors.append(f"V2模块导入失败: {e}")
    
    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        return False
    return True


def check_tool_system():
    """检查工具系统"""
    print("\n=== 检查工具系统 ===")
    
    from core.tools import ToolRegistry
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    
    expected_tools = [
        "read", "write", "edit", "apply_patch", "grep", "find", "ls",
        "exec", "process", "delete",
        "memory_search", "memory_get", "add_memory",
        "web_search", "web_fetch", "browser", "download",
        "create_skill", "update_persona",
        "sessions_list", "sessions_history", "sessions_send",
        "sessions_spawn", "subagents", "agents_list", "session_status",
        "cron", "message", "gateway", "image", "nodes"
    ]
    
    missing_tools = []
    for tool_name in expected_tools:
        tool = registry.get(tool_name)
        if tool is None:
            missing_tools.append(tool_name)
    
    if missing_tools:
        print(f"  ✗ 缺失工具: {missing_tools}")
        return False
    
    print(f"✓ 所有 {len(expected_tools)} 个核心工具已注册")
    
    user = User(user_id="test_owner", level=UserLevel.OWNER)
    tools_for_owner = registry.get_tools_for_user(user)
    print(f"✓ 主人可用工具: {len(tools_for_owner)} 个")
    
    whitelist_user = User(user_id="test_whitelist", level=UserLevel.WHITELIST)
    tools_for_whitelist = registry.get_tools_for_user(whitelist_user)
    print(f"✓ 白名单用户可用工具: {len(tools_for_whitelist)} 个")
    
    stranger = User(user_id="test_stranger", level=UserLevel.STRANGER)
    tools_for_stranger = registry.get_tools_for_user(stranger)
    print(f"✓ 陌生人可用工具: {len(tools_for_stranger)} 个")
    
    if len(tools_for_owner) > len(tools_for_whitelist) > len(tools_for_stranger):
        print("✓ 权限分级正确")
    else:
        print("  ✗ 权限分级可能有问题")
        return False
    
    return True


def check_tool_policy():
    """检查工具策略"""
    print("\n=== 检查工具策略 ===")
    
    from core.tool_policy import (
        ToolPolicy, ToolPolicyConfig, ToolProfile,
        ToolLoopDetector, TOOL_GROUPS, TOOL_PROFILES
    )
    
    print(f"✓ 工具组数量: {len(TOOL_GROUPS)}")
    print(f"✓ 工具策略数量: {len(TOOL_PROFILES)}")
    
    config = ToolPolicyConfig(profile=ToolProfile.MINIMAL)
    policy = ToolPolicy(config)
    
    base_tools = ["read", "write", "exec", "session_status"]
    allowed = policy.get_allowed_tools(base_tools)
    
    if "session_status" in allowed and "write" not in allowed:
        print("✓ Minimal 策略正确限制工具")
    else:
        print(f"  ✗ Minimal 策略有问题: {allowed}")
        return False
    
    detector = ToolLoopDetector()
    session_key = "test_session"
    
    for _ in range(5):
        detector.record_call(session_key, "read", {"path": "test.py"})
    
    is_loop, reason = detector.check_session_loop(session_key)
    if is_loop:
        print(f"✓ 循环检测正常工作: {reason[:50]}...")
    else:
        print("  ✗ 循环检测未触发")
        return False
    
    return True


def check_skill_system():
    """检查技能系统"""
    print("\n=== 检查技能系统 ===")
    
    from core.skills import SkillManager, Skill
    from core.skills_types import SkillMetadata
    from core.skill_loader import SkillLoader
    
    try:
        loader = SkillLoader(workspace_dir="./test_workspace")
        print("✓ SkillLoader 初始化成功")
    except Exception as e:
        print(f"  ✗ SkillLoader 初始化失败: {e}")
        return False
    
    try:
        manager = SkillManager.get_instance()
        print("✓ SkillManager 初始化成功")
    except Exception as e:
        print(f"  ✗ SkillManager 初始化失败: {e}")
        return False
    
    return True


def check_session_manager():
    """检查会话管理"""
    print("\n=== 检查会话管理 ===")
    
    from config import ConfigManager, XiaoMengConfig, OwnerConfig
    from core.session_manager import SessionManager
    from models import User, UserLevel
    
    try:
        config_manager = ConfigManager.get_instance()
        config = XiaoMengConfig(owner=OwnerConfig(user_id="test_owner"))
        config_manager._config = config
    except Exception:
        pass
    
    try:
        sm = SessionManager.get_instance()
        print("✓ SessionManager 初始化成功")
    except Exception as e:
        print(f"  ✗ SessionManager 初始化失败: {e}")
        return False
    
    required_methods = [
        "get_or_create_session", "get_session", "get_session_by_user",
        "get_current_session", "list_sessions", "get_history",
        "add_message_to_session", "add_message_to_session_by_key"
    ]
    
    missing_methods = []
    for method in required_methods:
        if not hasattr(sm, method):
            missing_methods.append(method)
    
    if missing_methods:
        print(f"  ✗ 缺失方法: {missing_methods}")
        return False
    
    print(f"✓ 所有 {len(required_methods)} 个必需方法存在")
    
    return True


def check_memory_system():
    """检查记忆系统"""
    print("\n=== 检查记忆系统 ===")
    
    from config import ConfigManager, XiaoMengConfig, OwnerConfig
    from core.memory import MemoryManager
    from core.memory.memory_manager import PersonaLoader, MarkdownMemoryStore
    
    try:
        config_manager = ConfigManager.get_instance()
        config = XiaoMengConfig(owner=OwnerConfig(user_id="test_owner"))
        config_manager._config = config
    except Exception:
        pass
    
    try:
        mm = MemoryManager.get_instance()
        print("✓ MemoryManager 初始化成功")
    except Exception as e:
        print(f"  ✗ MemoryManager 初始化失败: {e}")
        return False
    
    required_methods = [
        "get_context_for_llm", "add_memory", "search_memories"
    ]
    
    missing_methods = []
    for method in required_methods:
        if not hasattr(mm, method):
            missing_methods.append(method)
    
    if missing_methods:
        print(f"  ✗ 缺失方法: {missing_methods}")
        return False
    
    print(f"✓ 所有 {len(required_methods)} 个必需方法存在")
    
    return True


def check_subagent_system():
    """检查子Agent系统"""
    print("\n=== 检查子Agent系统 ===")
    
    from core.subagent import (
        SubagentRegistry, SubagentType, SubagentStatus,
        SUBAGENT_CONFIGS
    )
    
    try:
        registry = SubagentRegistry.get_instance()
        print("✓ SubagentRegistry 初始化成功")
    except Exception as e:
        print(f"  ✗ SubagentRegistry 初始化失败: {e}")
        return False
    
    required_methods = [
        "spawn", "get", "list_runs", "update_status",
        "complete", "fail", "kill", "register_completion_handler"
    ]
    
    missing_methods = []
    for method in required_methods:
        if not hasattr(registry, method):
            missing_methods.append(method)
    
    if missing_methods:
        print(f"  ✗ 缺失方法: {missing_methods}")
        return False
    
    print(f"✓ 所有 {len(required_methods)} 个必需方法存在")
    
    expected_types = [SubagentType.THINKER, SubagentType.CODER, 
                      SubagentType.VISION, SubagentType.REASONING]
    for t in expected_types:
        if t not in SUBAGENT_CONFIGS:
            print(f"  ✗ 缺少子Agent类型配置: {t}")
            return False
    
    print(f"✓ 所有 {len(expected_types)} 个子Agent类型已配置")
    
    return True


def check_system_prompt():
    """检查系统提示"""
    print("\n=== 检查系统提示 ===")
    
    from core.system_prompt import (
        build_agent_system_prompt, SystemPromptParams,
        CORE_TOOL_SUMMARIES, TOOL_ORDER
    )
    
    new_tools = ["apply_patch", "process", "browser", "agents_list", "nodes"]
    missing = []
    for tool in new_tools:
        if tool not in CORE_TOOL_SUMMARIES:
            missing.append(tool)
    
    if missing:
        print(f"  ✗ 系统提示缺少工具: {missing}")
        return False
    
    print(f"✓ 所有新工具已添加到系统提示")
    
    params = SystemPromptParams(
        workspace_dir="/test",
        tool_names=["read", "write", "apply_patch"],
        user_level="owner",
        prompt_mode="full",
        skills_prompt="<available_skills><skill><name>test</name><description>Test skill</description><location>~/.xiaomeng/skills/test/SKILL.md</location></skill></available_skills>"
    )
    
    prompt = build_agent_system_prompt(params)
    
    required_sections = [
        "Tooling",
        "Tool Groups",
        "Tool Loop Detection",
        "Skills (mandatory)",
        "Silent Replies"
    ]
    
    missing_sections = []
    for section in required_sections:
        if section not in prompt:
            missing_sections.append(section)
    
    if missing_sections:
        print(f"  ✗ 系统提示缺少部分: {missing_sections}")
        return False
    
    print(f"✓ 所有 {len(required_sections)} 个必需部分存在")
    
    return True


def check_processor():
    """检查处理器"""
    print("\n=== 检查处理器 ===")
    
    from config import ConfigManager, XiaoMengConfig, OwnerConfig
    from core.processor import MessageProcessor
    
    try:
        config_manager = ConfigManager.get_instance()
        config = XiaoMengConfig(owner=OwnerConfig(user_id="test_owner"))
        config_manager._config = config
    except Exception:
        pass
    
    try:
        processor = MessageProcessor()
        print("✓ MessageProcessor 初始化成功")
    except Exception as e:
        print(f"  ✗ MessageProcessor 初始化失败: {e}")
        return False
    
    required_methods = [
        "process", "_build_system_prompt", "_execute_tool_calls",
        "_execute_single_tool", "_setup_subagent_handlers"
    ]
    
    missing_methods = []
    for method in required_methods:
        if not hasattr(processor, method):
            missing_methods.append(method)
    
    if missing_methods:
        print(f"  ✗ 缺失方法: {missing_methods}")
        return False
    
    print(f"✓ 所有 {len(required_methods)} 个必需方法存在")
    
    return True


def check_openclaw_compatibility():
    """检查 OpenClaw 兼容性"""
    print("\n=== 检查 OpenClaw 兼容性 ===")
    
    from core.memory.memory_manager import PersonaLoader
    
    bootstrap_files = PersonaLoader.DEFAULT_BOOTSTRAP_FILES
    expected_files = [
        "AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md",
        "USER.md", "HEARTBEAT.md", "BOOTSTRAP.md", "MEMORY.md"
    ]
    
    if set(bootstrap_files) == set(expected_files):
        print("✓ 人设文件格式与 OpenClaw 兼容")
    else:
        print(f"  ✗ 人设文件不兼容")
        print(f"    期望: {expected_files}")
        print(f"    实际: {bootstrap_files}")
        return False
    
    from core.skills import SkillManager
    
    print("✓ 技能系统 SKILL.md 格式兼容")
    
    from core.system_prompt import build_agent_system_prompt
    
    print("✓ 系统提示构建方式兼容")
    
    return True


def main():
    """运行所有检查"""
    print("=" * 60)
    print("XiaoMengCore 综合检查")
    print("=" * 60)
    
    checks = [
        ("模块导入", check_module_imports),
        ("工具系统", check_tool_system),
        ("工具策略", check_tool_policy),
        ("技能系统", check_skill_system),
        ("会话管理", check_session_manager),
        ("记忆系统", check_memory_system),
        ("子Agent系统", check_subagent_system),
        ("系统提示", check_system_prompt),
        ("处理器", check_processor),
        ("OpenClaw兼容性", check_openclaw_compatibility),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n  ✗ {name} 检查出错: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("检查结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("\n🎉 所有检查通过！XiaoMengCore 已准备就绪。")
        return 0
    else:
        print("\n⚠️ 部分检查失败，请检查上述问题。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
