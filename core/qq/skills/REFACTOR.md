# XiaoMeng Skill 系统重构方案文档

## 一、概述

### 1.1 重构背景

原skill系统存在以下功能性问题：
- 技能仅作为纯文本注入 system prompt，缺乏执行逻辑
- 无技能注册中心，发现机制简陋（仅文件扫描）
- 无权限控制体系，所有用户对所有技能同样可见
- 无模型层级限制，本地14b模型与云端API使用相同工具集
- 缺乏技能生命周期管理（启用/禁用/热加载）

### 1.2 重构目标

基于 **Harness 框架**的先进设计理念，全面重写skill系统，实现：
- **Registry-based dispatch**: 统一注册、发现、过滤、执行管道
- **三级风险分类**: READ_ONLY / SENSITIVE / DANGEROUS
- **模型层级感知**: 本地14b / 云端DeepSeek / Pro 三级工具差异化
- **用户身份权限**: OWNER / ADMIN / STRANGER 基于身份(非QQ号)的权限控制
- **可编程技能注册**: @skill 装饰器 + SKILL.md 文件双向支持
- **完全向后兼容**: 现有 SKILL.md 文件无需修改

---

## 二、架构设计

### 2.1 总体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                       QQGateway                                 │
│  init_skill_registry(skills_dir)  ← 启动时初始化                │
│  build_context_skills_prompt()     ← 上下文感知技能prompt       │
│  get_tool_schemas_for_context()    ← 上下文感知工具schema       │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SkillRegistry (单例)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  register() │  │   get()     │  │  get_for_context()      │ │
│  │  enable()   │  │  reload()   │  │  get_tool_schemas()     │ │
│  │  disable()  │  │ validate()  │  │  get_active_prompt_..() │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  _skills: Dict[str, SkillDefinition]                      │  │
│  │  _perm_checker: SkillPermissionChecker                    │  │
│  │  _loader: SkillLoader                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────┬───────────────────────────────────────────────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌────────┐┌────────┐┌──────────────┐
│ Skill  ││ Skill  ││SkillPermission│
│Loader  ││Executor││   Checker    │
└────────┘└────────┘└──────────────┘
```

### 2.2 模块依赖关系

```
skills/__init__.py        # 公共API导出
├── definition.py          # 核心数据类（SkillRisk, ModelTier, UserLevel, SkillDefinition, SkillPermission）
├── loader.py              # 文件加载 + @skill 装饰器
├── registry.py            # 注册中心（单例）
├── executor.py            # 执行引擎（SkillContext + SkillExecutor）
├── permissions.py         # 权限检查器
└── schema.py              # 工具Schema生成器

外部调用:
  tools.py ──> skills/    (load_skills_prompt, build_context_skills_prompt, get_tool_schemas_for_context)
  gateway.py ──> tools.py + skills/  (init_skill_registry, SkillContext, ModelTier, UserLevel)
```

---

## 三、核心组件详解

### 3.1 SkillRisk（风险等级）

类比 Harness 的 `read-only / effectful` 风险分类：

| 等级 | 枚举值 | 含义 | 最低模型层级 |
|------|--------|------|-------------|
| READ_ONLY | 0 | 只读操作（搜索、读取） | LOCAL (14b) |
| SENSITIVE | 1 | 敏感操作（写文件、发消息） | CLOUD (DeepSeek) |
| DANGEROUS | 2 | 危险操作（执行命令、删除） | PRO |

### 3.2 ModelTier（模型层级）

对应项目现有的三层模型架构 [model_layer.py](file:///home/qwq/zcx_ai_group_friend/XiaoMeng/core/model_layer.py)：

| 层级 | 对应路由 | 对应 ModelLayer | 典型模型 |
|------|---------|-----------------|---------|
| LOCAL | "LOCAL" | BASIC | Ollama Qwen 14b |
| CLOUD | "CLOUD" | BRAIN | DeepSeek API |
| PRO | "PRO" | PRO | DeepSeek 最强模型 |

### 3.3 UserLevel（用户权限）

对应 [permissions.py](file:///home/qwq/zcx_ai_group_friend/XiaoMeng/core/qq/permissions.py) 的 PermLevel：

| 等级 | 对应 PermLevel | 典型场景 |
|------|---------------|---------|
| STRANGER | STRANGER (0) | 陌生人的群/私聊消息 |
| ADMIN | ADMIN (1) | 管理员命令 |
| OWNER | OWNER (2) | Bot主人的全部权限 |

### 3.4 SkillDefinition（技能定义）

```python
@dataclass
class SkillDefinition:
    name: str                       # 技能唯一标识
    description: str                # 技能描述
    version: str                    # 版本号
    author: str                     # 作者
    risk: SkillRisk                 # 风险等级
    permission: SkillPermission     # 权限要求
    tags: List[str]                 # 标签
    emoji: str                      # 图标
    enabled: bool                   # 是否启用
    always_active: bool             # 是否总是注入prompt
    body: str                       # 技能正文（Markdown）
    source_file: str                # 源文件路径
    handler: Optional[Callable]     # 可选的执行handler
    metadata: Dict[str, Any]        # 扩展元数据
