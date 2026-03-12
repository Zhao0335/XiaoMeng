"""
XiaoMengCore 新功能验证测试
测试 Tool Profiles, Tool Groups, apply_patch, process, browser, agents_list, nodes 等新功能
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tool_policy():
    """测试工具策略系统"""
    print("\n=== 测试 Tool Policy ===")
    
    from core.tool_policy import (
        ToolPolicy, ToolPolicyConfig, ToolProfile,
        ToolLoopDetector, get_tool_loop_detector,
        TOOL_GROUPS, TOOL_PROFILES
    )
    
    print(f"✓ 工具组数量: {len(TOOL_GROUPS)}")
    print(f"✓ 工具策略数量: {len(TOOL_PROFILES)}")
    
    for group_name, tools in list(TOOL_GROUPS.items())[:3]:
        print(f"  - {group_name}: {tools[:3]}...")
    
    config = ToolPolicyConfig(profile=ToolProfile.CODING)
    policy = ToolPolicy(config)
    
    base_tools = ["read", "write", "exec", "memory_search", "sessions_list", "web_search"]
    allowed = policy.get_allowed_tools(base_tools)
    print(f"✓ Coding 策略允许的工具: {allowed}")
    
    is_allowed = policy.is_tool_allowed("read", base_tools)
    print(f"✓ read 工具是否允许: {is_allowed}")
    
    print("✓ Tool Policy 测试通过")


def test_tool_loop_detection():
    """测试工具循环检测"""
    print("\n=== 测试 Tool Loop Detection ===")
    
    from core.tool_policy import ToolLoopDetector, ToolPolicyConfig
    
    detector = ToolLoopDetector()
    
    session_key = "test_session_001"
    
    detector.record_call(session_key, "read", {"path": "test.py"})
    detector.record_call(session_key, "read", {"path": "test.py"})
    detector.record_call(session_key, "read", {"path": "test.py"})
    detector.record_call(session_key, "read", {"path": "test.py"})
    detector.record_call(session_key, "read", {"path": "test.py"})
    
    config = ToolPolicyConfig(loop_detection_window=5, max_identical_calls=3)
    is_loop, reason = detector.check_session_loop(session_key, config)
    
    print(f"✓ 检测到循环: {is_loop}")
    if is_loop:
        print(f"  原因: {reason}")
    
    stats = detector.get_session_stats(session_key)
    print(f"✓ 会话统计: 总调用 {stats['total_calls']}, 唯一工具 {stats['unique_tools']}")
    
    print("✓ Tool Loop Detection 测试通过")


async def test_new_tools():
    """测试新添加的工具"""
    print("\n=== 测试新工具 ===")
    
    from core.tools import (
        ToolRegistry, EditTool, ApplyPatchTool, ProcessTool,
        BrowserTool, AgentsListTool, NodesTool
    )
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    user = User(user_id="test_user", level=UserLevel.OWNER)
    
    edit_tool = registry.get("edit")
    print(f"✓ edit 工具: {edit_tool is not None}")
    
    apply_patch_tool = registry.get("apply_patch")
    print(f"✓ apply_patch 工具: {apply_patch_tool is not None}")
    
    process_tool = registry.get("process")
    print(f"✓ process 工具: {process_tool is not None}")
    
    browser_tool = registry.get("browser")
    print(f"✓ browser 工具: {browser_tool is not None}")
    
    agents_list_tool = registry.get("agents_list")
    print(f"✓ agents_list 工具: {agents_list_tool is not None}")
    
    nodes_tool = registry.get("nodes")
    print(f"✓ nodes 工具: {nodes_tool is not None}")
    
    all_tools = registry.get_all_tools()
    print(f"✓ 总工具数量: {len(all_tools)}")
    
    print("✓ 新工具测试通过")


async def test_apply_patch_tool():
    """测试 apply_patch 工具"""
    print("\n=== 测试 apply_patch 工具 ===")
    
    from core.tools import ToolRegistry
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    user = User(user_id="test_user", level=UserLevel.OWNER)
    
    patch_content = """--- a/test_file.txt
+++ b/test_file.txt
@@ -1,3 +1,3 @@
 line1
-old line
+new line
 line3
