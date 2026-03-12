"""
XiaoMengCore 综合测试脚本
验证所有核心模块是否正常工作
"""

import sys
import os

def test_imports():
    """测试模块导入"""
    print("\n" + "=" * 60)
    print("📦 模块导入测试")
    print("=" * 60)
    
    errors = []
    
    print("\n[配置模块]")
    try:
        from config import ConfigManager, XiaoMengConfig
        print("  ✅ config.settings")
    except Exception as e:
        print(f"  ❌ config.settings: {e}")
        errors.append(f"config: {e}")
    
    print("\n[数据模型]")
    try:
        from models import User, Message, Response, Session
        print("  ✅ models.core")
    except Exception as e:
        print(f"  ❌ models.core: {e}")
        errors.append(f"models: {e}")
    
    print("\n[核心模块]")
    try:
        from core import (
            UserManager, SessionManager, LLMClient,
            MessageProcessor, MemoryManager, ToolRegistry,
            SkillManager, PluginManager, ModelLayerRouter,
            SelfImprovingAgent
        )
        print("  ✅ core (基础模块)")
    except Exception as e:
        print(f"  ❌ core: {e}")
        errors.append(f"core: {e}")
    
    print("\n[记忆系统]")
    try:
        from core.memory import (
            MemoryManager, SemanticAnalyzer, GraphitiMemoryStore,
            ModalityPluginSystem, TextModalityPlugin
        )
        print("  ✅ core.memory")
    except Exception as e:
        print(f"  ❌ core.memory: {e}")
        errors.append(f"memory: {e}")
    
    print("\n[v2 架构]")
    try:
        from core.v2 import (
            GatewayV2, IdentityManager, MessageQueue,
            HookSystem, SessionStore, ChannelAdapter
        )
        print("  ✅ core.v2")
    except Exception as e:
        print(f"  ❌ core.v2: {e}")
        errors.append(f"v2: {e}")
    
    print("\n[网关模块]")
    try:
        from gateway import base, cli, http, websocket
        print("  ✅ gateway")
    except Exception as e:
        print(f"  ❌ gateway: {e}")
        errors.append(f"gateway: {e}")
    
    return errors


def test_config():
    """测试配置系统"""
    print("\n" + "=" * 60)
    print("⚙️ 配置系统测试")
    print("=" * 60)
    
    errors = []
    
    try:
        from config import ConfigManager
        
        config_path = "data/config.json"
        if os.path.exists(config_path):
            manager = ConfigManager.get_instance()
            config = manager.load(config_path)
            
            print(f"\n  ✅ 配置加载成功")
            print(f"     - 主人ID: {config.owner.user_id}")
            print(f"     - LLM: {config.llm.provider}/{config.llm.model}")
            print(f"     - 模型层数: Basic={len(config.models.basic_layer)}, Brain={len(config.models.brain_layer)}, Special={len(config.models.special_layer)}")
        else:
            print(f"  ⚠️ 配置文件不存在: {config_path}")
    except Exception as e:
        print(f"  ❌ 配置测试失败: {e}")
        errors.append(str(e))
    
    return errors


def test_memory():
    """测试记忆系统"""
    print("\n" + "=" * 60)
    print("🧠 记忆系统测试")
    print("=" * 60)
    
    errors = []
    
    try:
        from core.memory import MemoryManager, SemanticAnalyzer
        
        print("\n[语义分析器]")
        analyzer = SemanticAnalyzer()
        result = analyzer.quick_analyze("今天天气真好，我很开心！")
        print(f"  ✅ 快速分析: {result}")
        
        print("\n[记忆管理器]")
        try:
            manager = MemoryManager.get_instance()
            print(f"  ✅ MemoryManager 初始化成功")
            
            stats = manager.get_memory_stats()
            print(f"     - 向量数据库: {'启用' if stats.get('vector_enabled') else '禁用'}")
            print(f"     - 知识图谱: {'启用' if stats.get('graph_enabled') else '禁用'}")
        except Exception as e:
            print(f"  ⚠️ MemoryManager 初始化警告: {e}")
    
    except Exception as e:
        print(f"  ❌ 记忆系统测试失败: {e}")
        errors.append(str(e))
    
    return errors


