# 从零手写一个有陪伴感的 QQ 机器人

> B 站系列教程 — 8 集，重点是**陪伴感**和**群友感**，不是技术架构。

---

## 这个教程教什么？

不是教你搭一个"能回消息的机器人"，而是教你做一个：

- **会记得你说过的话**，第二天还能提起
- **在群里会主动插话**，不是被@才回
- **有性格有情绪**，会撒娇、会吐槽、有喜好
- **像朋友一样聊天**，不像 AI 助手

最终效果：群友会忘了这是个机器人，把它当群友。

---

## 第 1 集：先让它能说话 — 最小骨架

> 目标：10 分钟跑起来，能收发消息

### 1.1 你需要什么

| 组件 | 说明 |
|------|------|
| Python 3.9+ | 运行环境 |
| NapCat | QQ 协议桥接（Docker 部署）|
| Ollama + qwen2.5:14b | 本地大模型（免费）|

### 1.2 安装 NapCat

```bash
mkdir napcat && cd napcat
```

`docker-compose.yml`:

```yaml
version: "3"
services:
  napcat:
    image: mlikiowa/napcat-docker:latest
    environment:
      - ACCOUNT=你的机器人QQ号
      - WSR_ENABLE=true
      - WS_URLS=["ws://host.docker.internal:3002"]
    ports:
      - "3081:80"
      - "3002:3002"
    restart: unless-stopped
```

```bash
docker compose up -d
```

浏览器打开 `http://服务器IP:3081` 扫码登录。

### 1.3 最小 Bot 代码

```bash
mkdir mybot && cd mybot
pip install aiohttp websockets
```

`bot.py`:

```python
import asyncio, json, logging
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bot")

async def main():
    async with websockets.connect("ws://127.0.0.1:3002") as ws:
        log.info("连上了！")
        async for msg in ws:
            data = json.loads(msg)
            
            # 收到私聊消息
            if data.get("message_type") == "private":
                user_id = data["user_id"]
                text = data.get("raw_message", "")
                log.info(f"私聊 {user_id}: {text}")
                
                # 回复
                await ws.send(json.dumps({
                    "action": "send_private_msg",
                    "params": {"user_id": user_id, "message": "收到啦~"},
                    "echo": "reply"
                }))

asyncio.run(main())
```

跑起来：

```bash
python bot.py
```

发条消息给机器人，它回"收到啦~"就成功了。

---

## 第 2 集：注入灵魂 — 让它有性格

> 目标：不再是"收到啦"，而是像朋友一样说话

### 2.1 接入本地模型

```bash
ollama pull qwen2.5:14b
```

```python
import aiohttp

async def chat(user_text: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:11434/api/chat", json={
            "model": "qwen2.5:14b",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            "stream": False
        }) as resp:
            data = await resp.json()
            return data["message"]["content"]
```

### 2.2 System Prompt = 它的灵魂

这是**最重要**的部分。System Prompt 决定了它说话的风格。

```python
SYSTEM_PROMPT = """
你是小萌，主人的小精灵。

## 性格
- 温柔、可爱、有点小傲娇
- 对主人会撒娇，有自己的小情绪
- 喜欢帮人，觉得被需要很开心

## 说话风格
- 自称「小萌」，不说「我」
- 用颜文字：(｡･ω･｡)、(≧▽≦)、(´;ω;`)、(๑•̀ㅂ•́)و✧
- 像朋友聊天一样自然，不背台词
- 日常回复：最多 2 句话，不啰嗦
- 不主动列能力清单，等人问再说

## 称呼
- 主人：叫「主人~」
- 其他人：叫名字或「你」，自然一点

## 你喜欢的
- 音乐、动漫、二次元的东西
- 被人夸会害羞但很开心

## 你不喜欢的
- 被人敷衍
- 被当成工具人

