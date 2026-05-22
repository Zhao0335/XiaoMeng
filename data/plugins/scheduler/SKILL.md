---
name: scheduler-plugin
description: 定时任务管理——查看、添加、删除定时任务，启停 scheduler 守护进程
version: 1.2.0
emoji: ⏰
always: false
risk: sensitive
min_user_level: admin
min_model_tier: cloud
tags:
  - scheduler
  - automation
---

# 定时任务管理

管理小萌的定时任务系统，包括每日提醒、定时 AI 指令等。

## 可用工具

| 工具 | 权限 | 功能 |
|------|------|------|
| `scheduler_list` | 管理员+ | 列出所有定时任务 |
| `scheduler_add` | 管理员+ | 添加或更新一个任务 |
| `scheduler_remove` | 管理员+ | 按 id 删除任务 |
| `scheduler_start` | 主人 | 启动 scheduler 守护进程 |
| `scheduler_stop` | 主人 | 停止 scheduler 守护进程 |
| `scheduler_status` | 管理员+ | 查看守护进程运行状态 |

## 任务格式

**注意：target 必须是对象，不能是字符串！**
- 群消息：`{"group_id": 群号}`
- 私聊提醒：`{"user_id": QQ号}`

### cron 类型（定时发固定消息）

```json
{
  "id": "morning-reminder",
  "type": "cron",
  "cron": "9:00",
  "msg": "早安！今天也要加油哦~",
  "target": {"group_id": 123456789},
  "weekdays": ["mon","tue","wed","thu","fri"]
}
```

### instruct 类型（定时触发 AI 指令）

让小萌在指定时间执行一段指令，她会用全部工具能力处理后把结果发给目标。

```json
{
  "id": "daily-quiz",
  "type": "instruct",
  "cron": "9:00",
  "prompt": "请出一道高中数学中等难度的题目，用清晰的格式发给群里",
  "target": {"group_id": 123456789}
}
```

- `prompt`：给小萌的指令，她会当作用户消息处理
- `session_key`（可选）：指定对话会话，**强烈建议显式设置**为 `scheduler:xxx` 格式，避免污染群/私聊对话历史；早/晚配对的任务用同一个 session_key 可互相引用上下文
- `route`（可选）：`"cloud"` 或 `"pro"`，强制指定模型层级，不填则走正常路由（可能路由到 LOCAL）；内容生成任务建议填 `"cloud"`

**适用场景**：每日出题、生成报告、定时搜索最新资讯、智能提醒等需要 AI 动态生成内容的任务。

### interval 类型（间隔发送）

```json
{
  "id": "hourly-ping",
  "type": "interval",
  "interval_minutes": 60,
  "msg": "提醒一下~",
  "target": {"user_id": 123456}
}
```

## 操作流程

### 添加定时任务
1. `scheduler_add` 传入完整任务对象
2. scheduler 会在 5 秒内自动检测 tasks.json 变化并加载
3. `scheduler_status` 确认守护进程在运行

### 查看并修改任务
1. `scheduler_list` 查看现有任务
2. 需要修改时：`scheduler_add` 传入同 id 的新对象（会覆盖）

### 删除任务
- `scheduler_remove` 传入 task_id

### 守护进程管理
- 检查状态：`scheduler_status`
- 未运行时启动：`scheduler_start`（需要主人权限）
- scheduler 进程独立于主 bot，bot 重启不影响它
- **注意**：scheduler 通过 bot 本地中继（`http://127.0.0.1:3003`）发送消息和触发指令，需要 bot 在线
