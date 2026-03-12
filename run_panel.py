"""
XiaoMengCore 启动脚本
启动管理面板和核心服务
"""

import asyncio
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="XiaoMengCore 管理面板")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式（自动重载）")
    parser.add_argument("--init", action="store_true", help="初始化配置")
    parser.add_argument("--register-model", action="store_true", help="注册默认模型")
    
    args = parser.parse_args()
    
    if args.init:
        init_config()
        return
    
    if args.register_model:
        register_default_models()
        return
    
    start_server(args.host, args.port, args.reload)


def init_config():
    """初始化配置"""
    from config import ConfigManager
    
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    learnings_dir = data_dir / ".learnings"
    learnings_dir.mkdir(exist_ok=True)
    
    skills_dir = data_dir / "skills"
    skills_dir.mkdir(exist_ok=True)
    
    persona_dir = data_dir / "persona"
    persona_dir.mkdir(exist_ok=True)
    
    memory_dir = data_dir / "memory"
    memory_dir.mkdir(exist_ok=True)
    
    print("✅ 配置初始化完成")
    print(f"   数据目录: {data_dir.absolute()}")
    print(f"   学习记录: {learnings_dir.absolute()}")
    print(f"   技能目录: {skills_dir.absolute()}")


def register_default_models():
    """注册默认模型配置"""
    from core.model_layer import ModelLayerRouter, ModelEndpoint, ModelLayer, ModelRole
    
    router = ModelLayerRouter.get_instance()
    
    default_models = [
        {
            "model_id": "qwen-basic",
            "layer": "basic",
            "role": "chat",
            "endpoint": "http://localhost:11434/v1",
            "model_name": "qwen2.5:7b",
            "description": "Qwen 7B 本地模型 - Basic层"
        }
    ]
    
    for cfg in default_models:
        endpoint = ModelEndpoint(
            model_id=cfg["model_id"],
            layer=ModelLayer(cfg["layer"]),
            role=ModelRole(cfg["role"]),
            endpoint=cfg["endpoint"],
            model_name=cfg["model_name"],
            enabled=True
        )
        router.register_model(endpoint)
        print(f"✅ 已注册模型: {cfg['model_id']} ({cfg['layer']}/{cfg['role']})")
    
    print("\n提示: 使用管理面板或 register_model 工具添加更多模型")


def start_server(host: str, port: int, reload: bool):
    """启动管理面板服务器"""
    import uvicorn
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    XiaoMengCore 管理面板                      ║
╠══════════════════════════════════════════════════════════════╣
║  访问地址: http://{host}:{port}                              ║
║                                                              ║
║  功能:                                                       ║
║  • 模型管理 - 注册和管理 Basic/Brain/Special 三层模型         ║
║  • 技能管理 - 创建、编辑、删除技能                            ║
║  • 学习记录 - 查看自我改进的学习历史                          ║
║  • 插件管理 - 启用/禁用插件                                   ║
║  • 记忆管理 - 管理用户记忆分组                                ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "core.admin_panel:app",
        host=host,
        port=port,
        reload=reload
    )


if __name__ == "__main__":
    main()