def test_modality():
    """测试多模态系统"""
    print("\n" + "=" * 60)
    print("🧩 多模态系统测试")
    print("=" * 60)
    
    errors = []
    
    try:
        from core.memory import (
            ModalityPluginSystem, TextModalityPlugin,
            create_plugin_system, create_default_plugins
        )
        
        print("\n[插件系统]")
        system = create_plugin_system()
        
        for plugin in create_default_plugins():
            system.register_plugin(plugin)
            print(f"  ✅ 注册插件: {plugin.modality_name}")
        
        info = system.get_plugin_info()
        print(f"\n  融合策略: {info.get('fusion_strategies', [])}")
        print(f"  默认策略: {info.get('default_fusion')}")
        print(f"  并行模式: {info.get('parallel')}")
        
    except Exception as e:
        print(f"  ❌ 多模态系统测试失败: {e}")
        errors.append(str(e))
    
    return errors


def test_v2():
    """测试 v2 架构"""
    print("\n" + "=" * 60)
    print("🌐 v2 架构测试")
    print("=" * 60)
    
    errors = []
    
    try:
        from core.v2 import (
            IdentityManager, Platform, MessageQueue, QueueMode,
            HookSystem, HookPoint, SessionStore
        )
        
        print("\n[身份管理]")
        identity_manager = IdentityManager()
        identity_manager.link_platform_identity("alice", Platform.QQ, "12345")
        identity_manager.link_platform_identity("alice", Platform.WECHAT, "wxid_alice")
        
        identity = identity_manager.resolve_identity(Platform.QQ, "12345")
        print(f"  ✅ 身份解析: QQ:12345 -> {identity.identity_id if identity else 'None'}")
        
        print("\n[消息队列]")
        queue = MessageQueue()
        print(f"  ✅ 消息队列初始化成功")
        print(f"     - 模式: STEER, FOLLOWUP, COLLECT")
        
        print("\n[钩子系统]")
        hooks = HookSystem()
        
        def test_hook(context):
            print("     钩子触发!")
        
        hooks.register("test_hook", HookPoint.MESSAGE_RECEIVED, test_hook)
        print(f"  ✅ 钩子系统初始化成功")
        
        print("\n[会话存储]")
        session_store = SessionStore("./data")
        print(f"  ✅ 会话存储初始化成功")
        
    except Exception as e:
        print(f"  ❌ v2 架构测试失败: {e}")
        errors.append(str(e))
    
    return errors


def test_persona():
    """测试人设文件"""
    print("\n" + "=" * 60)
    print("📝 人设文件测试")
    print("=" * 60)
    
    errors = []
    
    persona_files = ["SOUL.md", "AGENTS.md", "MEMORY.md", "USER.md", "IDENTITY.md", "TOOLS.md"]
    persona_dir = "data/persona"
    
    for filename in persona_files:
        path = os.path.join(persona_dir, filename)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  ✅ {filename} ({size} bytes)")
        else:
            print(f"  ⚠️ {filename} 不存在")
    
    return errors


def test_skills():
    """测试技能文件"""
    print("\n" + "=" * 60)
    print("🎯 技能文件测试")
    print("=" * 60)
    
    errors = []
    
    skills_dir = "data/skills"
    if os.path.exists(skills_dir):
        skills = [d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d))]
        print(f"  已加载 {len(skills)} 个技能:")
        for skill in skills:
            skill_path = os.path.join(skills_dir, skill, "SKILL.md")
            if os.path.exists(skill_path):
                print(f"    ✅ {skill}")
            else:
                print(f"    ⚠️ {skill} (缺少 SKILL.md)")
    else:
        print(f"  ⚠️ 技能目录不存在: {skills_dir}")
    
    return errors


