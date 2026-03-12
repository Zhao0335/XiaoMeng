"""
XiaoMengCore CLI 工具
"""

import click
import asyncio
import json
import sys
import os
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import XiaoMengConfig, LLMConfig, OwnerConfig, ChannelIdentity


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """XiaoMengCore - 多端 AI 桌宠/伴侣框架"""
    pass


@cli.command()
@click.option('--workspace', default='./test_workspace', help='工作区路径')
def onboard(workspace):
    """引导安装配置"""
    click.echo("🦀 欢迎使用 XiaoMengCore！")
    click.echo("")
    
    workspace_path = Path(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    click.echo(f"📁 工作区路径: {workspace_path.absolute()}")
    
    if not (workspace_path / "SOUL.md").exists():
        click.echo("📝 创建默认人设文件...")
        _create_default_persona(workspace_path)
    
    click.echo("✅ 配置完成！")
    click.echo("")
    click.echo("下一步:")
    click.echo(f"  1. 编辑 {workspace}/SOUL.md 自定义人设")
    click.echo(f"  2. 运行 xiaomeng config set-llm 配置模型")
    click.echo(f"  3. 运行 xiaomeng chat 开始对话")


@cli.command()
def config():
    """配置管理"""
    pass


@config.command('show')
def config_show():
    """显示当前配置"""
    config_path = Path("./data/config.json")
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        click.echo(json.dumps(config_data, indent=2, ensure_ascii=False))
    else:
        click.echo("⚠️ 配置文件不存在，请先运行 xiaomeng onboard")


@config.command('set-llm')
@click.option('--provider', required=True, help='模型提供商')
@click.option('--model', required=True, help='模型名称')
@click.option('--api-key', help='API Key')
@click.option('--base-url', help='API Base URL')
def config_set_llm(provider, model, api_key, base_url):
    """设置 LLM 配置"""
    config_path = Path("./data/config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    else:
        config_data = {}
    
    if 'llm' not in config_data:
        config_data['llm'] = {}
    
    config_data['llm']['provider'] = provider
    config_data['llm']['model'] = model
    if api_key:
        config_data['llm']['api_key'] = api_key
    if base_url:
        config_data['llm']['base_url'] = base_url
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    
    click.echo(f"✅ 已设置 LLM: {provider}/{model}")


@config.command('set-owner')
@click.option('--user-id', required=True, help='主人ID')
@click.option('--nickname', help='昵称')
def config_set_owner(user_id, nickname):
    """设置主人信息"""
    config_path = Path("./data/config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    else:
        config_data = {}
    
    if 'owner' not in config_data:
        config_data['owner'] = {}
    
    config_data['owner']['user_id'] = user_id
    if nickname:
        config_data['owner']['nickname'] = nickname
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    
    click.echo(f"✅ 已设置主人: {user_id}")


@cli.command()
@click.option('--workspace', default='./test_workspace', help='工作区路径')
@click.option('--model', default='local', help='使用的模型')
def chat(workspace, model):
    """开始对话"""
    click.echo("🦀 小螃蟹已启动！(输入 /exit 退出)")
    click.echo("")
    
    asyncio.run(_run_chat(workspace, model))


async def _run_chat(workspace: str, model: str):
    """运行对话循环"""
    from core.memory import MemoryManager
    from core.session_manager import SessionManager
    from core.user_manager import UserManager
    from core.llm_client import LLMClient
    from models.core import User, UserLevel, Source, ChannelIdentity as CID
    
    workspace_path = Path(workspace)
    
    memory_manager = MemoryManager.get_instance()
    memory_manager._persona_loader = memory_manager._persona_loader.__class__(
        str(workspace_path)
    )
    
    user_manager = UserManager.get_instance()
    test_user = User(
        user_id="test_user",
        level=UserLevel.OWNER,
        nickname="测试者"
    )
    user_manager._users["test_user"] = test_user
    
    session_manager = SessionManager.get_instance()
    session = session_manager.get_or_create_session(test_user)
    
    llm_client = LLMClient.get_instance()
    
    persona = memory_manager.load_persona()
    system_prompt = f"""你是{persona.identity if persona.identity else '小螃蟹'}

{persona.soul if persona.soul else ''}

{persona.agents if persona.agents else ''}

{persona.user_info if persona.user_info else ''}

{persona.memory if persona.memory else ''}
"""
    
    messages = [{"role": "system", "content": system_prompt}]
    
    while True:
        try:
            user_input = input("你: ").strip()
            
            if not user_input:
                continue
            
            if user_input == "/exit":
                click.echo("🦀 小螃蟹说再见！泡泡泡泡~")
                break
            
            if user_input.startswith("/"):
                await _handle_command(user_input, workspace_path)
                continue
            
            messages.append({"role": "user", "content": user_input})
            
            click.echo("小螃蟹: ", nl=False)
            
            response = await llm_client.chat(
                messages=messages,
                stream=True
            )
            
            full_response = ""
            async for chunk in response:
                content = chunk.get("content", "")
                if content:
                    click.echo(content, nl=False)
                    full_response += content
            
            click.echo("")
            messages.append({"role": "assistant", "content": full_response})
            
        except KeyboardInterrupt:
            click.echo("\n🦀 小螃蟹说再见！")
            break
        except Exception as e:
            click.echo(f"❌ 错误: {e}")


async def _handle_command(command: str, workspace_path: Path):
    """处理命令"""
    parts = command.split()
    cmd = parts[0]
    
    if cmd == "/help":
        click.echo("""
可用命令:
  /help        显示帮助
  /exit        退出对话
  /history     查看变更历史
  /rollback    回滚变更
  /status      显示状态
  /persona     显示人设信息
  /test        运行测试
""")
    
    elif cmd == "/status":
        from core.version_control import VersionControl
        vc = VersionControl.get_instance()
        click.echo(f"""
状态:
  工作区: {workspace_path}
  Git: {'✅' if vc.is_enabled() else '❌'}
  审计日志: ✅
""")
    
    elif cmd == "/persona":
        from core.memory import MemoryManager
        mm = MemoryManager.get_instance()
        persona = mm.load_persona()
        click.echo(f"""
人设信息:
  SOUL.md: {len(persona.soul) if persona.soul else 0} 字符
  AGENTS.md: {len(persona.agents) if persona.agents else 0} 字符
  IDENTITY.md: {len(persona.identity) if persona.identity else 0} 字符
  USER.md: {len(persona.user_info) if persona.user_info else 0} 字符
  MEMORY.md: {len(persona.memory) if persona.memory else 0} 字符
""")
    
    elif cmd == "/history":
        from core.version_control import VersionControl
        vc = VersionControl.get_instance()
        history = vc.get_history(limit=10)
        click.echo("变更历史:")
        for h in history:
            click.echo(f"  - {h}")
    
    elif cmd == "/test":
        await _run_tests()
    
    else:
        click.echo(f"未知命令: {cmd}")


async def _run_tests():
    """运行功能测试"""
    click.echo("\n🧪 开始功能测试...\n")
    
    tests = [
        ("核心模块导入", _test_imports),
        ("人设加载", _test_persona),
        ("版本控制", _test_version_control),
        ("工具注册", _test_tools),
        ("会话管理", _test_session),
        ("用户管理", _test_user),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            await test_func()
            click.echo(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            click.echo(f"  ❌ {name}: {e}")
            failed += 1
    
    click.echo(f"\n结果: {passed} 通过, {failed} 失败")


async def _test_imports():
    from core.memory import MemoryManager
    from core.session_manager import SessionManager
    from core.user_manager import UserManager
    from core.llm_client import LLMClient
    from core.version_control import VersionControl
    from core.skills import SkillManager
    from core.tools import ToolRegistry


async def _test_persona():
    from core.memory import MemoryManager
    mm = MemoryManager.get_instance()
    persona = mm.load_persona()
    assert persona is not None


async def _test_version_control():
    from core.version_control import VersionControl
    vc = VersionControl.get_instance()
    assert vc._audit is not None


async def _test_tools():
    from core.tools import ToolRegistry
    registry = ToolRegistry.get_instance()
    tools = registry.get_all_tools()
    assert len(tools) > 0


async def _test_session():
    from core.session_manager import SessionManager
    from models.core import User, UserLevel
    sm = SessionManager.get_instance()
    user = User(user_id="test", level=UserLevel.OWNER)
    session = sm.get_or_create_session(user)
    assert session is not None


async def _test_user():
    from core.user_manager import UserManager
    um = UserManager.get_instance()
    assert um is not None


def _create_default_persona(workspace_path: Path):
    """创建默认人设文件"""
    files = {
        "SOUL.md": "# 灵魂\n\n这是一个 AI 助手。\n",
        "AGENTS.md": "# 行为规范\n\n帮助用户解决问题。\n",
        "IDENTITY.md": "# 身份\n\n名字: AI助手\n",
        "USER.md": "# 用户\n\n主人信息。\n",
        "MEMORY.md": "# 记忆\n\n重要记忆。\n",
    }
    
    for filename, content in files.items():
        (workspace_path / filename).write_text(content, encoding='utf-8')


@cli.command()
def doctor():
    """诊断问题"""
    click.echo("🔍 检查系统状态...\n")
    
    issues = []
    
    if not Path("./data/config.json").exists():
        issues.append("配置文件不存在")
    
    from core.version_control import VersionControl
    vc = VersionControl.get_instance()
    if not vc._git._enabled:
        issues.append("Git 不可用")
    
    if issues:
        click.echo("发现问题:")
        for issue in issues:
            click.echo(f"  ⚠️ {issue}")
    else:
        click.echo("✅ 系统状态正常")


@cli.command()
@click.option('--port', default=8080, help='端口')
def web(port):
    """启动 Web 服务"""
    click.echo(f"🌐 启动 Web 服务: http://localhost:{port}")
    os.system(f"python -m uvicorn web.app:app --host 0.0.0.0 --port {port}")


if __name__ == '__main__':
    cli()
