---
name: daily-quiz
description: 每日题目——生成练习题（含答案解析）并定时发到群聊
version: 2.0.0
emoji: 📚
always: false
risk: sensitive
min_user_level: admin
min_model_tier: cloud
tags:
  - quiz
  - scheduler
  - education
---

# 每日题目技能

让小萌每天定时向群里发一道练习题，题目由小萌在触发时即时生成，附带答案和解析。

## 工作方式

定时出题通过 scheduler 的 `instruct` 类型触发——scheduler 在指定时间向小萌发一条指令，小萌生成题目并直接发给目标群/私聊。**不需要预生成队列，直接生成直接发。**

## 配置每日定时出题

当用户说"每天X点在群Y出一道题"时：

**Step 1** — 读取现有任务：
```
read_file("skills/scheduler/tasks.json")
```

**Step 2** — 在 tasks 数组里追加 `instruct` 类型任务：

```json
{
  "id": "daily-quiz-<group_id>",
  "type": "instruct",
  "cron": "9:30",
  "prompt": "请出一道高中数学中等难度的练习题，包含题目、答案、解析，直接发给群里。",
  "target": {"group_id": 123456789},
  "session_key": "scheduler:quiz:<group_id>"
}
```

- `prompt`：给小萌的指令，要明确说"直接发给群里"
- `session_key`：建议使用 `scheduler:quiz:<group_id>` 格式，与群对话历史隔离；同一群早/晚两道题（出题+解析）共享同一 session_key 让小萌能看到早上出了什么

**Step 3** — 写回任务文件：
```
write_file("skills/scheduler/tasks.json", <完整JSON内容>)
```

**Step 4** — 确认 scheduler 在运行：
```
scheduler_status
```
如未运行则启动：`scheduler_start`

## 早/晚题目配对示例

```json
[
  {
    "id": "quiz-morning-123456",
    "type": "instruct",
    "cron": "9:00",
    "prompt": "📚 每日一题！请出一道高中数学中等难度题，告诉大家晚8点发解析，直接发到群里。",
    "target": {"group_id": 123456789},
    "session_key": "scheduler:quiz:123456789"
  },
  {
    "id": "quiz-evening-123456",
    "type": "instruct",
    "cron": "20:00",
    "prompt": "🌙 解析时间！请根据你今天早上出的那道题，发详细解析到群里。",
    "target": {"group_id": 123456789},
    "session_key": "scheduler:quiz:123456789"
  }
]
```

## 即时生成题目

用户想马上看一道题时，直接生成并用 `send_message` 发送预览，询问是否需要配置定时任务。