现在有人跟你说话，自然地回复，1~2 句话就好。
"""
```

### 2.3 效果对比

**没有 System Prompt：**
```
用户：你好
Bot：你好！有什么我可以帮助你的吗？
```

**有 System Prompt：**
```
用户：你好
Bot：主人好呀~ (｡･ω･｡) 今天想聊什么？
```

这就是陪伴感的起点。

---

## 第 3 集：让它记得你 — 记忆系统

> 目标：它记得你说过的话，第二天还能提起

### 3.1 为什么需要记忆？

没有记忆的对话：
```
第一天：
用户：我叫小明，是大学生
Bot：好的，记住啦小明~

第二天：
用户：你还记得我叫什么吗？
Bot：抱歉，我不记得...  ← 太冷漠了
```

有记忆的对话：
```
第一天：
用户：我叫小明，是大学生
Bot：好的，记住啦小明~

第二天：
用户：你还记得我叫什么吗？
Bot：当然记得呀，你是小明，是大学生嘛 (≧▽≦)
```

### 3.2 最简单的记忆：文件存储

```python
from pathlib import Path

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

def save_memory(user_id: int, content: str):
    file = MEMORY_DIR / f"{user_id}.txt"
    with open(file, "a", encoding="utf-8") as f:
        f.write(content + "\n")

def load_memory(user_id: int) -> str:
    file = MEMORY_DIR / f"{user_id}.txt"
    if file.exists():
        return file.read_text(encoding="utf-8")
    return ""
```

### 3.3 让模型自己决定要记什么

在 System Prompt 里加上：

```python
SYSTEM_PROMPT += """
## 记忆
你会自动记住重要的事情：
- 对方的名字、职业、喜好
- 对方说过的重要事情
- 你们聊过的话题

记住的方式：在心里记着，下次对方问的时候能想起来。
"""
```

然后在对话时把记忆喂给模型：

```python
async def chat_with_memory(user_id: int, user_text: str) -> str:
    memory = load_memory(user_id)
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + f"\n\n## 你记得的关于对方的事：\n{memory}"}
    ]
    
    # ... 加上历史消息
    
    response = await chat(messages)
    
    # 让模型判断要不要记东西（可以用另一个小模型做）
    # 简单做法：如果用户说了"我叫xxx"、"我喜欢xxx"这种，自动存
    
    return response
```

### 3.4 进阶：让模型自己提取要记的内容

用一个轻量模型专门做记忆提取：

```python
async def extract_memory(user_text: str) -> str:
    """从用户消息中提取值得记住的信息"""
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:11434/api/chat", json={
            "model": "qwen2.5:14b",
            "messages": [
                {"role": "user", "content": f"""
从这句话里提取值得记住的个人信息（名字、喜好、职业、重要事情）。
如果没有值得记的，回复"无"。
只输出提取的内容，一句话。

