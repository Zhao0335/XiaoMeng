# XiaoMengCore 快速入门指南

欢迎来到 XiaoMengCore！这是一个让 AI 能够自主学习、持续进化的框架。

## 🚀 5分钟快速开始

### 1. 安装依赖

```bash
cd XiaoMengCore
pip install -r requirements.txt
```

### 2. 启动管理面板

```bash
python run_panel.py
```

访问 http://127.0.0.1:8000 即可看到管理界面。

### 3. 配置模型

在管理面板的「模型管理」中注册你的模型，或直接编辑 `data/config.json`：

```json
{
  "llm": {
    "provider": "ollama",
    "base_url": "http://localhost:11434/v1",
    "model": "qwen2.5:7b"
  }
}
```

### 4. 开始对话

```bash
python main.py
```

## 📁 项目结构

```
XiaoMengCore/
├── data/                    # 数据目录
│   ├── config.json         # 主配置文件
│   ├── config.example.json # 配置示例（带注释）
│   ├── persona/            # 人设文件
│   │   ├── SOUL.md        # 灵魂/性格
│   │   ├── AGENTS.md      # 工作流程
│   │   └── TOOLS.md       # 工具使用指南
│   ├── skills/             # 技能目录
│   │   └── xxx/SKILL.md   # 技能定义
│   ├── memory/             # 记忆存储
│   └── .learnings/         # 学习记录
│       ├── ERRORS.md       # 错误记录
│       ├── LEARNINGS.md    # 学习内容
│       └── FEATURE_REQUESTS.md
├── config/                  # 配置模块
├── core/                    # 核心模块
│   ├── processor.py        # 消息处理器
│   ├── skills.py           # 技能系统
│   ├── tools.py            # 工具系统
│   ├── model_layer.py      # 多模型调度
│   └── self_improving.py   # 自学习系统
└── models/                  # 数据模型
```

## 🎯 核心概念

### 1. 技能 (Skills)

技能是小萌的"能力模块"，用 Markdown 文件定义：

```markdown
---
name: my-skill
description: 技能描述
---

# 技能标题

使用说明...

## 示例
用户请求: 示例请求
响应: 示例响应
```

创建新技能：
- 方式1：在管理面板「技能管理」中创建
- 方式2：在 `data/skills/` 目录创建 `SKILL.md` 文件
- 方式3：让小萌自己创建（使用 `create_skill` 工具）

### 2. 人设 (Persona)

人设文件定义小萌的"性格"：

| 文件 | 用途 |
|------|------|
| SOUL.md | 性格、说话风格、自我认知 |
| AGENTS.md | 工作流程、处理规则 |
| TOOLS.md | 工具使用指南 |
| MEMORY.md | 重要记忆 |
| USER.md | 用户相关信息 |

### 3. 学习系统

小萌会从交互中学习：

```
用户纠正 → 记录到 LEARNINGS.md
操作失败 → 记录到 ERRORS.md
功能需求 → 记录到 FEATURE_REQUESTS.md
重要学习 → 提升到人设文件
```

### 4. 多层模型

三层模型架构让小萌更聪明：

| 层级 | 用途 | 示例模型 |
|------|------|----------|
| Basic | 快速判断、简单问答 | Qwen 7B |
| Brain | 复杂推理、代码生成 | Qwen 14B / GPT-4 |
| Special | 专用任务 | CodeLlama / 视觉模型 |

## 🔧 常用配置

### 添加主人身份

```json
{
  "owner": {
    "user_id": "your_id",
    "identities": [
      {
        "source": "cli",
        "channel_user_id": "your_username"
      }
    ]
  }
}
```

### 添加白名单用户

```json
{
  "whitelist": {
    "enabled": true,
    "users": [
      {"user_id": "friend_001", "display_name": "朋友"}
    ]
  }
}
```

### 注册新模型

```json
{
  "models": {
    "brain_layer": [
      {
        "model_id": "gpt4",
        "layer": "brain",
        "role": "reasoning",
        "endpoint": "https://api.openai.com/v1",
        "model_name": "gpt-4",
        "api_key": "your-api-key"
      }
    ]
  }
}
```

## 💡 使用技巧

### 让小萌记住事情

```
主人：记住，我喜欢简洁的回复
小萌：好的主人，我会记住的~
```

小萌会自动记录到学习文件。

### 让小萌学习新技能

```
主人：帮我创建一个翻译技能
小萌：好的主人，我来创建翻译技能...
```

小萌会使用 `create_skill` 工具创建新技能。

### 纠正小萌的错误

```
小萌：使用 npm install 安装...
主人：不对，这是 Python 项目，应该用 pip
小萌：抱歉主人，我记住了，Python 项目用 pip~
```

小萌会记录这次纠正，下次不会再犯。

## 🐛 常见问题

### Q: 管理面板显示"未连接"

A: 检查配置文件中的模型配置是否正确，确保 Ollama 或其他模型服务正在运行。

### Q: 小萌不执行命令

A: 确保你的身份是"主人"，只有主人有执行命令的权限。

### Q: 如何添加新技能

A: 三种方式：
1. 管理面板 → 技能管理 → 创建技能
2. 在 `data/skills/` 目录创建 `SKILL.md`
3. 让小萌自己创建

### Q: 如何查看学习记录

A: 查看 `data/.learnings/` 目录下的文件，或在管理面板的「学习记录」中查看。

## 📚 进阶话题

### 自定义人设

编辑 `data/persona/SOUL.md` 来自定义小萌的性格。

### 创建插件

在 `plugins/` 目录创建插件，参考现有插件结构。

### 接入新渠道

实现 `Channel` 接口，在配置中启用新渠道。

---

有问题？查看管理面板或阅读源码注释获取更多信息！
