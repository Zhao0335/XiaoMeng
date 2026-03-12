"""
XiaoMengCore 主入口
AI Agent 框架启动入口，集成多模型路由、优先级调度、心跳系统

核心改进（与OpenClaw一致）：
1. 使用 build_agent_system_prompt 构建系统提示
2. 使用 SkillLoader 加载技能（6级优先级）
3. 使用 EnhancedModelManager 管理模型
4. 使用 EnhancedRouter 路由消息
"""

import asyncio
import argparse
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, List

from config import ConfigManager, XiaoMengConfig
from models import User, UserLevel, Source
from core import (
    UserManager, SessionManager, MessageProcessor,
    MemoryManager, ToolRegistry, SkillManager,
    HardwareManager, HeartbeatManager,
    ModelRouter, ModelConfig, ModelType,
    PriorityScheduler, ThreeLayerCoordinator, Priority,
    SkillLoader, EnhancedModelManager, EnhancedRouter,
    build_agent_system_prompt, SystemPromptParams
)
from gateway import (
    GatewayManager, HTTPGateway, 
    WebSocketGateway, CLIGateway
)


class XiaoMengCore:
    """
    XiaoMengCore 应用
    
    完整的 AI Agent 框架，支持：
    - 多模型路由
    - 优先级调度
    - 三层协同（小脑/脑干/大脑）
    - OpenClaw 兼容
    - 心跳任务系统
    - 硬件控制
    
    核心改进（与OpenClaw一致）：
    - 使用 build_agent_system_prompt 构建系统提示
    - 使用 SkillLoader 加载技能（6级优先级）
    - 使用 EnhancedModelManager 管理模型
    - 使用 EnhancedRouter 路由消息
    """
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config: Optional[XiaoMengConfig] = None
        self.gateway_manager = GatewayManager.get_instance()
        self.user_manager: Optional[UserManager] = None
        self.session_manager: Optional[SessionManager] = None
        self.memory_manager: Optional[MemoryManager] = None
        self.processor: Optional[MessageProcessor] = None
        self.heartbeat_manager: Optional[HeartbeatManager] = None
        self.scheduler: Optional[PriorityScheduler] = None
        self.coordinator: Optional[ThreeLayerCoordinator] = None
        
        self.skill_loader: Optional[SkillLoader] = None
        self.enhanced_model_manager: Optional[EnhancedModelManager] = None
        self.enhanced_router: Optional[EnhancedRouter] = None
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """初始化所有组件"""
        print("=" * 60)
        print("  XiaoMengCore 启动中...")
        print("  兼容 OpenClaw 人设系统 | 支持多模型路由")
        print("=" * 60)
        
        print("\n[1/12] 加载配置...")
        config_manager = ConfigManager.get_instance()
        self.config = config_manager.load(self.config_path)
        print(f"  配置文件: {self.config_path}")
        print(f"  数据目录: {self.config.data_dir}")
        
        print("\n[2/12] 初始化用户管理器...")
        self.user_manager = UserManager.get_instance()
        print(f"  主人ID: {self.config.owner.user_id}")
        print(f"  主人身份数: {len(self.config.owner.identities)}")
        
        print("\n[3/12] 初始化会话管理器...")
        self.session_manager = SessionManager.get_instance()
        
        print("\n[4/12] 初始化记忆管理器...")
        self.memory_manager = MemoryManager.get_instance()
        persona = self.memory_manager.load_persona()
        self._print_persona_status(persona)
        
        print("\n[5/12] 初始化技能系统（SkillLoader - 6级优先级）...")
        self.skill_loader = SkillLoader(workspace_dir=self.config.data_dir)
        skills = self.skill_loader.load_all_skills()
        print(f"  已加载技能: {len(skills)} 个")
        print(f"  优先级: extra < bundled < managed < personal < project < workspace")
        
        print("\n[6/12] 初始化工具系统...")
        tool_registry = ToolRegistry.get_instance()
        tools = tool_registry.get_all_tools()
        print(f"  已注册工具: {len(tools)} 个")
        for tool in tools:
            owner_only = "🔒" if tool.requires_owner else "🌐"
            print(f"    {owner_only} {tool.name}: {tool.description}")
        
        print("\n[7/12] 初始化优先级调度器...")
        self.scheduler = PriorityScheduler.get_instance()
        self.coordinator = ThreeLayerCoordinator.get_instance()
        print("  调度器已就绪")
        print("  三层协同架构: 小脑(P0) / 脑干(P1) / 大脑(P2/P3)")
        
        print("\n[8/12] 初始化心跳系统...")
        self.heartbeat_manager = HeartbeatManager.get_instance()
        self.heartbeat_manager.load_config()
        self.heartbeat_manager.register_callback(self._on_heartbeat_task)
        print(f"  心跳任务: {len(self.heartbeat_manager._config.tasks)} 个")
        
        print("\n[9/12] 初始化消息处理器...")
        self.processor = MessageProcessor.get_instance()
        
        print("\n[10/12] 初始化增强组件...")
        await self._setup_enhanced_components()
        
        print("\n[11/12] 初始化网关...")
        await self._setup_gateways()
        
        print("\n[12/12] 设置模型路由...")
        await self._setup_model_router()
        
        print("\n" + "=" * 60)
        print("  XiaoMengCore 启动完成!")
        print("=" * 60)
    
    def _print_persona_status(self, persona):
        """打印人设状态"""
        files_status = {
            "SOUL.md": bool(persona.soul),
            "AGENTS.md": bool(persona.agents),
            "IDENTITY.md": bool(persona.identity),
            "USER.md": bool(persona.user_info),
            "TOOLS.md": bool(persona.tools),
            "MEMORY.md": bool(persona.memory),
            "HEARTBEAT.md": bool(persona.heartbeat)
        }
        
        print("  人设文件状态:")
        for filename, exists in files_status.items():
            status = "✅" if exists else "❌"
            print(f"    {status} {filename}")
        
        if not any(files_status.values()):
            print("  ⚠️ 警告: 未找到人设文件，请配置 persona 目录")
    
    async def _setup_enhanced_components(self):
        """设置增强组件（与OpenClaw一致的核心机制）"""
        from core.model_manager import ModelEndpoint, ModelLayer, LoadBalancingConfig
        
        models_config = getattr(self.config, 'models', None)
        
        all_endpoints = []
        if models_config and models_config.enabled:
            for cfg in getattr(models_config, 'basic_layer', []):
                all_endpoints.append((cfg, "basic"))
            for cfg in getattr(models_config, 'brain_layer', []):
                all_endpoints.append((cfg, "brain"))
            for cfg in getattr(models_config, 'special_layer', []):
                all_endpoints.append((cfg, "special"))
        
        if all_endpoints:
            lb_config = LoadBalancingConfig(
                strategy="least_latency",
                max_retries=3,
                health_check_interval=60
            )
            self.enhanced_model_manager = EnhancedModelManager(load_balance_config=lb_config)
            
            endpoints = []
            for cfg, layer_name in all_endpoints:
                ep = ModelEndpoint(
                    model_id=cfg.model_id,
                    layer=ModelLayer(layer_name),
                    endpoint=cfg.endpoint,
                    model_name=cfg.model_name,
                    api_key=cfg.api_key,
                    max_tokens=getattr(cfg, 'max_tokens', 4096),
                    temperature=getattr(cfg, 'temperature', 0.7)
                )
                endpoints.append(ep)
            
            results = await self.enhanced_model_manager.initialize_parallel(endpoints)
            success_count = sum(1 for v in results.values() if v)
            print(f"  增强模型管理器: {success_count}/{len(endpoints)} 模型初始化成功")
            print(f"  特性: 并行加载 | 健康检查 | 自动重试 | 负载均衡")
        else:
            print("  未配置多模型，跳过增强模型管理器")
        
        router_path = Path(self.config.data_dir) / "router_data"
        router_path.mkdir(parents=True, exist_ok=True)
        self.enhanced_router = EnhancedRouter(storage_path=str(router_path))
        print(f"  跨平台路由器: 已初始化")
        print(f"  特性: 身份统一 | 用户分组 | 会话隔离")
    
    async def _setup_model_router(self):
        """设置多模型路由"""
        from core.llm_client import LLMClient
        
        llm_client = LLMClient.get_instance()
        
        models_config = getattr(self.config, 'models', None)
        
        has_models = False
        if models_config and models_config.enabled:
            has_models = bool(
                getattr(models_config, 'basic_layer', []) or
                getattr(models_config, 'brain_layer', []) or
                getattr(models_config, 'special_layer', [])
            )
        
        if has_models:
            llm_client.enable_router(models_config)
            print(f"\n  多模型路由已启用")
            
            router_status = llm_client.get_router_status()
            for model_type, status in router_status.items():
                available = status['available']
                print(f"    {model_type}: {status['available']}/{status['total']} 可用")
        else:
            print("\n  使用单一模型模式")
    
    async def _setup_gateways(self):
        """设置网关"""
        enabled_channels = self.config.gateway.enabled_channels
        
        if "http" in enabled_channels:
            http_gateway = HTTPGateway()
            http_gateway.set_message_handler(self._handle_message)
            self.gateway_manager.register("http", http_gateway)
            print(f"  HTTP Gateway: http://{self.config.gateway.http_host}:{self.config.gateway.http_port}")
        
        if "websocket" in enabled_channels:
            ws_gateway = WebSocketGateway()
            ws_gateway.set_message_handler(self._handle_message)
            self.gateway_manager.register("websocket", ws_gateway)
            print(f"  WebSocket Gateway: ws://{self.config.gateway.websocket_host}:{self.config.gateway.websocket_port}")
        
        if "cli" in enabled_channels:
            cli_gateway = CLIGateway()
            cli_gateway.set_message_handler(self._handle_message)
            self.gateway_manager.register("cli", cli_gateway)
            print("  CLI Gateway: 已启用")
    
    async def _handle_message(self, message):
        """处理消息"""
        return await self.processor.process(message)
    
    async def _on_heartbeat_task(self, task, result: Dict):
        """心跳任务回调"""
        if result.get("skipped"):
            return
        
        if result.get("actions"):
            for action_result in result["actions"]:
                action = action_result.get("action", "")
                action_data = action_result.get("result", {})
                
                if "发送" in action or "消息" in action:
                    message = action_data.get("message")
                    if message:
                        print(f"\n[心跳] 主动消息: {message}")
    
    async def run(self):
        """运行应用"""
        await self.initialize()
        
        try:
            await self.gateway_manager.start_all()
            
            await self.heartbeat_manager.start()
            
            asyncio.create_task(self.scheduler.start())
            
            self._setup_signal_handlers()
            
            print("\n按 Ctrl+C 退出...")
            await self._shutdown_event.wait()
            
        except Exception as e:
            print(f"\n启动错误: {e}")
            raise
        finally:
            await self.shutdown()
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(sig, frame):
            print("\n正在关闭...")
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def shutdown(self):
        """关闭应用"""
        print("\n正在关闭 XiaoMengCore...")
        
        await self.heartbeat_manager.stop()
        
        await self.scheduler.stop()
        
        await self.gateway_manager.stop_all()
        
        if self.memory_manager:
            self.memory_manager.close()
        
        print("XiaoMengCore 已关闭")