def test_care():
    """测试主动关怀系统"""
    print("\n" + "=" * 60)
    print("💝 主动关怀系统测试")
    print("=" * 60)
    
    errors = []
    
    try:
        from core import ProactiveCareSystem, CareType, SpecialDay
        
        print("\n[关怀系统]")
        care_system = ProactiveCareSystem()
        
        care_system.add_special_day("测试生日", "2024-06-15", "birthday")
        print(f"  ✅ 添加特殊日子成功")
        
        status = care_system.get_status()
        print(f"     - 特殊日子数: {status['special_days_count']}")
        
        print("\n[个性化引擎]")
        from core import PersonalizationEngine
        
        engine = PersonalizationEngine()
        engine.record_interaction("你好呀~", "你好~", emotion="happy")
        
        summary = engine.get_user_summary()
        print(f"  ✅ 个性化引擎初始化成功")
        print(f"     - 沟通风格: {summary['communication_style']}")
        
    except Exception as e:
        print(f"  ❌ 关怀系统测试失败: {e}")
        errors.append(str(e))
    
    return errors


def test_schedule_todo():
    """测试日程和待办系统"""
    print("\n" + "=" * 60)
    print("📅 日程与待办系统测试")
    print("=" * 60)
    
    errors = []
    
    try:
        from core import ScheduleManager, ScheduleType
        from datetime import datetime, timedelta
        
        print("\n[日程管理]")
        schedule_mgr = ScheduleManager()
        
        schedule = schedule_mgr.add_schedule(
            title="测试会议",
            start_time=datetime.now() + timedelta(hours=1),
            schedule_type=ScheduleType.MEETING
        )
        print(f"  ✅ 添加日程成功: {schedule.title}")
        
        today = schedule_mgr.get_today_schedules()
        print(f"     - 今日日程: {len(today)} 条")
        
        print("\n[待办事项]")
        from core import TodoManager, TodoPriority, TodoCategory
        
        todo_mgr = TodoManager()
        
        todo = todo_mgr.add_todo(
            title="测试任务",
            priority=TodoPriority.HIGH,
            category=TodoCategory.WORK
        )
        print(f"  ✅ 添加待办成功: {todo.title}")
        
        stats = todo_mgr.get_statistics()
        print(f"     - 总待办: {stats['total']} 条")
        
    except Exception as e:
        print(f"  ❌ 日程待办测试失败: {e}")
        errors.append(str(e))
    
    return errors


def test_realtime_info():
    """测试实时信息服务"""
    print("\n" + "=" * 60)
    print("🌐 实时信息服务测试")
    print("=" * 60)
    
    errors = []
    
    try:
        import asyncio
        from core import RealtimeInfoService
        
        print("\n[实时信息]")
        info_service = RealtimeInfoService()
        print(f"  ✅ 实时信息服务初始化成功")
        
        async def get_holiday():
            return await info_service.get_holiday_info()
        
        holiday = asyncio.run(get_holiday())
        print(f"     - 今日: {holiday.get('weekday_cn', '')} {'🎉 ' + holiday.get('holiday_name') if holiday.get('is_holiday') else ''}")
        
    except Exception as e:
        print(f"  ❌ 实时信息测试失败: {e}")
        errors.append(str(e))
    
    return errors


def main():
    """运行所有测试"""
    print("\n" + "═" * 60)
    print("🐱 XiaoMengCore 综合测试")
    print("═" * 60)
    
    all_errors = []
    
    all_errors.extend(test_imports())
    all_errors.extend(test_config())
    all_errors.extend(test_memory())
    all_errors.extend(test_modality())
    all_errors.extend(test_v2())
    all_errors.extend(test_persona())
    all_errors.extend(test_skills())
    all_errors.extend(test_care())
    all_errors.extend(test_schedule_todo())
    all_errors.extend(test_realtime_info())
    
    print("\n" + "=" * 60)
    print("📊 测试结果")
    print("=" * 60)
    
    if all_errors:
        print(f"\n❌ 发现 {len(all_errors)} 个问题:")
        for error in all_errors:
            print(f"   - {error}")
        return 1
    else:
        print("\n✅ 所有测试通过!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
