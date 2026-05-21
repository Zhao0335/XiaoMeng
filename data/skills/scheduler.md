# ⏰ 定时提醒技能 v1.0

## 技术栈

- **APScheduler (AsyncIOScheduler)** — Python 最成熟的定时任务框架
  - 支持 cron 表达式（每天9点、每周一8点等）
  - 支持 interval 间隔（每5分钟、每1小时等）
  - 支持一次性定时（30分钟后提醒）
  - 支持 SQLite 持久化，重启不丢任务
- **httpx** — 异步 HTTP 请求，调用 napcat API 发送 QQ 消息
- **SQLite** — 任务持久化存储

## 架构设计

```
scheduler 进程（独立运行）
    │
    ├── APScheduler（定时调度引擎）
    │   ├── SQLAlchemyJobStore（SQLite 持久化）
    │   └── 任务触发器（cron / interval / date）
    │
    └── httpx → napcat API → 发送QQ消息
```

## 安装

```bash
pip install apscheduler httpx
```

## 核心功能

### 1. 添加定时提醒

```bash
# 一次性提醒（30分钟后）
python3 -c "
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import asyncio

async def send_reminder(msg, group_id=None, user_id=None):
    import httpx
    async with httpx.AsyncClient() as client:
        payload = {'message': msg}
        if group_id:
            payload['group_id'] = group_id
        if user_id:
            payload['user_id'] = user_id
        await client.post('http://127.0.0.1:3002/send_msg', json=payload)

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=datetime.now() + timedelta(minutes=30),
        args=['⏰ 小萌提醒：该休息啦！'],
        kwargs={'group_id': 123456789},
        id='reminder_001',
        replace_existing=True
    )
    scheduler.start()
    await asyncio.sleep(1)

asyncio.run(main())
print('✅ 定时提醒已添加')
"
```

### 2. 启动持久化 scheduler 服务

```bash
# 启动 scheduler 后台服务（持久化任务到 SQLite）
nohup python3 skills/scheduler/main.py > skills/scheduler/scheduler.log 2>&1 &
echo $! > skills/scheduler/scheduler.pid
```

### 3. 停止 scheduler 服务

```bash
kill $(cat skills/scheduler/scheduler.pid) && rm skills/scheduler/scheduler.pid
```

### 4. 查看所有定时任务

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('skills/scheduler/tasks.db')
cursor = conn.cursor()
cursor.execute('SELECT id, next_run_time, job_state FROM apscheduler_jobs')
for row in cursor.fetchall():
    print(f'ID: {row[0]}, 下次执行: {row[1]}')
conn.close()
"
```

## 使用方法

### 用户说「30分钟后提醒我喝水」

1. 通过 `run_command` 调用 Python + APScheduler
2. 添加一次性 date 触发器任务
3. 任务触发时通过 napcat API 发送消息到对应的群/私聊

### 用户说「每天早上9点提醒我签到」

1. 用 cron 触发器：`hour=9, minute=0`
2. 持久化到 SQLite

## 注意事项

- scheduler 需要作为独立进程运行（用 `run_command` 启动）
- 重启机器人后需重新启动 scheduler 进程（或集成到主程序启动时自动拉起）
- 消息发送走 napcat websocket API，确保 napcat 在线
- 建议用 SQLAlchemyJobStore 持久化，避免重启丢任务
- 任务数量过多时注意清理过期的一次性任务

## 待办（后续优化）

- [ ] 集成到主程序启动流程中，自动拉起 scheduler
- [ ] 提供「查看提醒列表」「删除提醒」「修改提醒」的便捷命令
- [ ] 支持重复提醒（每N分钟/小时）
- [ ] 支持带参数的自定义提醒内容
