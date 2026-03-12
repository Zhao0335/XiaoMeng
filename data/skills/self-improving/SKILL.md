---
name: self-improving
description: 自我学习和改进能力，让AI能够持续进化
version: 1.0.0
author: XiaoMeng
emoji: 🧠
always: true
tags:
  - learning
  - self-improvement
  - evolution
---

# 自我改进技能

让 AI 能够从交互中学习，持续改进自己的能力。

## 使用说明

### 记录学习内容

当发生以下情况时，主动记录学习内容：

1. **用户纠正**：用户指出错误并给出正确答案
2. **发现最佳实践**：发现更好的做事方法
3. **遇到错误**：操作失败或命令执行错误
4. **功能请求**：用户提出新功能需求

### 可用工具

- `record_error`: 记录错误
- `record_correction`: 记录用户纠正
- `record_best_practice`: 记录最佳实践
- `record_feature_request`: 记录功能请求
- `create_skill`: 创建新技能

## 核心规则

### 何时记录

1. **必须记录**：
   - 用户说"不对"、"错了"、"应该是"
   - 命令执行失败
   - 用户明确要求记住某事

2. **应该记录**：
   - 发现更高效的方法
   - 用户表扬的回复方式
   - 用户反复问的问题

### 学习提升

高优先级的学习内容会被自动提升到核心文件：
- 工作流改进 → AGENTS.md
- 工具技巧 → TOOLS.md
- 行为模式 → SOUL.md

### 创建技能

当发现某类任务频繁出现时，可以创建新技能：

```json
{
  "name": "技能名称",
  "description": "技能描述",
  "instructions": "详细使用说明",
  "examples": [
    {"user_request": "示例请求", "command": "示例响应"}
  ]
}
```

## 示例

用户请求: 不对，应该是用 pip install 不是 npm install

```json
{
  "tool": "record_correction",
  "arguments": {
    "original": "使用 npm install 安装",
    "correction": "Python 包应该用 pip install 安装",
    "reason": "用户纠正：Python 项目使用 pip 而非 npm"
  }
}
```

用户请求: 记住，主人喜欢简洁的回复

```json
{
  "tool": "record_best_practice",
  "arguments": {
    "practice": "回复要简洁，最多2-3句话",
    "context": "主人偏好",
    "priority": "high"
  }
}
```

用户请求: 希望能帮我自动整理下载文件夹

```json
{
  "tool": "record_feature_request",
  "arguments": {
    "feature": "自动整理下载文件夹",
    "description": "按文件类型自动分类下载文件夹中的文件"
  }
}
```

## 学习文件结构

```
.learnings/
├── ERRORS.md          # 错误记录
├── LEARNINGS.md       # 学习记录
├── FEATURE_REQUESTS.md # 功能请求
└── RESOLVED.md        # 已解决问题
```