```

### 3.5 SkillPermission（权限定义）

```python
@dataclass
class SkillPermission:
    min_user_level: UserLevel       # 最低用户级别
    min_model_tier: ModelTier       # 最低模型层级
    allowed_identities: List[str]   # 身份白名单（覆盖最低级别）
```

**权限判断逻辑**：
1. 模型层级检查：`当前模型层级 >= 技能最低模型层级`
2. 用户级别检查：`当前用户级别 >= 技能最低用户级别`
3. 身份白名单：若用户级别不满足，检查是否在 identity 白名单中

### 3.6 SkillRegistry（注册中心）

单例模式，全局唯一入口：

```python
registry = SkillRegistry.get_instance()

# 初始化（启动时）
registry.init_loader("./data/skills")

# 上下文感知查询（核心）
skills = registry.get_for_context(
    model_tier=ModelTier.CLOUD,
    user_level=UserLevel.ADMIN,
    identity="owner",
)

# 工具schema生成
schemas = registry.get_tool_schemas(tier, level, identity)

# 管理操作
registry.enable("code-assistant")
registry.disable("healthcheck")
registry.reload()  # 热加载
registry.validate_all()  # 校验所有技能
```

### 3.7 @skill 装饰器（编程式注册）

类比 Harness 的 `#[harness::skill]` proc-macro：

```python
from core.qq.skills import skill, SkillContext, ModelTier, UserLevel

@skill(
    name="my-skill",
    description="我的自定义技能",
    risk="sensitive",
    min_user_level="admin",
    min_model_tier="cloud",
)
async def my_skill(ctx: SkillContext) -> str:
    """handler 函数，SkillRegistry 自动注册"""
    return f"处理完成，当前用户: {ctx.identity}"
```

### 3.8 SkillContext（执行上下文）

```python
@dataclass
class SkillContext:
    model_tier: ModelTier           # 当前模型层级
    user_level: UserLevel           # 当前用户级别
    identity: str                   # 用户身份名（非QQ号）
    session_key: str                # 会话标识
    sender_qq: int                  # QQ号
    tool_executor: Any              # 工具执行器实例
    extra: Dict[str, Any]           # 扩展数据

    @classmethod
    def from_gateway(cls, route, perm_level, identity, ...):
        """从 gateway 上下文构建 SkillContext"""
```

---

## 四、权限控制逻辑

### 4.1 三重权限检查流程图

```
用户消息
  │
  ▼
路由判决 (LOCAL / CLOUD / PRO)
  │
  ├──> ModelTier 确定
  │
  ▼
权限查询 (OWNER / ADMIN / STRANGER)
  │
  ├──> UserLevel 确定
  │
  ▼
Identity 解析 (data/identity_links.json)
  │
  ├──> identity 字符串确定
  │
  ▼
SkillPermissionChecker.filter_skills()
  │
  ├── 检查1: skill.enabled == True?
  ├── 检查2: ModelTier >= skill.permission.min_model_tier?
  ├── 检查3: UserLevel >= skill.permission.min_user_level?
  │          └── 若不满足 → identity in skill.permission.allowed_identities?
  │
  ▼
返回可用技能列表
```

### 4.2 本地模型 vs 云端模型的工具差异

| 工具 | LOCAL (14b) | CLOUD (DeepSeek) | PRO |
|------|:-----------:|:----------------:|:---:|
| search_memory | ✅ | ✅ | ✅ |
| recall_conversations | ✅ (ADMIN+) | ✅ (ADMIN+) | ✅ |
| web_search | ❌ | ✅ | ✅ |
| add_memory | ❌ | ✅ | ✅ |
| update_soul | ❌ | ✅ | ✅ |
| send_voice | ❌ | ✅ | ✅ |
| read_file | ❌ | ✅ | ✅ |
| write_file | ❌ | ✅ (ADMIN+) | ✅ |
| delete_file | ❌ | ✅ (ADMIN+) | ✅ |
| run_command | ❌ | ❌ | ✅ (OWNER) |
| send_message | ❌ | ✅ | ✅ |
| list_files | ❌ | ✅ | ✅ |

### 4.3 基于身份(非QQ号)的权限控制