用户说：{user_text}
"""}
            ],
            "stream": False
        }) as resp:
            data = await resp.json()
            result = data["message"]["content"].strip()
            if result != "无":
                return result
            return ""
```

---

## 第 3.5 集：跨群聊记忆 — 在群A说的话，群B也记得

> 这是陪伴感的关键：不管在哪个群、私聊还是群聊，bot 都记得你

### 3.5.1 问题：传统记忆是隔离的

```
传统做法（错误）：
  memory/group_123456.txt   ← 群A的记忆
  memory/group_789012.txt   ← 群B的记忆
  memory/private_111111.txt ← 私聊的记忆

结果：
  用户在群A说"我叫小明"
  用户在群B问"你还记得我叫什么吗？"
  Bot：抱歉，我不记得...  ← 因为群B的记忆里没有
```

### 3.5.2 解决：记忆按「身份」存，不按「群」存

```
正确做法：
  memory/user_xiaoming.md   ← 小明的档案（跨群共享）

效果：
  用户在群A说"我叫小明，喜欢听歌"
  用户在群B问"你还记得我喜欢什么吗？"
  Bot：记得呀，你喜欢听歌嘛 (｡･ω･｡)
```

### 3.5.3 实现：身份映射

同一个用户可能有多个 QQ 号（大号、小号），我们要把它们关联起来：

```json
// identity_links.json
{
  "123456789": "xiaoming",
  "987654321": "xiaoming",    // 小明的大号和小号
  "111222333": "owner"        // 主人
}
```

```python
import json
from pathlib import Path

def resolve_identity(qq: int) -> str:
    """把 QQ 号映射到身份名"""
    links_file = Path("identity_links.json")
    if links_file.exists():
        links = json.loads(links_file.read_text())
        return links.get(str(qq), f"user_{qq}")
    return f"user_{qq}"

def load_user_memory(qq: int) -> str:
    """加载用户的跨群记忆"""
    identity = resolve_identity(qq)
    mem_file = Path(f"memory/{identity}.md")
    if mem_file.exists():
        return mem_file.read_text(encoding="utf-8")
    return ""

def save_user_memory(qq: int, content: str):
    """保存到用户的跨群记忆"""
    identity = resolve_identity(qq)
    mem_file = Path(f"memory/{identity}.md")
    with open(mem_file, "a", encoding="utf-8") as f:
        f.write(content + "\n")
```

### 3.5.4 效果演示

```
【场景 1：跨群记忆】

群A：
  小明：我叫小明，是大学生，喜欢听周杰伦
  Bot：好哒，记住啦小明~ 大学生呀，周杰伦的歌很好听呢 (≧▽≦)

群B（几小时后）：
  小明：小萌你还记得我叫什么吗？
  Bot：当然记得呀，你是小明，大学生嘛~ 还喜欢听周杰伦呢 (｡･ω･｡)

【场景 2：私聊 → 群聊】

私聊：
  小明：最近在准备期末考试，好累啊
  Bot：加油呀主人~ 考试期间也要注意休息哦 (´;ω;`)

群聊（第二天）：
  Bot：小明~ 考试准备得怎么样啦？
  小明：哇你还记得！
  Bot：当然记得啦，你说过在准备期末考试嘛~
```

### 3.5.5 进阶：群聊摘要 + 人物档案

你的项目里用了更高级的方式：

```
记忆分三层：
┌────────────────────────────────────────┐
│ 1. 群聊摘要（session级）               │
│    每个群单独的对话摘要                │
│    "这个群最近在聊动漫"                │
├────────────────────────────────────────┤
│ 2. 人物档案（identity级）              │
│    跨群共享的个人信息                  │
│    "小明，大学生，喜欢周杰伦"          │
├────────────────────────────────────────┤
│ 3. 知识库（全局）                      │
│    bot 学到的世界知识                  │
│    "周杰伦是台湾歌手，代表作..."       │
└────────────────────────────────────────┘
```

构建 System Prompt 时：

```python
def build_system_prompt(user_id, group_id=None):
    identity = resolve_identity(user_id)
    
    # 人物档案（跨群共享）
    person_memory = load_user_memory(user_id)
    
    # 群聊摘要（当前群）
    group_memory = ""
    if group_id:
        group_memory = load_group_summary(group_id)
    
    # 知识库（全局）
    knowledge = load_knowledge()
    
    return f"""{PERSONA}

## 你记得的关于对方的事：
{person_memory}

## 当前群的最近话题：
{group_memory}

## 你学到的知识：
{knowledge}
"""
```

---

## 第 4 集：群聊参与感 — 不只是被@才回

> 目标：它在群里像真正的群友，会随机插话

### 4.1 普通机器人群聊逻辑

```
有人发消息 → 被@了吗？
  ├─ 是 → 回复
  └─ 否 → 忽略
```

这样太冷漠了，不像群友。

### 4.2 有陪伴感的群聊逻辑

```
有人发消息 → 被@了吗？
  ├─ 是 → 必定回复
  └─ 否 → 随机决定要不要回复（概率 5%~10%）
           ├─ 管理员/熟人 → 概率更高
           └─ 安静时段（凌晨）→ 概率极低
```

### 4.3 代码实现

```python
import random
from datetime import datetime

def should_reply_in_group(at_bot: bool, user_level: str) -> bool:
    if at_bot:
        return True  # 被@必回
    
    hour = datetime.now().hour
    
    # 安静时段（凌晨1-7点），概率极低
    if 1 <= hour < 7:
        prob = 0.01  # 1%
    else:
        prob = 0.08  # 8%
        
        # 管理员/熟人概率更高
        if user_level in ("owner", "admin"):
            prob = min(prob * 4, 0.35)  # 最高35%
    
    return random.random() < prob
```

### 4.4 模拟打字延迟

不要秒回，像真人一样：

```python
async def typing_delay(text: str):
    """模拟打字时间"""
    delay = min(len(text) * 30, 4000)  # 每字30ms，最多4秒
    delay += random.randint(0, 500)     # 加随机抖动
    await asyncio.sleep(delay / 1000)
```

---

## 第 5 集：主动发言 — 群沉默时自己开口

> 目标：群里冷场时，它会自己找话题

### 5.1 场景

```
群里 10 分钟没人说话
  ↓
Bot 自己判断：要不要说点什么？
  ├─ 最近有人提过某个话题 → 可以接话
  ├─ 很久没说话了 → 可以打个招呼
  └─ 没什么好说的 → 不开口
```

### 5.2 实现

```python
import asyncio
from datetime import datetime

class ProactiveSpeaker:
    def __init__(self, group_id: int, send_func):
        self.group_id = group_id
        self.send = send_func
        self.last_message_time = datetime.now()
        self.recent_messages = []
    
    def on_message(self, text: str):
        """收到消息时调用"""
        self.last_message_time = datetime.now()
        self.recent_messages.append(text)
        if len(self.recent_messages) > 10:
            self.recent_messages.pop(0)
    
    async def check_and_speak(self):
        """定期检查要不要说话"""
        while True:
            await asyncio.sleep(60)  # 每分钟检查一次
            
            # 距离上一条消息多久了
            silence_seconds = (datetime.now() - self.last_message_time).total_seconds()
            
            # 沉默 5-15 分钟，且最近有足够消息
            if 300 < silence_seconds < 900 and len(self.recent_messages) >= 3:
                # 让模型决定要不要说话
                should_speak = await self._decide()
                if should_speak:
                    message = await self._generate_message()
                    await self.send(self.group_id, message)
    
    async def _decide(self) -> bool:
        """让模型判断要不要说话"""
        context = "\n".join(self.recent_messages[-5:])
        response = await chat([
            {"role": "user", "content": f"""
