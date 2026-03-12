---
name: healthcheck
description: 检查系统健康状态
version: 1.0.0
author: XiaoMeng
emoji: 🏥
always: true
tags:
  - system
  - health
  - monitoring
commands:
  check:
    description: 执行系统健康检查
    dispatch:
      kind: tool
      toolName: exec
      argMode: raw
  status:
    description: 获取系统状态概览
    dispatch:
      kind: tool
      toolName: exec
      argMode: raw
---

# 系统健康检查技能

检查系统资源使用情况和服务状态。

## 使用说明

当用户请求检查系统状态时，执行以下检查：

1. **CPU 使用率**
2. **内存使用率**
3. **磁盘空间**
4. **运行时间**

## 核心规则

- 使用系统命令获取信息
- 将结果以友好的方式呈现
- 如果发现异常，提醒用户

## 示例

用户请求: 检查系统状态

```bash
# Windows
systeminfo | findstr /C:"OS" /C:"System Type" /C:"Total Physical Memory" /C:"Available Physical Memory"
wmic cpu get loadpercentage
wmic logicaldisk get size,freespace,caption

# Linux
uptime
free -h
df -h
```

用户请求: 系统健康吗？

```markdown
我来检查一下系统状态...

[执行检查命令]

系统状态报告：
- CPU: [使用率]
- 内存: [使用情况]
- 磁盘: [剩余空间]

[如果有问题，提出建议]
```

## 注意事项

- 不同操作系统使用不同的命令
- 敏感信息不要显示
- 大文件或高负载时提醒用户
