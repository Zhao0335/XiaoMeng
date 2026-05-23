# 内心世界（Inner World）技术文档

> 版本：2026-05-23 / 小萌项目 v5

---

## 一、概述

内心世界是小萌项目中一个**自主空闲时间系统**：当 bot 长时间没有收到任何消息、任务池也为空时，小萌不会只是静止等待——她会进入自己的"内心世界"，用 CLOUD 级别模型自主决定做点什么。

这个系统的核心目标是让 AI 具备"时间感"和"自我驱动"，而不只是被动响应刺激。

---

## 二、整体架构

```
                        ┌─────────────────────────────┐
                        │       QQGateway              │
                        │                             │
                        │  ┌──────────────────────┐  │
每次用户消息到来 ──────► │  │ _last_any_msg_time   │  │
                        │  └──────────────────────┘  │
                        │                             │
                        │  ┌──────────────────────┐  │
                        │  │  _inner_world_watchdog│  │  每 60s 检查一次
                        │  │  (asyncio 后台任务)   │  │
                        │  └────────┬─────────────┘  │
                        └──────────┼──────────────────┘
                                   │ 条件满足时触发
                                   ▼
                        ┌─────────────────────────────┐
                        │      InnerWorldAgent.run()   │
                        │                             │
                        │  1. 读 SOUL.md + MEMORY.md  │
                        │  2. 读 events.jsonl (近20条)│
                        │  3. 加载 skills + tools      │
                        │  4. CLOUD LLM 决策           │
                        │  5. 工具调用循环 (≤10次)     │
                        │  6. 写 state.json            │
                        └─────────────────────────────┘

每次用户消息结束后（异步后台）：
    compress_session_to_event()
    → LOCAL LLM 生成一句感受
    → append 到 events.jsonl
```

### 模块划分

| 文件 | 职责 |
|------|------|
| `core/inner_world/agent.py` | `InnerWorldAgent`：平台无关的主执行体 |
| `core/inner_world/events.py` | `InnerWorldEventLogger`：事件流写入/读取；`compress_session_to_event()`：感受压缩 |
| `core/qq/gateway.py` | watchdog 循环、触发条件判断、`_make_inner_world_executor()` |
| `core/qq/task_runner.py` | 每次回复后触发后台压缩任务 |

---

## 三、触发机制

watchdog 每 **60 秒**轮询，满足以下**全部**条件才触发：

```python
# gateway.py _inner_world_watchdog()
not _in_quiet_hours(hour)                                     # 非静默时段
now - _last_any_msg_time >= iw_idle_threshold                 # ≥ 15分钟无任何消息
not any(task.status in (PENDING, RUNNING, WAITING_USER) ...)  # 任务池完全空闲
now - _last_inner_world_time >= iw_cooldown                   # 距上次触发 ≥ 30分钟
```

默认值均可通过 `config.json` 的 `inner_world` 块覆盖：

```json
{
  "inner_world": {
    "idle_threshold": 900,
    "cooldown": 1800
  }
}
```

触发后，`_inner_world_agent.run()` 以后台任务形式执行，**不阻塞** watchdog 本身（下一分钟仍会检查，但 cooldown 已更新为当前时间，不会重复触发）。

---

## 四、事件流：`events.jsonl`

每次小萌回复用户消息后，`task_runner.py` 启动一个后台协程：

```python
compress_session_to_event(
    session_key,          # 来源（如 "group:1073211277"）
    last_exchange,        # "用户：xxx\n小萌：xxx"
    local_adapter,        # LOCAL 模型
    event_logger,
    soul=soul,            # 注入人设，让感受更贴合角色
)
```

LOCAL 模型被要求用**一句话（≤15字）** 从第一人称描述这次交流的感受，写入 `data/inner_world/events.jsonl`：

```jsonl
{"ts": "2026-05-23T14:30", "source": "group:1073211277", "summary": "哥哥问了我一个有趣的问题，我答得挺好"}
{"ts": "2026-05-23T15:12", "source": "private:3797723137", "summary": "帮哥哥查了一首歌，有点开心"}
```

文件上限 200 条，超出后保留最新 150 条（滚动窗口）。

**内心世界触发时**，这 20 条事件会被格式化成时间线注入 system prompt，作为小萌"最近经历"的背景：