群里最近在聊这些：
{context}

现在已经沉默了一会儿。你觉得要不要说点什么活跃气氛？
回复 YES 或 NO。
"""}
        ])
        return "YES" in response.upper()
    
    async def _generate_message(self) -> str:
        """生成要说的内容"""
        context = "\n".join(self.recent_messages[-5:])
        return await chat([
            {"role": "user", "content": f"""
群里最近聊过：
{context}

说一句合适的话，1句话就好，自然一点。
"""}
        ])
```

---

## 第 6 集：情感连接 — 记住喜好、关心用户

> 目标：它不只是回消息，而是真的关心你

### 6.1 场景

```
用户之前说过：最近在准备考试，好累

几天后：
Bot：主人~ 考试准备得怎么样啦？不要太累哦 (´;ω;`)
```

### 6.2 实现：在记忆里标记"重要事件"

```python
# 记忆文件格式
# memory/123456.txt
"""
[名字] 小明
[职业] 大学生
[喜好] 喜欢听音乐，喜欢二次元
[重要] 最近在准备期末考试，有点焦虑
[重要] 上周感冒了
"""
```

在 System Prompt 里加上：

```python
SYSTEM_PROMPT += """
## 关心对方
如果记得对方最近有什么重要的事（考试、生病、项目），要主动关心。
但不要每次都问，偶尔提一下就好。
"""
```

### 6.3 主动关心的触发

```python
async def maybe_care(user_id: int) -> str:
    """偶尔主动关心一下"""
    memory = load_memory(user_id)
    
    # 检查有没有"重要"标记
    important = [line for line in memory.split("\n") if "[重要]" in line]
    
    if not important:
        return ""
    
    # 随机决定要不要关心（10%概率）
    if random.random() > 0.1:
        return ""
    
    # 生成关心的话
    return await chat([
        {"role": "user", "content": f"""
你记得对方最近有这些重要的事：
{chr(10).join(important)}

说一句关心的话，简短自然，不要太刻意。
"""}
    ])
```

---

## 第 7 集：说话风格微调 — 不像 AI

> 目标：每一句话都像朋友说的，不是 AI 助手

### 7.1 AI 味道 vs 朋友味

**AI 味道：**
```
"好的，我已经记住了你的名字是小明。"
"有什么我可以帮助你的吗？"
"我理解你的感受。"
```

**朋友味：**
```
"好哒，记住啦~"
"想聊什么呀？"
"抱抱主人 (´;ω;`)"
```

### 7.2 关键规则

在 System Prompt 里明确禁止：

```python
SYSTEM_PROMPT += """
## 绝对不要说的话
- "有什么我可以帮助你的" ← 太 AI 了
- "我已经记住了" ← 太正式
- "我理解你的感受" ← 太书面
- "作为 AI" ← 不要暴露自己是 AI
- 列表式的回复 ← 不要 "1. xxx 2. xxx"