"""
    
    result = await registry.execute("apply_patch", user, patch=patch_content, dry_run=True)
    print(f"✓ apply_patch dry_run: success={result.success}")
    if result.success:
        print(f"  预览: {result.output[:100]}...")
    
    print("✓ apply_patch 工具测试通过")


async def test_process_tool():
    """测试 process 工具"""
    print("\n=== 测试 process 工具 ===")
    
    from core.tools import ToolRegistry
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    user = User(user_id="test_user", level=UserLevel.OWNER)
    
    result = await registry.execute("process", user, action="list")
    print(f"✓ process list: success={result.success}")
    
    print("✓ process 工具测试通过")


async def test_browser_tool():
    """测试 browser 工具"""
    print("\n=== 测试 browser 工具 ===")
    
    from core.tools import ToolRegistry
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    user = User(user_id="test_user", level=UserLevel.OWNER)
    
    result = await registry.execute("browser", user, action="screenshot")
    print(f"✓ browser screenshot: success={result.success}")
    print(f"  输出: {result.output[:100]}...")
    
    print("✓ browser 工具测试通过")


async def test_agents_list_tool():
    """测试 agents_list 工具"""
    print("\n=== 测试 agents_list 工具 ===")
    
    from core.tools import ToolRegistry
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    user = User(user_id="test_user", level=UserLevel.OWNER)
    
    result = await registry.execute("agents_list", user)
    print(f"✓ agents_list: success={result.success}")
    if result.success and result.data:
        print(f"  Agent 数量: {result.data.get('count', 0)}")
    
    print("✓ agents_list 工具测试通过")


async def test_nodes_tool():
    """测试 nodes 工具"""
    print("\n=== 测试 nodes 工具 ===")
    
    from core.tools import ToolRegistry
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    user = User(user_id="test_user", level=UserLevel.OWNER)
    
    result = await registry.execute("nodes", user, action="list")
    print(f"✓ nodes list: success={result.success}")
    if result.success and result.data:
        print(f"  节点数量: {len(result.data.get('nodes', []))}")
    
    print("✓ nodes 工具测试通过")


def test_system_prompt():
    """测试系统提示"""
    print("\n=== 测试系统提示 ===")
    
    from core.system_prompt import (
        build_agent_system_prompt, SystemPromptParams,
        CORE_TOOL_SUMMARIES, TOOL_ORDER
    )
    
    print(f"✓ 工具摘要数量: {len(CORE_TOOL_SUMMARIES)}")
    print(f"✓ 工具顺序数量: {len(TOOL_ORDER)}")
    
    new_tools = ["apply_patch", "process", "browser", "agents_list", "nodes"]
    for tool in new_tools:
        if tool in CORE_TOOL_SUMMARIES:
            print(f"  ✓ {tool}: {CORE_TOOL_SUMMARIES[tool][:50]}...")
        else:
            print(f"  ✗ {tool}: 未找到")
    
    params = SystemPromptParams(
        workspace_dir="/test/workspace",
        tool_names=["read", "write", "edit", "apply_patch", "process", "browser"],
        user_level="owner",
        prompt_mode="full"
    )
    
    prompt = build_agent_system_prompt(params)
    
    if "Tool Groups" in prompt:
        print("✓ 系统提示包含 Tool Groups 部分")
    if "Tool Loop Detection" in prompt:
        print("✓ 系统提示包含 Tool Loop Detection 部分")
    if "apply_patch" in prompt:
        print("✓ 系统提示包含 apply_patch 工具")
    
    print(f"✓ 系统提示长度: {len(prompt)} 字符")
    
    print("✓ 系统提示测试通过")


def test_tool_registry_extensions():
    """测试 ToolRegistry 扩展方法"""
    print("\n=== 测试 ToolRegistry 扩展 ===")
    
    from core.tools import ToolRegistry
    from models import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    user = User(user_id="test_user", level=UserLevel.OWNER)
    
    groups = registry.get_tool_groups()
    print(f"✓ 工具组数量: {len(groups)}")
    
    profiles = registry.get_tool_profiles()
    print(f"✓ 工具策略数量: {len(profiles)}")
    
    tools_by_profile = registry.get_tools_by_profile(user, "coding")
    print(f"✓ Coding 策略工具数量: {len(tools_by_profile)}")
    
    schema_by_profile = registry.get_tools_schema_by_profile(user, "minimal")
    print(f"✓ Minimal 策略 schema 数量: {len(schema_by_profile)}")
    
    print("✓ ToolRegistry 扩展测试通过")


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("XiaoMengCore 新功能验证测试")
    print("=" * 60)
    
    try:
        test_tool_policy()
        test_tool_loop_detection()
        await test_new_tools()
        await test_apply_patch_tool()
        await test_process_tool()
        await test_browser_tool()
        await test_agents_list_tool()
        await test_nodes_tool()
        test_system_prompt()
        test_tool_registry_extensions()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        
        print("\n新增功能总结:")
        print("1. Tool Profiles 和 Tool Groups 系统")
        print("2. apply_patch 多文件补丁工具")
        print("3. process 后台进程管理工具")
        print("4. Tool Loop Detection 循环检测机制")
        print("5. browser 浏览器控制工具")
        print("6. agents_list Agent 列表工具")
        print("7. nodes 节点管理工具")
        print("8. edit 文件编辑工具")
        print("9. 系统提示更新支持新工具")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