```
2026-05-23T14:30 [group:1073211277] 哥哥问了我一个有趣的问题，我答得挺好
2026-05-23T15:12 [private:3797723137] 帮哥哥查了一首歌，有点开心
```

---

## 五、执行上下文

`InnerWorldAgent.run()` 中，工具执行器以 **OWNER 权限**构建：

```python
QQToolExecutor(
    session_key = "inner_world",
    sender_qq   = owner_qq,
    level       = PermLevel.OWNER,
    identity    = "owner",
    target_id   = owner_qq,   # 默认发消息给主人
    is_private  = True,
)
```

可用工具与 CLOUD 模型 + OWNER 权限下的对话完全一致：`web_search`、`add_memory`、`read_file`、`write_file`、`run_command`、插件工具（B站、音乐、scheduler）等。

Skills prompt 通过 `build_context_skills_prompt(skills_dir, ModelTier.CLOUD, UserLevel.OWNER)` 动态加载，新增插件自动出现在内心世界可用范围中，**无需改代码**。

---

## 六、与传统 Agent 模式的对比

### 传统响应型 Agent

```
用户输入 → [LLM 推理] → [工具调用*N] → 回复用户 → 结束
```

- 完全被动，无输入则无行为
- 生命周期 = 一次请求
- 上下文 = 本次对话历史
- 目标 = 满足用户当前需求

### 本项目内心世界 Agent

```
计时器触发 → [读取历史感受] → [LLM 自主决策] → [工具调用*N] → 写状态 → 结束
                   ↑
每次普通对话结束后异步写入 events.jsonl
```

| 维度 | 传统响应型 | 内心世界 |
|------|-----------|---------|
| 触发方式 | 用户输入 | 计时器（空闲条件） |
| 行为目标 | 回答用户问题 | 自主决定（可以什么都不做） |
| 上下文来源 | 当前会话历史 | 跨群事件流 + 全局记忆 |
| 执行权限 | 由用户等级决定 | 固定 OWNER 权限 |
| 生命周期 | 一个任务 | 独立后台协程 |
| 结果去向 | 发给用户 | 写 state.json，可能主动发消息 |

### 与 Cron/定时任务的区别

定时任务（如 scheduler）是**确定性的**：时间到了就执行预设的消息。内心世界是**非确定性的**：不知道小萌会做什么，她自己决定——可能刷 B 站，可能写记忆，可能什么都不做。

---

## 七、优势

**1. 跨会话连续性**
events.jsonl 把来自所有群、私聊的交流感受串成一条时间线。内心世界触发时，小萌不是"第一次启动"，而是带着最近经历的记忆进入自由时间，行为更有连贯性。

**2. 与现有工具体系零摩擦**
`InnerWorldAgent` 完全复用 `QQToolExecutor` 和 `SkillRegistry`，新装的插件自动可用，不需要专门适配。

**3. 平台无关**
`core/inner_world/` 不依赖任何 QQ 协议代码，只通过注入的 `executor_factory` 和 `router` 与平台交互。移植到其他平台只需换一个 executor factory。

**4. 低开销**
watchdog 只是一个每 60s 唤醒一次的 asyncio 协程，event 压缩是后台任务，对主请求路径零影响。

**5. 可配置**
idle_threshold 和 cooldown 可以在 config.json 里调，不同部署场景可以调整节奏。

---

## 八、局限性分析

### 8.1 由项目资源限制导致的局限

**（1）事件压缩质量差**

`compress_session_to_event` 用的是 LOCAL 模型（Ollama）。LOCAL 模型能力有限，生成的感受句子：
- 容易不贴合小萌人设
- 有时语义重复（连续多条"帮哥哥解答了问题"）
- 小模型经常无法严格遵守字数限制

根本原因是用 CLOUD 模型做压缩成本太高（每次对话结束都调用一次），只能用 LOCAL。

**（2）事件流维度单一**

events.jsonl 每条只有时间戳 + 来源 + 一句感受，没有：
- 话题标签（聊了什么类别的事）
- 情绪强度评分
- 与哪个人的对话（来源只写群/私聊 key）

`emotion` 字段已经预留在数据结构里，但目前全部为空——LOCAL 模型生成情绪标签的稳定性更差，暂时禁用。

