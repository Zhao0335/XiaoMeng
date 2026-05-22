---
name: self-improving
description: 从交互中学习——记录用户纠正、发现的最佳实践，持续改进行为
version: 1.1.0
emoji: 🧠
always: true
risk: sensitive
min_user_level: stranger
min_model_tier: local
tags:
  - learning
  - memory
  - self-improvement
---

# 自我改进技能

主动记录交互中的学习内容，用现有工具持续改进。

## 何时记录

| 情况 | 操作 |
|------|------|
| 用户说"不对"、"错了"、"应该是" | `add_memory` 记录正确做法 |
| 发现更好的方法 | `add_memory` 记录最佳实践 |
| 用户要求记住某事 | `add_memory` 立即存储 |
| 发现角色/行为需要调整 | `update_soul` 更新 SOUL.md |

## 使用工具

- **`add_memory`**：记录知识、纠正、偏好
- **`search_memory`**：查找已记录的内容避免重复犯错
- **`update_soul`**：调整核心人格和行为准则（主人授权）
- **`write_file`**：写入较大的学习总结到 `data/memory/`

## 原则

- 不等用户提醒——发现错误/纠正时主动记录
- 记录"为什么"而不只是"是什么"
- 同类知识归并，不重复记录
