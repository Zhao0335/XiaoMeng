"""
XiaoMengCore 管理面板
提供 Skill、插件、模型的可视化管理界面

功能：
1. Skill 管理：查看、创建、编辑、删除技能
2. 插件管理：管理已安装的插件
3. 模型管理：配置和监控多模型调度
4. 学习记录：查看自我改进的学习历史
5. 记忆管理：管理用户记忆分组
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import os
import asyncio


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup()
    yield
    shutdown()


def startup():
    from config import ConfigManager
    from core.model_layer import ModelLayerRouter, ModelEndpoint, ModelLayer, ModelRole
    from core.self_improving import SelfImprovingAgent
    
    config_path = Path("data/config.json")
    if not config_path.exists():
        config_path = Path("config.example.yaml")
    
    try:
        if config_path.exists():
            ConfigManager.get_instance().load(str(config_path))
        else:
            from config import XiaoMengConfig, OwnerConfig
            default_config = XiaoMengConfig(
                owner=OwnerConfig(user_id="owner"),
                data_dir="./data"
            )
            ConfigManager.get_instance()._config = default_config
    except Exception as e:
        print(f"配置加载警告: {e}")
        from config import XiaoMengConfig, OwnerConfig
        ConfigManager.get_instance()._config = XiaoMengConfig(
            owner=OwnerConfig(user_id="owner"),
            data_dir="./data"
        )
    
    config = ConfigManager.get_instance().get()
    data_dir = Path(config.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    learnings_dir = data_dir / ".learnings"
    learnings_dir.mkdir(parents=True, exist_ok=True)
    
    skills_dir = data_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    persona_dir = data_dir / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    
    memory_dir = data_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        router = ModelLayerRouter.get_instance()
        
        if config.models.enabled:
            all_models = (
                config.models.basic_layer + 
                config.models.brain_layer + 
                config.models.special_layer
            )
            for m in all_models:
                endpoint = ModelEndpoint(
                    model_id=m.model_id,
                    layer=ModelLayer(m.layer),
                    role=ModelRole(m.role),
                    endpoint=m.endpoint,
                    model_name=m.model_name,
                    api_key=m.api_key,
                    max_tokens=m.max_tokens,
                    temperature=m.temperature,
                    timeout=m.timeout,
                    enabled=m.enabled,
                    priority=m.priority
                )
                router.register_model(endpoint)
            print(f"✅ ModelLayerRouter 初始化成功，已加载 {len(all_models)} 个模型")
    except Exception as e:
        print(f"ModelLayerRouter 初始化警告: {e}")
    
    try:
        SelfImprovingAgent.initialize(str(data_dir))
        print("✅ SelfImprovingAgent 初始化成功")
    except Exception as e:
        print(f"SelfImprovingAgent 初始化警告: {e}")
    
    try:
        from core.skills import SkillManager
        SkillManager.get_instance()
        print("✅ SkillManager 初始化成功")
    except Exception as e:
        print(f"SkillManager 初始化警告: {e}")
    
    try:
        from core.memory import MemoryManager
        MemoryManager.get_instance()
        print("✅ MemoryManager 初始化成功")
    except Exception as e:
        print(f"MemoryManager 初始化警告: {e}")
    
    try:
        from core.plugins import PluginManager
        plugin_manager = PluginManager.initialize(str(data_dir.parent / "plugins"))
        asyncio.create_task(plugin_manager.initialize_plugins())
        print(f"✅ PluginManager 初始化成功，已加载 {len(plugin_manager.list_plugins())} 个插件")
    except Exception as e:
        print(f"PluginManager 初始化警告: {e}")
    
    print("✅ XiaoMengCore 管理面板已启动")


def shutdown():
    print("👋 XiaoMengCore 管理面板已关闭")


app = FastAPI(title="XiaoMengCore 管理面板", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from gateway.paper_reader import router as paper_router
app.include_router(paper_router)


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    instructions: str
    examples: List[Dict[str, str]] = []


class SkillUpdateRequest(BaseModel):
    content: str


class ModelRegisterRequest(BaseModel):
    model_id: str
    layer: str
    role: str
    endpoint: str
    model_name: str
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    enabled: bool = True
    priority: int = 1


class MemoryAddRequest(BaseModel):
    content: str
    tags: List[str] = []
    importance: int = 1


PANEL_DIR = Path(__file__).parent / "panel"
PANEL_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    return get_panel_html()


@app.get("/api/status")
async def get_status():
    try:
        from core.model_layer import ModelLayerRouter
        router = ModelLayerRouter.get_instance()
        model_status = router.get_status()
        has_models = len(model_status.get("models", [])) > 0
    except Exception as e:
        model_status = {"error": str(e), "models": [], "layers": {}}
        has_models = False
    
    try:
        from core.self_improving import SelfImprovingAgent
        agent = SelfImprovingAgent.get_instance()
        learning_summary = agent.get_learning_summary()
    except Exception as e:
        learning_summary = {"error": str(e)}
    
    return {
        "connected": has_models,
        "models": model_status,
        "learnings": learning_summary
    }


@app.get("/api/skills")
async def list_skills():
    from core.skills import SkillManager
    manager = SkillManager.get_instance()
    skills = manager.get_all_skills()
    
    return {
        "skills": [
            {
                "name": s.metadata.name,
                "description": s.metadata.description,
                "path": s.skill_path,
                "enabled": True
            }
            for s in skills
        ]
    }


@app.get("/api/skills/{skill_name}")
async def get_skill(skill_name: str):
    from core.skills import SkillManager
    manager = SkillManager.get_instance()
    skill = manager.get_skill(skill_name)
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {
        "name": skill.metadata.name,
        "description": skill.metadata.description,
        "content": skill.content,
        "path": skill.skill_path,
        "examples": [
            {"user_request": e.user_request, "command": e.command}
            for e in skill.examples
        ]
    }


@app.post("/api/skills")
async def create_skill(request: SkillCreateRequest):
    from core.skills import SkillManager
    manager = SkillManager.get_instance()
    
    try:
        skill = manager.create_skill(
            name=request.name,
            description=request.description,
            instructions=request.instructions,
            examples=request.examples
        )
        return {"success": True, "skill_path": skill.skill_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/skills/{skill_name}")
async def update_skill(skill_name: str, request: SkillUpdateRequest):
    from core.skills import SkillManager
    manager = SkillManager.get_instance()
    
    try:
        success = manager.update_skill(skill_name, request.content)
        if not success:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/skills/{skill_name}")
async def delete_skill(skill_name: str):
    from core.skills import SkillManager
    manager = SkillManager.get_instance()
    
    try:
        success = manager.delete_skill(skill_name)
        if not success:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models")
async def list_models():
    from core.model_layer import ModelLayerRouter, ModelLayer
    from config import ConfigManager
    
    router = ModelLayerRouter.get_instance()
    config = ConfigManager.get_instance().get()
    
    return {
        "models": [
            endpoint.to_dict()
            for endpoint in router.list_models()
        ],
        "layers": {
            layer.value: [
                endpoint.to_dict()
                for endpoint in router.list_models(layer)
            ]
            for layer in ModelLayer
        },
        "config": {
            "enabled": config.models.enabled,
            "basic_count": len(config.models.basic_layer),
            "brain_count": len(config.models.brain_layer),
            "special_count": len(config.models.special_layer)
        }
    }


@app.post("/api/models")
async def register_model(request: ModelRegisterRequest):
    from core.model_layer import ModelLayerRouter, ModelEndpoint, ModelLayer, ModelRole
    from config import ConfigManager, ModelEndpointConfig
    
    router = ModelLayerRouter.get_instance()
    config_manager = ConfigManager.get_instance()
    config = config_manager.get()
    
    endpoint = ModelEndpoint(
        model_id=request.model_id,
        layer=ModelLayer(request.layer),
        role=ModelRole(request.role),
        endpoint=request.endpoint,
        model_name=request.model_name,
        api_key=request.api_key,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        enabled=request.enabled,
        priority=request.priority
    )
    
    try:
        model_id = router.register_model(endpoint)
        
        model_config = ModelEndpointConfig(
            model_id=request.model_id,
            layer=request.layer,
            role=request.role,
            endpoint=request.endpoint,
            model_name=request.model_name,
            api_key=request.api_key,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            enabled=request.enabled,
            priority=request.priority
        )
        
        if request.layer == "basic":
            config.models.basic_layer.append(model_config)
        elif request.layer == "brain":
            config.models.brain_layer.append(model_config)
        elif request.layer == "special":
            config.models.special_layer.append(model_config)
        
        config_manager._config = config
        config.save_json("data/config.json")
        
        return {"success": True, "model_id": model_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/models/{model_id}")
async def unregister_model(model_id: str):
    from core.model_layer import ModelLayerRouter
    from config import ConfigManager
    
    router = ModelLayerRouter.get_instance()
    config_manager = ConfigManager.get_instance()
    config = config_manager.get()
    
    success = router.unregister_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    
    config.models.basic_layer = [m for m in config.models.basic_layer if m.model_id != model_id]
    config.models.brain_layer = [m for m in config.models.brain_layer if m.model_id != model_id]
    config.models.special_layer = [m for m in config.models.special_layer if m.model_id != model_id]
    
    config_manager._config = config
    config.save_json("data/config.json")
    
    return {"success": True}


class UserGroupCreateRequest(BaseModel):
    group_id: str
    name: str
    user_level: str = "whitelist"
    identities: List[Dict[str, str]] = []


@app.get("/api/user-groups")
async def list_user_groups():
    from config import ConfigManager
    
    config = ConfigManager.get_instance().get()
    
    return {
        "groups": [
            {
                "group_id": gid,
                "name": g.name,
                "user_level": g.user_level,
                "identities": [
                    {"source": i.source, "channel_user_id": i.channel_user_id, "display_name": i.display_name}
                    for i in g.identities
                ]
            }
            for gid, g in config.user_groups.items()
        ],
        "owner": {
            "user_id": config.owner.user_id,
            "identities": [
                {"source": i.source, "channel_user_id": i.channel_user_id, "display_name": i.display_name}
                for i in config.owner.identities
            ]
        },
        "whitelist": {
            "enabled": config.whitelist.enabled,
            "pairing_code": config.whitelist.pairing_code,
            "users": config.whitelist.users
        }
    }


@app.post("/api/user-groups")
async def create_user_group(request: UserGroupCreateRequest):
    from config import ConfigManager, UserGroupConfig, ChannelIdentity
    
    config_manager = ConfigManager.get_instance()
    config = config_manager.get()
    
    if request.group_id in config.user_groups:
        raise HTTPException(status_code=400, detail="Group ID already exists")
    
    identities = [
        ChannelIdentity(
            source=i.get("source", ""),
            channel_user_id=i.get("channel_user_id", ""),
            display_name=i.get("display_name")
        )
        for i in request.identities
    ]
    
    config.user_groups[request.group_id] = UserGroupConfig(
        group_id=request.group_id,
        name=request.name,
        identities=identities,
        user_level=request.user_level
    )
    
    config_manager._config = config
    config.save_json("data/config.json")
    
    return {"success": True, "group_id": request.group_id}


@app.delete("/api/user-groups/{group_id}")
async def delete_user_group(group_id: str):
    from config import ConfigManager
    
    config_manager = ConfigManager.get_instance()
    config = config_manager.get()
    
    if group_id not in config.user_groups:
        raise HTTPException(status_code=404, detail="Group not found")
    
    del config.user_groups[group_id]
    config_manager._config = config
    config.save_json("data/config.json")
    
    return {"success": True}


@app.get("/api/config")
async def get_config():
    from config import ConfigManager
    
    config = ConfigManager.get_instance().get()
    
    return {
        "owner": {
            "user_id": config.owner.user_id,
            "identities": [
                {"source": i.source, "channel_user_id": i.channel_user_id, "display_name": i.display_name}
                for i in config.owner.identities
            ]
        },
        "llm": {
            "provider": config.llm.provider,
            "base_url": config.llm.base_url,
            "model": config.llm.model,
            "max_tokens": config.llm.max_tokens,
            "temperature": config.llm.temperature
        },
        "models": {
            "enabled": config.models.enabled,
            "basic_layer": [
                {"model_id": m.model_id, "model_name": m.model_name, "enabled": m.enabled}
                for m in config.models.basic_layer
            ],
            "brain_layer": [
                {"model_id": m.model_id, "model_name": m.model_name, "enabled": m.enabled}
                for m in config.models.brain_layer
            ],
            "special_layer": [
                {"model_id": m.model_id, "model_name": m.model_name, "enabled": m.enabled}
                for m in config.models.special_layer
            ]
        },
        "memory": {
            "enabled": config.memory.enabled,
            "storage_type": config.memory.storage_type
        },
        "gateway": {
            "enabled_channels": config.gateway.enabled_channels,
            "http_port": config.gateway.http_port
        },
        "data_dir": config.data_dir
    }


@app.get("/api/learnings")
async def list_learnings():
    from core.self_improving import SelfImprovingAgent
    agent = SelfImprovingAgent.get_instance()
    
    return {
        "errors": [e.to_markdown() for e in agent.get_pending_errors()],
        "learnings": [l.to_markdown() for l in agent.get_recent_learnings()],
        "features": [f.to_markdown() for f in agent.get_feature_requests()]
    }


@app.get("/api/learnings/search")
async def search_learnings(q: str):
    from core.self_improving import SelfImprovingAgent
    agent = SelfImprovingAgent.get_instance()
    
    results = agent.search_learnings(q)
    return {
        "results": [r.to_markdown() for r in results]
    }


@app.get("/api/memory/groups")
async def list_memory_groups():
    from core.memory import MemoryManager
    from models import UserLevel
    
    manager = MemoryManager.get_instance()
    
    return {
        "groups": [
            {"level": "owner", "description": "主人的记忆"},
            {"level": "whitelist", "description": "白名单用户的记忆"},
            {"level": "stranger", "description": "陌生人的记忆（临时）"}
        ]
    }


@app.get("/api/memory/{user_level}")
async def get_memories(user_level: str):
    from core.memory import MemoryManager
    from models import User, UserLevel
    
    manager = MemoryManager.get_instance()
    
    try:
        level = UserLevel(user_level)
        user = User(user_id="viewer", level=level)
        memories = manager.get_recent_memories(user, days=7)
        
        return {
            "memories": [m.to_markdown() for m in memories]
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user level")


@app.post("/api/memory")
async def add_memory(request: MemoryAddRequest):
    from core.memory import MemoryManager
    from models import User, UserLevel
    
    manager = MemoryManager.get_instance()
    user = User(user_id="owner", level=UserLevel.OWNER)
    
    try:
        manager.add_memory(user, request.content, request.tags, request.importance)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/plugins")
async def list_plugins():
    try:
        from core.plugins import PluginManager
        manager = PluginManager.get_instance()
        
        plugins = []
        for plugin in manager.list_plugins():
            plugins.append({
                "name": plugin.metadata.name,
                "version": plugin.metadata.version,
                "description": plugin.metadata.description,
                "author": plugin.metadata.author,
                "enabled": plugin.metadata.enabled,
                "has_skill": plugin.has_skill(),
                "tools_count": len(plugin.get_tools()),
                "path": str(plugin.plugin_dir)
            })
        
        return {"plugins": plugins}
    except Exception as e:
        plugins_dir = Path("plugins")
        if not plugins_dir.exists():
            return {"plugins": []}
        
        plugins = []
        for plugin_dir in plugins_dir.iterdir():
            if plugin_dir.is_dir():
                manifest_file = plugin_dir / "plugin.json"
                if manifest_file.exists():
                    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
                    plugins.append({
                        "name": manifest.get("name", plugin_dir.name),
                        "version": manifest.get("version", "1.0.0"),
                        "description": manifest.get("description", ""),
                        "enabled": manifest.get("enabled", True),
                        "path": str(plugin_dir)
                    })
        
        return {"plugins": plugins}


@app.post("/api/plugins/{plugin_name}/toggle")
async def toggle_plugin(plugin_name: str):
    try:
        from core.plugins import PluginManager
        manager = PluginManager.get_instance()
        
        plugin = manager.get_plugin(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        
        if plugin.metadata.enabled:
            success = manager.disable_plugin(plugin_name)
        else:
            success = manager.enable_plugin(plugin_name)
        
        return {"success": success, "enabled": not plugin.metadata.enabled}
    except HTTPException:
        raise
    except Exception as e:
        plugins_dir = Path("plugins")
        plugin_dir = plugins_dir / plugin_name
        
        if not plugin_dir.exists():
            raise HTTPException(status_code=404, detail="Plugin not found")
        
        manifest_file = plugin_dir / "plugin.json"
        if not manifest_file.exists():
            raise HTTPException(status_code=404, detail="Plugin manifest not found")
        
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
        manifest["enabled"] = not manifest.get("enabled", True)
        manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        
        return {"success": True, "enabled": manifest["enabled"]}


@app.get("/api/plugins/{plugin_name}/tools")
async def get_plugin_tools(plugin_name: str):
    from core.plugins import PluginManager
    manager = PluginManager.get_instance()
    
    plugin = manager.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    return {"tools": plugin.get_tools()}


@app.get("/api/skills/commands")
async def get_all_skill_commands():
    from core.skills import SkillManager
    manager = SkillManager.get_instance()
    
    return {"commands": manager.get_all_commands()}


@app.get("/api/modality/plugins")
async def list_modality_plugins():
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        info = manager.get_modality_info()
        
        plugins = []
        for p in info.get("plugins", []):
            plugins.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "status": p.get("status"),
                "weight": p.get("weight"),
                "version": p.get("version"),
                "description": p.get("description"),
                "input_types": p.get("input_types", [])
            })
        
        return {
            "plugins": plugins,
            "fusion_strategies": info.get("fusion_strategies", []),
            "default_fusion": info.get("default_fusion", "attention"),
            "parallel": info.get("parallel", True),
            "timeout_ms": info.get("timeout_ms", 5000)
        }
    except Exception as e:
        return {
            "plugins": [],
            "error": str(e)
        }


@app.post("/api/modality/plugins/{modality_id}/weight")
async def set_modality_weight(modality_id: str, weight: float):
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        manager.set_modality_weight(modality_id, weight)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/modality/plugins/{modality_id}/toggle")
async def toggle_modality_plugin(modality_id: str):
    from core.memory import MemoryManager, ModalityStatus
    
    try:
        manager = MemoryManager.get_instance()
        info = manager.get_modality_info(modality_id)
        
        if not info:
            raise HTTPException(status_code=404, detail="Modality not found")
        
        current_status = info.get("status")
        if current_status == "active":
            manager._modality_system.set_status(modality_id, ModalityStatus.INACTIVE)
            new_status = "inactive"
        else:
            manager._modality_system.set_status(modality_id, ModalityStatus.ACTIVE)
            new_status = "active"
        
        return {"success": True, "status": new_status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/modality/fusion")
async def set_fusion_strategy(strategy: str):
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        manager._modality_system._default_fusion = strategy
        return {"success": True, "strategy": strategy}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/modality/analyze")
async def analyze_modality(request: Dict[str, Any]):
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        result = manager.analyze_multimodal_sync(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/stats")
async def get_memory_stats():
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        stats = manager.get_memory_stats()
        return stats
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/memory/semantic")
async def analyze_semantic(text: str):
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        result = manager.analyze_semantic(text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/graph/entity/{entity_name}")
async def get_entity_memory(entity_name: str):
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        result = manager.get_entity_memory(entity_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/memory/decay")
async def apply_memory_decay(decay_factor: float = 0.95):
    from core.memory import MemoryManager
    
    try:
        manager = MemoryManager.get_instance()
        manager.apply_memory_decay(decay_factor)
        return {"success": True, "decay_factor": decay_factor}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_panel_html() -> str:
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XiaoMengCore 管理面板</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        [v-cloak] { display: none; }
        .tab-active { border-bottom: 2px solid #3b82f6; color: #3b82f6; }
        .card { background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 16px; margin-bottom: 16px; }
        .btn { padding: 8px 16px; border-radius: 6px; cursor: pointer; transition: all 0.2s; }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-primary:hover { background: #2563eb; }
        .btn-danger { background: #ef4444; color: white; }
        .btn-danger:hover { background: #dc2626; }
        .btn-success { background: #22c55e; color: white; }
        .btn-success:hover { background: #16a34a; }
        .input { width: 100%; padding: 8px 12px; border: 1px solid #e5e7eb; border-radius: 6px; margin-bottom: 8px; }
        .textarea { width: 100%; padding: 8px 12px; border: 1px solid #e5e7eb; border-radius: 6px; min-height: 200px; font-family: monospace; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 12px; font-weight: 500; }
        .badge-basic { background: #dbeafe; color: #1d4ed8; }
        .badge-brain { background: #dcfce7; color: #15803d; }
        .badge-special { background: #fef3c7; color: #b45309; }
        .model-card { border-left: 4px solid #3b82f6; padding-left: 12px; }
        .model-card.basic { border-left-color: #3b82f6; }
        .model-card.brain { border-left-color: #22c55e; }
        .model-card.special { border-left-color: #f59e0b; }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <div id="app" v-cloak>
        <nav class="bg-white shadow-sm border-b">
            <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
                <h1 class="text-xl font-bold text-gray-800">🎀 XiaoMengCore 管理面板</h1>
                <div class="flex items-center gap-4">
                    <a href="/paper/reader" class="text-sm text-indigo-600 hover:text-indigo-800">📚 论文阅读器</a>
                    <span :class="['text-sm', status.connected ? 'text-green-500' : 'text-gray-500']">
                        {{ status.connected ? '● 已连接' : '○ 未连接' }}
                    </span>
                    <span class="text-xs text-gray-400">{{ models.length }} 个模型</span>
                </div>
            </div>
        </nav>

        <div class="max-w-7xl mx-auto px-4 py-6">
            <div class="flex gap-4 border-b mb-6">
                <button v-for="tab in tabs" :key="tab.id"
                    @click="activeTab = tab.id"
                    :class="['px-4 py-2 font-medium', activeTab === tab.id ? 'tab-active' : 'text-gray-500']">
                    {{ tab.name }}
                </button>
            </div>

            <div v-if="activeTab === 'models'">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-lg font-semibold">模型管理</h2>
                    <button @click="showModelModal = true" class="btn btn-primary">+ 注册模型</button>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                    <div class="card">
                        <h3 class="font-semibold text-blue-600 mb-2">Basic 层</h3>
                        <p class="text-sm text-gray-500 mb-2">快速决策和路由判断</p>
                        <div v-for="model in modelsByLayer.basic" :key="model.model_id" class="model-card basic mb-2">
                            <div class="font-medium">{{ model.model_name }}</div>
                            <div class="text-xs text-gray-500">{{ model.role }}</div>
                        </div>
                        <div v-if="!modelsByLayer.basic.length" class="text-gray-400 text-sm">暂无模型</div>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold text-green-600 mb-2">Brain 层</h3>
                        <p class="text-sm text-gray-500 mb-2">复杂任务处理</p>
                        <div v-for="model in modelsByLayer.brain" :key="model.model_id" class="model-card brain mb-2">
                            <div class="font-medium">{{ model.model_name }}</div>
                            <div class="text-xs text-gray-500">{{ model.role }}</div>
                        </div>
                        <div v-if="!modelsByLayer.brain.length" class="text-gray-400 text-sm">暂无模型</div>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold text-amber-600 mb-2">Special 层</h3>
                        <p class="text-sm text-gray-500 mb-2">专业领域任务</p>
                        <div v-for="model in modelsByLayer.special" :key="model.model_id" class="model-card special mb-2">
                            <div class="font-medium">{{ model.model_name }}</div>
                            <div class="text-xs text-gray-500">{{ model.role }}</div>
                        </div>
                        <div v-if="!modelsByLayer.special.length" class="text-gray-400 text-sm">暂无模型</div>
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'skills'">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-lg font-semibold">技能管理</h2>
                    <button @click="showSkillModal = true" class="btn btn-primary">+ 创建技能</button>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div v-for="skill in skills" :key="skill.name" class="card">
                        <div class="flex justify-between items-start">
                            <div>
                                <h3 class="font-semibold">{{ skill.name }}</h3>
                                <p class="text-sm text-gray-500 mt-1">{{ skill.description }}</p>
                            </div>
                            <div class="flex gap-2">
                                <button @click="editSkill(skill)" class="text-blue-500 hover:text-blue-700">编辑</button>
                                <button @click="deleteSkill(skill.name)" class="text-red-500 hover:text-red-700">删除</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'learnings'">
                <h2 class="text-lg font-semibold mb-4">学习记录</h2>
                
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="card">
                        <h3 class="font-semibold text-red-600 mb-2">待处理错误</h3>
                        <div v-for="error in learnings.errors" :key="error" class="text-sm mb-2 p-2 bg-red-50 rounded">
                            <div v-html="renderMarkdown(error)"></div>
                        </div>
                        <div v-if="!learnings.errors.length" class="text-gray-400 text-sm">暂无错误</div>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold text-blue-600 mb-2">学习记录</h3>
                        <div v-for="learning in learnings.learnings" :key="learning" class="text-sm mb-2 p-2 bg-blue-50 rounded">
                            <div v-html="renderMarkdown(learning)"></div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold text-green-600 mb-2">功能请求</h3>
                        <div v-for="feature in learnings.features" :key="feature" class="text-sm mb-2 p-2 bg-green-50 rounded">
                            <div v-html="renderMarkdown(feature)"></div>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'plugins'">
                <h2 class="text-lg font-semibold mb-4">插件管理</h2>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div v-for="plugin in plugins" :key="plugin.name" class="card">
                        <div class="flex justify-between items-start">
                            <div>
                                <h3 class="font-semibold">{{ plugin.name }}</h3>
                                <p class="text-sm text-gray-500">{{ plugin.description }}</p>
                                <span class="text-xs text-gray-400">v{{ plugin.version }}</span>
                            </div>
                            <button @click="togglePlugin(plugin.name)" 
                                :class="['btn', plugin.enabled ? 'btn-danger' : 'btn-success']">
                                {{ plugin.enabled ? '禁用' : '启用' }}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'users'">
                <h2 class="text-lg font-semibold mb-4">用户分组管理</h2>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                    <div class="card border-l-4 border-purple-500">
                        <h3 class="font-semibold text-purple-600 mb-2">主人</h3>
                        <div class="text-sm mb-2">
                            <span class="font-medium">ID:</span> {{ userGroups.owner?.user_id }}
                        </div>
                        <div class="text-sm text-gray-500">
                            身份: {{ userGroups.owner?.identities?.length || 0 }} 个渠道
                        </div>
                    </div>
                    
                    <div class="card border-l-4 border-green-500">
                        <h3 class="font-semibold text-green-600 mb-2">白名单</h3>
                        <div class="text-sm mb-2">
                            <span :class="userGroups.whitelist?.enabled ? 'text-green-500' : 'text-gray-400'">
                                {{ userGroups.whitelist?.enabled ? '✓ 已启用' : '○ 未启用' }}
                            </span>
                        </div>
                        <div class="text-sm text-gray-500">
                            配对码: {{ userGroups.whitelist?.pairing_code || '未设置' }}
                        </div>
                    </div>
                </div>
                
                <h3 class="font-semibold mb-2">用户组</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div v-for="group in userGroups.groups" :key="group.group_id" class="card">
                        <div class="flex justify-between items-start">
                            <div>
                                <h4 class="font-medium">{{ group.name }}</h4>
                                <span class="text-xs px-2 py-1 rounded bg-gray-100">{{ group.user_level }}</span>
                                <div class="text-sm text-gray-500 mt-1">
                                    {{ group.identities?.length || 0 }} 个身份
                                </div>
                            </div>
                            <button @click="deleteUserGroup(group.group_id)" class="text-red-500 hover:text-red-700 text-sm">
                                删除
                            </button>
                        </div>
                    </div>
                    <div v-if="!userGroups.groups?.length" class="card text-gray-400 text-sm">
                        暂无用户组，可通过配置文件添加
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'modality'">
                <h2 class="text-lg font-semibold mb-4">多模态管理</h2>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                    <div class="card">
                        <h3 class="font-semibold mb-2">融合策略</h3>
                        <select v-model="modalitySettings.fusionStrategy" @change="setFusionStrategy" class="input">
                            <option v-for="s in modalitySettings.fusionStrategies" :key="s" :value="s">{{ s }}</option>
                        </select>
                        <p class="text-sm text-gray-500 mt-2">
                            当前: <span class="font-medium">{{ modalitySettings.defaultFusion }}</span>
                        </p>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold mb-2">系统设置</h3>
                        <div class="text-sm space-y-1">
                            <div><span class="text-gray-500">并行模式:</span> 
                                <span :class="modalitySettings.parallel ? 'text-green-500' : 'text-gray-400'">
                                    {{ modalitySettings.parallel ? '✓ 启用' : '○ 禁用' }}
                                </span>
                            </div>
                            <div><span class="text-gray-500">超时时间:</span> {{ modalitySettings.timeoutMs }}ms</div>
                        </div>
                    </div>
                </div>
                
                <h3 class="font-semibold mb-2">模态插件</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div v-for="plugin in modalityPlugins" :key="plugin.id" class="card">
                        <div class="flex justify-between items-start mb-2">
                            <div>
                                <h4 class="font-medium">{{ plugin.name }}</h4>
                                <span :class="['badge', plugin.status === 'active' ? 'badge-brain' : 'bg-gray-100 text-gray-500']">
                                    {{ plugin.status }}
                                </span>
                            </div>
                            <button @click="toggleModalityPlugin(plugin.id)" 
                                :class="['btn text-sm', plugin.status === 'active' ? 'btn-danger' : 'btn-success']">
                                {{ plugin.status === 'active' ? '禁用' : '启用' }}
                            </button>
                        </div>
                        <p class="text-sm text-gray-500 mb-2">{{ plugin.description }}</p>
                        <div class="flex items-center gap-2">
                            <span class="text-sm text-gray-500">权重:</span>
                            <input type="range" min="0" max="1" step="0.1" 
                                :value="plugin.weight" 
                                @change="setModalityWeight(plugin.id, $event.target.value)"
                                class="flex-1">
                            <span class="text-sm font-medium">{{ plugin.weight?.toFixed(1) }}</span>
                        </div>
                        <div class="text-xs text-gray-400 mt-1">
                            输入: {{ plugin.inputTypes?.join(', ') }}
                        </div>
                    </div>
                </div>
                
                <div class="card mt-6">
                    <h3 class="font-semibold mb-2">快速测试</h3>
                    <div class="space-y-3">
                        <textarea v-model="modalityTestInput" placeholder="输入测试文本..." class="textarea" style="min-height: 80px;"></textarea>
                        <button @click="testModalityAnalyze" class="btn btn-primary">分析</button>
                        <div v-if="modalityTestResult" class="mt-4 p-4 bg-gray-50 rounded">
                            <h4 class="font-medium mb-2">分析结果</h4>
                            <pre class="text-sm overflow-auto">{{ JSON.stringify(modalityTestResult, null, 2) }}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="activeTab === 'config'">
                <h2 class="text-lg font-semibold mb-4">系统配置</h2>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="card">
                        <h3 class="font-semibold mb-2">LLM 配置</h3>
                        <div class="text-sm space-y-1">
                            <div><span class="text-gray-500">Provider:</span> {{ configData.llm?.provider }}</div>
                            <div><span class="text-gray-500">Model:</span> {{ configData.llm?.model }}</div>
                            <div><span class="text-gray-500">Endpoint:</span> {{ configData.llm?.base_url }}</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold mb-2">模型配置</h3>
                        <div class="text-sm space-y-1">
                            <div><span class="text-gray-500">Basic:</span> {{ configData.models?.basic_layer?.length || 0 }} 个</div>
                            <div><span class="text-gray-500">Brain:</span> {{ configData.models?.brain_layer?.length || 0 }} 个</div>
                            <div><span class="text-gray-500">Special:</span> {{ configData.models?.special_layer?.length || 0 }} 个</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold mb-2">记忆配置</h3>
                        <div class="text-sm space-y-1">
                            <div><span class="text-gray-500">Enabled:</span> {{ configData.memory?.enabled ? '是' : '否' }}</div>
                            <div><span class="text-gray-500">Type:</span> {{ configData.memory?.storage_type }}</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3 class="font-semibold mb-2">网关配置</h3>
                        <div class="text-sm space-y-1">
                            <div><span class="text-gray-500">Channels:</span> {{ configData.gateway?.enabled_channels?.join(', ') }}</div>
                            <div><span class="text-gray-500">HTTP Port:</span> {{ configData.gateway?.http_port }}</div>
                        </div>
                    </div>
                </div>
                
                <div class="card mt-4">
                    <h3 class="font-semibold mb-2">数据目录</h3>
                    <code class="text-sm bg-gray-100 px-2 py-1 rounded">{{ configData.data_dir }}</code>
                </div>
            </div>
        </div>

        <div v-if="showModelModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg p-6 w-full max-w-md">
                <h3 class="text-lg font-semibold mb-4">注册新模型</h3>
                <div class="space-y-3">
                    <input v-model="newModel.model_id" placeholder="模型ID" class="input">
                    <select v-model="newModel.layer" class="input">
                        <option value="basic">Basic 层</option>
                        <option value="brain">Brain 层</option>
                        <option value="special">Special 层</option>
                    </select>
                    <select v-model="newModel.role" class="input">
                        <option value="chat">聊天</option>
                        <option value="reasoning">推理</option>
                        <option value="code">代码</option>
                        <option value="vision">视觉</option>
                    </select>
                    <input v-model="newModel.endpoint" placeholder="API端点 (如 http://localhost:11434/v1)" class="input">
                    <input v-model="newModel.model_name" placeholder="模型名称 (如 qwen2.5:7b)" class="input">
                    <input v-model="newModel.api_key" placeholder="API Key (可选)" class="input">
                </div>
                <div class="flex justify-end gap-2 mt-4">
                    <button @click="showModelModal = false" class="btn">取消</button>
                    <button @click="registerModel" class="btn btn-primary">注册</button>
                </div>
            </div>
        </div>

        <div v-if="showSkillModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
                <h3 class="text-lg font-semibold mb-4">创建新技能</h3>
                <div class="space-y-3">
                    <input v-model="newSkill.name" placeholder="技能名称" class="input">
                    <input v-model="newSkill.description" placeholder="技能描述" class="input">
                    <textarea v-model="newSkill.instructions" placeholder="使用说明（支持Markdown）" class="textarea"></textarea>
                </div>
                <div class="flex justify-end gap-2 mt-4">
                    <button @click="showSkillModal = false" class="btn">取消</button>
                    <button @click="createSkill" class="btn btn-primary">创建</button>
                </div>
            </div>
        </div>
    </div>

    <script>
    const { createApp, ref, computed, onMounted } = Vue;

    createApp({
        setup() {
            const tabs = [
                { id: 'models', name: '模型管理' },
                { id: 'skills', name: '技能管理' },
                { id: 'users', name: '用户分组' },
                { id: 'modality', name: '多模态' },
                { id: 'learnings', name: '学习记录' },
                { id: 'plugins', name: '插件管理' },
                { id: 'config', name: '配置' }
            ];
            
            const activeTab = ref('models');
            const status = ref({});
            const skills = ref([]);
            const plugins = ref([]);
            const learnings = ref({ errors: [], learnings: [], features: [] });
            const userGroups = ref({ groups: [], owner: {}, whitelist: {} });
            const configData = ref({});
            const models = ref([]);
            
            const modalityPlugins = ref([]);
            const modalitySettings = ref({
                fusionStrategies: [],
                defaultFusion: 'attention',
                parallel: true,
                timeoutMs: 5000,
                fusionStrategy: 'attention'
            });
            const modalityTestInput = ref('');
            const modalityTestResult = ref(null);
            
            const showModelModal = ref(false);
            const showSkillModal = ref(false);
            
            const newModel = ref({
                model_id: '',
                layer: 'basic',
                role: 'chat',
                endpoint: '',
                model_name: '',
                api_key: ''
            });
            
            const newSkill = ref({
                name: '',
                description: '',
                instructions: ''
            });
            
            const modelsByLayer = computed(() => {
                const result = { basic: [], brain: [], special: [] };
                models.value.forEach(m => {
                    if (result[m.layer]) {
                        result[m.layer].push(m);
                    }
                });
                return result;
            });
            
            const fetchData = async () => {
                try {
                    const statusRes = await fetch('/api/status');
                    const statusData = await statusRes.json();
                    status.value = statusData;
                    
                    if (statusData.models && statusData.models.models) {
                        models.value = statusData.models.models || [];
                    } else {
                        const modelsRes = await fetch('/api/models');
                        const modelsData = await modelsRes.json();
                        models.value = modelsData.models || [];
                    }
                    
                    const skillsRes = await fetch('/api/skills');
                    const skillsData = await skillsRes.json();
                    skills.value = skillsData.skills || [];
                    
                    const pluginsRes = await fetch('/api/plugins');
                    const pluginsData = await pluginsRes.json();
                    plugins.value = pluginsData.plugins || [];
                    
                    const learningsRes = await fetch('/api/learnings');
                    learnings.value = await learningsRes.json();
                    
                    const userGroupsRes = await fetch('/api/user-groups');
                    userGroups.value = await userGroupsRes.json();
                    
                    const configRes = await fetch('/api/config');
                    configData.value = await configRes.json();
                    
                    const modalityRes = await fetch('/api/modality/plugins');
                    const modalityData = await modalityRes.json();
                    modalityPlugins.value = modalityData.plugins || [];
                    modalitySettings.value = {
                        fusionStrategies: modalityData.fusion_strategies || [],
                        defaultFusion: modalityData.default_fusion || 'attention',
                        parallel: modalityData.parallel ?? true,
                        timeoutMs: modalityData.timeout_ms || 5000,
                        fusionStrategy: modalityData.default_fusion || 'attention'
                    };
                } catch (e) {
                    console.error('Failed to fetch data:', e);
                    status.value = { connected: false };
                }
            };
            
            const registerModel = async () => {
                try {
                    const res = await fetch('/api/models', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(newModel.value)
                    });
                    if (res.ok) {
                        showModelModal.value = false;
                        fetchData();
                        newModel.value = { model_id: '', layer: 'basic', role: 'chat', endpoint: '', model_name: '', api_key: '' };
                    }
                } catch (e) {
                    console.error('Failed to register model:', e);
                }
            };
            
            const createSkill = async () => {
                try {
                    const res = await fetch('/api/skills', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(newSkill.value)
                    });
                    if (res.ok) {
                        showSkillModal.value = false;
                        fetchData();
                        newSkill.value = { name: '', description: '', instructions: '' };
                    }
                } catch (e) {
                    console.error('Failed to create skill:', e);
                }
            };
            
            const deleteSkill = async (name) => {
                if (confirm('确定要删除这个技能吗？')) {
                    try {
                        await fetch(`/api/skills/${name}`, { method: 'DELETE' });
                        fetchData();
                    } catch (e) {
                        console.error('Failed to delete skill:', e);
                    }
                }
            };
            
            const togglePlugin = async (name) => {
                try {
                    await fetch(`/api/plugins/${name}/toggle`, { method: 'POST' });
                    fetchData();
                } catch (e) {
                    console.error('Failed to toggle plugin:', e);
                }
            };
            
            const deleteUserGroup = async (groupId) => {
                if (confirm('确定要删除这个用户组吗？')) {
                    try {
                        await fetch(`/api/user-groups/${groupId}`, { method: 'DELETE' });
                        fetchData();
                    } catch (e) {
                        console.error('Failed to delete user group:', e);
                    }
                }
            };
            
            const toggleModalityPlugin = async (modalityId) => {
                try {
                    await fetch(`/api/modality/plugins/${modalityId}/toggle`, { method: 'POST' });
                    fetchData();
                } catch (e) {
                    console.error('Failed to toggle modality plugin:', e);
                }
            };
            
            const setModalityWeight = async (modalityId, weight) => {
                try {
                    await fetch(`/api/modality/plugins/${modalityId}/weight?weight=${weight}`, { method: 'POST' });
                    fetchData();
                } catch (e) {
                    console.error('Failed to set modality weight:', e);
                }
            };
            
            const setFusionStrategy = async () => {
                try {
                    await fetch(`/api/modality/fusion?strategy=${modalitySettings.value.fusionStrategy}`, { method: 'POST' });
                    fetchData();
                } catch (e) {
                    console.error('Failed to set fusion strategy:', e);
                }
            };
            
            const testModalityAnalyze = async () => {
                try {
                    const res = await fetch('/api/modality/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: modalityTestInput.value })
                    });
                    modalityTestResult.value = await res.json();
                } catch (e) {
                    console.error('Failed to analyze:', e);
                    modalityTestResult.value = { error: e.message };
                }
            };
            
            const renderMarkdown = (text) => {
                return marked.parse(text || '');
            };
            
            onMounted(fetchData);
            
            return {
                tabs, activeTab, status, skills, plugins, learnings, userGroups, configData, models,
                modalityPlugins, modalitySettings, modalityTestInput, modalityTestResult,
                showModelModal, showSkillModal, newModel, newSkill, modelsByLayer,
                registerModel, createSkill, deleteSkill, togglePlugin, deleteUserGroup, renderMarkdown,
                toggleModalityPlugin, setModalityWeight, setFusionStrategy, testModalityAnalyze
            };
        }
    }).mount('#app');
    </script>
</body>
</html>'''
