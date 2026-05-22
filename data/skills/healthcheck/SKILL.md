---
name: healthcheck
description: 用 run_command 检查系统 CPU、内存、磁盘等运行状态
version: 1.0.0
emoji: 🏥
always: false
risk: sensitive
min_user_level: admin
min_model_tier: cloud
tags:
  - system
  - health
  - monitoring
---

# 系统健康检查技能

通过 `run_command` 执行系统命令，汇报资源使用情况。

## 常用检查命令

```bash
uptime          # 运行时间 + 负载
free -h         # 内存使用
df -h           # 磁盘空间
top -bn1 | head -20  # CPU + 进程概览
```

## 使用场景

当用户说"检查系统状态"、"服务器还好吗"、"内存够不够" 时触发。

## 输出格式

用 `run_command` 执行命令，把结果整理成中文友好格式回复。发现异常（负载高、磁盘快满）时主动提醒用户。