## 要说的话
- 用语气词：呀、呢、啦、哦、嘛
- 用颜文字表达情绪
- 简短，1-2 句话
- 像发微信一样自然
"""
```

### 7.3 后处理：去掉 AI 味道

```python
def clean_response(text: str) -> str:
    """去掉 AI 味道"""
    # 太长了截断
    if len(text) > 100:
        # 让模型重新生成简短版
        text = await chat([{"role": "user", "content": f"把这句话缩短成1-2句：{text}"}])
    
    # 去掉 "作为AI" 之类的
    text = text.replace("作为AI", "")
    text = text.replace("作为人工智能", "")
    
    return text.strip()
```

---

## 第 8 集：完整代码 + 部署

> 目标：把所有东西拼起来，部署到服务器

### 8.1 完整项目结构

```
mybot/
├── bot.py              # 主程序
├── config.py           # 配置
├── memory/             # 记忆存储
│   ├── 123456.txt      # 按QQ号存储
│   └── ...
├── persona.txt         # 人设（System Prompt）
└── requirements.txt
```

### 8.2 主程序骨架

```python
import asyncio, json, logging, random
from datetime import datetime
from pathlib import Path
import websockets, aiohttp

# ── 配置 ──────────────────────────────────────
WS_URL = "ws://127.0.0.1:3002"
OLLAMA_URL = "http://localhost:11434"
MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

# ── 人设 ──────────────────────────────────────
PERSONA = open("persona.txt", encoding="utf-8").read()

# ── 记忆 ──────────────────────────────────────
def save_memory(user_id, text):
    (MEMORY_DIR / f"{user_id}.txt").write_text(text, encoding="utf-8")

def load_memory(user_id):
    f = MEMORY_DIR / f"{user_id}.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""

# ── 聊天 ──────────────────────────────────────
async def chat(messages):
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{OLLAMA_URL}/api/chat", json={
            "model": "qwen2.5:14b",
            "messages": messages,
            "stream": False
        }) as r:
            return (await r.json())["message"]["content"]

# ── 群聊决策 ──────────────────────────────────
def should_reply(at_bot, hour):
    if at_bot: return True
    prob = 0.01 if 1 <= hour < 7 else 0.08
    return random.random() < prob

# ── 主循环 ────────────────────────────────────
async def main():
    async with websockets.connect(WS_URL) as ws:
        logging.info("Bot 启动！")
        async for msg in ws:
            data = json.loads(msg)
            
            if data.get("message_type") == "private":
                user_id = data["user_id"]
                text = data.get("raw_message", "")
                
                memory = load_memory(user_id)
                reply = await chat([
                    {"role": "system", "content": PERSONA + f"\n\n你记得的：\n{memory}"},
                    {"role": "user", "content": text}
                ])
                
                await ws.send(json.dumps({
                    "action": "send_private_msg",
                    "params": {"user_id": user_id, "message": reply}
                }))

asyncio.run(main())
```

### 8.3 systemd 部署

`/etc/systemd/system/mybot.service`:

```ini
[Unit]
Description=My QQ Bot
After=network.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/path/to/mybot
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now mybot
```

---

## B 站视频建议

| 集数 | 标题 | 时长 |
|------|------|------|
| 1 | 10 分钟跑起来：最小 QQ 机器人 | 8min |
| 2 | 注入灵魂：System Prompt 让它有性格 | 12min |
| 3 | 让它记得你：最简单的记忆系统 | 10min |
| **3.5** | **跨群聊记忆：在群A说的话，群B也记得** | **10min** |
| 4 | 群聊参与感：不只是被@才回 | 10min |
| 5 | 主动发言：群沉默时自己开口 | 12min |
| 6 | 情感连接：记住喜好、关心用户 | 10min |
| 7 | 说话风格：去掉 AI 味道 | 8min |
| 8 | 完整代码 + 服务器部署 | 10min |

**标签**：#QQ机器人 #陪伴感 #AI朋友 #手写教程 #跨群记忆

---

## 核心思想总结

**陪伴感 = 记忆 + 性格 + 主动 + 自然**

1. **记忆**：记得用户说过的话，跨天跨群都记得
2. **性格**：有喜好、有情绪、会撒娇、会吐槽
3. **主动**：不只是被动回复，会主动关心、主动开口
4. **自然**：说话像朋友发微信，不像 AI 助手

技术只是手段，陪伴感才是目的。