async def migrate_from_openclaw(config_path: str, openclaw_dir: str):
    """从 OpenClaw 迁移"""
    print(f"正在从 OpenClaw 迁移: {openclaw_dir}")
    
    config_manager = ConfigManager.get_instance()
    config = config_manager.load(config_path)
    
    memory_manager = MemoryManager.get_instance()
    memory_manager.migrate_from_openclaw(openclaw_dir)
    
    print("迁移完成!")


def create_default_config(config_path: str):
    """创建默认配置文件"""
    from config import XiaoMengConfig, OwnerConfig, ChannelIdentity
    
    config = XiaoMengConfig(
        owner=OwnerConfig(
            user_id="your_qq_number",
            identities=[
                ChannelIdentity(source="qq", channel_user_id="your_qq_number", display_name="主人"),
                ChannelIdentity(source="desktop", channel_user_id="desktop_user", display_name="桌宠"),
            ]
        )
    )
    
    config.save_yaml(config_path)
    print(f"已创建默认配置文件: {config_path}")
    print("请编辑配置文件，填入你的 QQ 号和 API Key")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="XiaoMengCore AI Agent 框架")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="创建默认配置文件"
    )
    parser.add_argument(
        "--migrate",
        metavar="OPENCLAW_DIR",
        help="从 OpenClaw 迁移人设"
    )
    
    args = parser.parse_args()
    
    if args.init:
        create_default_config(args.config)
        return
    
    if not Path(args.config).exists():
        print(f"配置文件不存在: {args.config}")
        print("使用 --init 创建默认配置文件")
        sys.exit(1)
    
    if args.migrate:
        asyncio.run(migrate_from_openclaw(args.config, args.migrate))
        return
    
    app = XiaoMengCore(args.config)
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