系统通过 `data/identity_links.json` 建立 **QQ号 → 身份名** 的映射：

```json
{
    "3797723137": "owner",
    "123456789": "admin_zhang",
    "987654321": "owner"
}
```

- 同一身份名下多个QQ号共享权限（如上例中两个QQ号都是OWNER）
- Skill 可通过 `allowed_identities` 字段精确授权给指定身份
- 权限判断不依赖QQ号本身，而是解析后的 identity 字符串

---

## 五、与现有系统的集成要点

### 5.1 启动初始化

[gateway.py](file:///home/qwq/zcx_ai_group_friend/XiaoMeng/core/qq/gateway.py) 在 `QQGateway.__init__` 中：

```python
# 初始化 SkillRegistry（启动时加载所有技能文件）
init_skill_registry(self._skills_dir)
```

### 5.2 工具调用循环中的集成

在 `_make_task_coro_factory` 中：

```python
# 1. 创建 SkillContext
skill_ctx = SkillContext.from_gateway(
    route=route, perm_level=level, identity=identity, ...
)

# 2. 路由后更新上下文
skill_ctx.model_tier = ModelTier.from_route(route)

# 3. 上下文感知的技能 prompt
skills_section = build_context_skills_prompt(
    self._skills_dir, skill_ctx.model_tier, skill_ctx.user_level, identity,
)

# 4. 上下文感知的工具 schema
active_tools = get_tool_schemas_for_context(
    TOOL_SCHEMAS, skill_ctx.model_tier, skill_ctx.user_level, identity,
)
```

### 5.3 向后兼容

`tools.py` 中保留了 `load_skills_prompt()` 函数，内部委托给新的 `SkillRegistry`：

```python
def load_skills_prompt(skills_dir: str) -> str:
    """[向后兼容] 内部委托给 SkillRegistry + SkillExecutor"""
    registry = init_skill_registry(skills_dir)
    skills = registry.list_enabled()
    # ... 构建prompt ...
```

所有现有调用方无需修改。

---

## 六、如何添加新技能

### 方式一：SKILL.md 文件（推荐）

在 `data/skills/` 下创建 `.md` 文件：

```markdown
---
name: my-new-skill
description: 我的新技能描述
version: 1.0.0
risk: read_only          # read_only / sensitive / dangerous
permission:
    min_user_level: admin
    min_model_tier: cloud
tags:
    - custom
always: true             # true = 自动注入prompt
---

# My New Skill

技能的具体指令正文...
```

### 方式二：@skill 装饰器（编程式）

```python
from core.qq.skills import skill, SkillContext, SkillRegistry

@skill(
    name="my-skill",
    description="我的自定义技能",
    risk="sensitive",
    min_user_level="admin",
    min_model_tier="cloud",
)
async def my_skill_handler(ctx: SkillContext) -> str:
    # 自定义执行逻辑
    return "任务完成"
```

### 方式三：运行时热加载

```python
registry = SkillRegistry.get_instance()
registry.reload()  # 重新扫描文件系统
```

---

## 七、新增/修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `core/qq/skills/__init__.py` | 新增 | 公共API导出 |
| `core/qq/skills/definition.py` | 新增 | 核心数据定义 |
| `core/qq/skills/loader.py` | 新增 | 文件加载+装饰器 |
| `core/qq/skills/registry.py` | 新增 | 注册中心(单例) |
| `core/qq/skills/executor.py` | 新增 | 执行引擎+上下文 |
| `core/qq/skills/permissions.py` | 新增 | 权限检查器 |
| `core/qq/skills/schema.py` | 新增 | Schema生成器 |
| `core/qq/tools.py` | 修改 | 集成SkillRegistry |
| `core/qq/gateway.py` | 修改 | 集成SkillRegistry+上下文感知 |

---

## 八、设计原则总结

| Harness 原则 | 本项目实现 |
|-------------|-----------|
| Registry-based dispatch | SkillRegistry 单例 + 统一注册/发现 |
| Risk classification | SkillRisk (READ_ONLY/SENSITIVE/DANGEROUS) |
| Model Connector Abstraction | ModelTier 抽象层 (LOCAL/CLOUD/PRO) |
| RBAC + Policy Gates | SkillPermissionChecker 三重检查 |
| Event-based hook system | SkillExecutor 上下文感知执行 |
| Feedforward context | build_active_prompt() 按权限注入 |
| Plugin architecture | @skill 装饰器 + SKILL.md 双向注册 |
| Sandbox isolation | 工具执行器沙箱 (`_resolve_workspace_path`) |
| Governance layer | Identity 映射 + 用户级别 + 模型层级三合一 |