**（3）内心世界只能主动发消息给主人**

executor 的 `target_id = owner_qq`，初始化时写死。内心世界触发时没有"当前会话"，无法动态确定目标群/用户。CLOUD 模型的能力完全够用——这不是模型或资源的问题，是工具封装层的设计缺陷：像 `send_voice` 这类直接发消息的工具，都依赖 executor 里固定的 `target_id`，导致内心世界只能默认发给主人私聊。想发给某个群，模型只能绕道用 `run_command` 手动调 NapCat API。

---

### 8.2 技术设计层面的缺陷

**（1）内心世界没有持久意图（No persistent intent）**

每次触发都是完全独立的：小萌不知道上次内心世界做了什么（只能通过 state.json 的 `last_activity` 字段读到 200 字摘要）。她无法实现"上次没查完，这次继续"这样的多次触发连贯行为。

从架构上看，缺少一个"意图持久化层"：本次内心世界结束时，应该能把"未完成的意图"写成结构化数据，下次触发时注入上下文。

**（2）事件流是扁平追加，无语义检索**

events.jsonl 是顺序文件，只能取最近 N 条。内心世界无法问"上周和群里聊过什么有趣的话题"，也无法按情绪或主题筛选。

理想情况下应该有向量索引（embedding + 相似度检索），但这需要额外的 embedding 服务和存储，目前未集成。

**（3）事件时间戳精度只到分钟**

```python
"ts": time.strftime("%Y-%m-%dT%H:%M")
```

同一分钟内多条事件无法区分顺序，也无法计算"距上次交流多少秒"这类细粒度时间感知。

**（4）内心世界与主消息循环共享 event loop**

`_inner_world_agent.run()` 是后台 `asyncio.Task`，与处理用户消息的协程运行在同一 event loop。如果内心世界里的工具调用（如 `run_command` 执行一个耗时命令）长时间占用 CPU，会影响其他任务的调度。

目前没有专属的 executor/process 隔离，也没有对内心世界设置 CPU 时间预算。

**（5）工具调用结果不被记忆**

内心世界里调用 `web_search` 查到的信息，如果小萌没有主动调 `add_memory` 保存，结果就随着这次会话消失了。模型不一定每次都记得保存。传统对话里 system prompt 有明确的"搜到信息后必须保存"指令，但内心世界的 prompt 目前没有这条约束。

**（6）无法感知其他用户的存在**

events.jsonl 的来源是 `session_key`（如 `group:1073211277`），小萌知道"在群里聊过"，但不知道"是谁发的消息"——因为压缩时只保留感受摘要，原始发言者信息丢失了。这使内心世界缺乏"人际关系维度"：她无法思考"最近哥哥说了什么让我在意的话"。

---

## 九、未来可能的改进方向

> 这里只列技术可行路径，不代表计划实现。

| 问题 | 可能的解法 |
|------|-----------|
| 事件压缩质量差 | 在对话量不大时改用 CLOUD 模型压缩；或改成模板提取而非生成 |
| 无持久意图 | 内心世界结束时写 `pending_intents.json`，下次读取并注入 |
| 无语义检索 | 集成 ChromaDB（项目里已有 `data/chroma/` 目录），events 入库时同时写向量 |
| 发消息限制 | 工具层新增带 `group_id`/`user_id` 参数的发消息工具，或 executor 支持在工具调用时动态指定目标 |
| event loop 共享 | 内心世界改在 `asyncio.run_in_executor(ThreadPoolExecutor)` 中运行 |
| 工具结果不被记忆 | system prompt 里加强"必须 add_memory"约束，或在工具循环结束后自动提示 |
| 发言者信息丢失 | events.jsonl 增加 `participants` 字段，记录参与者 QQ/昵称 |

---

## 十、数据文件一览

```
data/inner_world/
├── events.jsonl    # 滚动事件流（最多 200 条，自动 trim 到 150）
└── state.json      # 最近一次内心世界的运行状态
                    # 字段：last_triggered, last_finished, status, last_activity
```

`state.json` 示例：
```json
{
  "last_triggered": 1716451200.0,
  "status": "done",
  "last_activity": "搜索了一首歌的歌词，感觉挺好听的",
  "last_finished": 1716451380.0
}
```