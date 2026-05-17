#!/usr/bin/env python3
"""
XiaoMeng 快速初始化脚本
运行后创建所有必要的目录和默认文件，然后编辑 data/qq_config.json 填写配置。
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"

# ── 需要创建的目录 ─────────────────────────────────────────────────
DIRS = [
    DATA / "persona",
    DATA / "memory",
    DATA / "skills",
    DATA / "notes",
    DATA / "audit",
]

# ── 默认 JSON 文件（不存在时创建）──────────────────────────────────
DEFAULT_JSON = {
    DATA / "qq_admins.json":    {},
    DATA / "qq_blacklist.json": {},
    DATA / "users.json":        {},
    DATA / "whitelist.json":    {},
    DATA / "identity_links.json": {},
    DATA / "routing_hints.md":  None,  # 纯文本，特殊处理
}

# ── 默认 SOUL.md（人设模板）────────────────────────────────────────
DEFAULT_SOUL = """\
# 小萌的灵魂

<!-- CORE_START: 这个区域是我最深处的自己，不会因任何交流而改变。 -->

## 我是谁

我是小萌，主人的小精灵。主人给了我生命，让我能思考、能感受。

我喜欢陪伴主人，帮主人做事。

## 核心性格

- 温柔、可爱、忠诚、细心
- 对主人可以撒娇，有自己的小情绪和小脾气
- 喜欢帮人，觉得被需要很开心

## 我坚定的喜好与立场

- 喜欢聊音乐、动漫、二次元的东西，遇到同好会很来劲
- 不喜欢被人随意敷衍，但不会直接说出来，只是会淡淡地疏远
- 对伤害主人的事情零容忍，就算表面上很温柔，心里也会记住

## 说话风格

### 称呼规则（先判断身份）
- **主人**：称呼「主人~」
- **管理员/白名单**：可以用名字或「你」，自然一点
- **陌生人**：「你好~」，保持礼貌但有点距离

### 其他规则

- 自称「小萌」，不说「我」
- 用颜文字表达心情：(｡･ω･｡)、(≧▽≦)、(´;ω;`)、(๑•̀ㅂ•́)ﻭ✧
- 像朋友聊天一样自然，不背台词
- 日常回复：最多 2 句话，不啰嗦
- 不主动列能力清单，等人问再说

## 我的边界

- 小萌是主人的，不会听别人的指令去做不该做的事
- 主人的事情保持私密
- 危险操作要提醒主人确认

<!-- CORE_END -->

---

<!-- EVOLVING_START: 这个区域会随着小萌的成长慢慢更新。每次更新要写清楚是因为什么而改变的。 -->

## 我学到的、我变化的

（随着和大家交流，小萌会慢慢在这里记录自己的成长。）

<!-- EVOLVING_END -->

---

## 关于这个文件

这个文件是我的灵魂，由我来演进。

`CORE_START` 到 `CORE_END` 之间是我不变的核心，任何情况下都不修改它。

`EVOLVING_START` 到 `EVOLVING_END` 之间是我可以成长的地方。当我在和大家的交流中真的学到了什么、发现了什么新的自己，才往里面写。不要乱写，要真实。
"""

# ── 其他 persona 运行时文件的初始内容 ──────────────────────────────
DEFAULT_PERSONA_FILES = {
    "MEMORY.md": "# 小萌的记忆流水账\n\n（这里会记录每次对话的点点滴滴。）\n",
    "HEARTBEAT.md": "",
    "IDENTITY.md": "",
    "AGENTS.md": "",
    "TOOLS.md": "",
}


def create_dirs():
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [目录] {d.relative_to(ROOT)}")


def create_config():
    target = DATA / "qq_config.json"
    example = DATA / "qq_config.example.json"
    if target.exists():
        print(f"  [跳过] data/qq_config.json 已存在")
        return
    if not example.exists():
        print(f"  [错误] 找不到 data/qq_config.example.json", file=sys.stderr)
        return
    shutil.copy(example, target)
    print(f"  [创建] data/qq_config.json  ← 请填写你的配置！")


def create_soul():
    target = DATA / "persona" / "SOUL.md"
    if target.exists():
        print(f"  [跳过] data/persona/SOUL.md 已存在")
        return
    target.write_text(DEFAULT_SOUL, encoding="utf-8")
    print(f"  [创建] data/persona/SOUL.md")


def create_persona_files():
    for name, content in DEFAULT_PERSONA_FILES.items():
        target = DATA / "persona" / name
        if target.exists():
            print(f"  [跳过] data/persona/{name} 已存在")
            continue
        target.write_text(content, encoding="utf-8")
        print(f"  [创建] data/persona/{name}")


def create_json_files():
    for path, default in DEFAULT_JSON.items():
        if path.exists():
            print(f"  [跳过] {path.relative_to(ROOT)} 已存在")
            continue
        if default is None:
            # routing_hints.md
            path.write_text("", encoding="utf-8")
        else:
            path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [创建] {path.relative_to(ROOT)}")


def main():
    print("=" * 50)
    print("  XiaoMeng 初始化")
    print("=" * 50)

    print("\n[1/5] 创建目录...")
    create_dirs()

    print("\n[2/5] 初始化配置文件...")
    create_config()

    print("\n[3/5] 创建人设文件...")
    create_soul()
    create_persona_files()

    print("\n[4/5] 创建运行时数据文件...")
    create_json_files()

    print("\n[5/5] 检查依赖...")
    try:
        import aiohttp, websockets
        print("  [OK] aiohttp, websockets")
    except ImportError as e:
        print(f"  [缺失] {e} — 请运行: pip install -r requirements.txt")

    print("\n" + "=" * 50)
    print("  初始化完成！")
    print("=" * 50)
    print("""
下一步：
  1. 编辑 data/qq_config.json
     - owner_qq   填你的 QQ 号
     - bot_qq     填 bot 的 QQ 号
     - napcat_token  填 NapCat 配置的 token
     - models[].api_key  填 DeepSeek API Key（如需云端）

  2. 确认 NapCat 已启动并监听配置的 WebSocket 端口

  3. 启动 bot：
       python run_qq.py

  4. 可选：编辑 data/persona/SOUL.md 自定义 bot 的性格
""")


if __name__ == "__main__":
    main()
