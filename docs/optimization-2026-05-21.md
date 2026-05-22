# XiaoMeng 代码优化报告

**日期**: 2026-05-21  
**范围**: `core/qq/gateway.py`、`core/model_layer.py`、`data/qq_config.json`、`data/skills/formula_render.md`、`core/qq/formula.py`（新增）

---

## 一、新增功能（本次优化前已实现）

### 1.1 LaTeX 公式渲染 (`core/qq/formula.py`)

新增独立模块，让小萌能在聊天中自动渲染数学公式并以图片发送。

**实现机制**：
- AI 回复中用 `$$...$$` 包裹 LaTeX 公式
- 系统检测到公式后，先发送文字（`$$...$$` 替换为 `[见下方公式图]`），再逐个发送公式图片
- 图片通过 OneBot v11 CQ 码 `[CQ:image,file=base64://...]` 发送

**渲染两级 Fallback**：
| 阶段 | 引擎 | 覆盖范围 |
|------|------|---------|
| Stage 1 | 系统 LaTeX + dvipng (`usetex=True`) | 完整 LaTeX 语法，含 `\begin{pmatrix}` `\begin{cases}` `\begin{aligned}` 等环境 |
| Stage 2 | matplotlib mathtext（内置） | 常见公式符号，无需系统 LaTeX |

**缓存策略**：
- 缓存目录：`data/formula_cache/formula_<md5>.png`
- 相同公式命中缓存，不重复渲染
- 每次渲染前自动清理超过 1 小时的旧文件

**安装依赖**：
```bash
pip install matplotlib
sudo apt install dvipng texlive-latex-extra cm-super fonts-cmu
```

**技能文件**：`data/skills/formula_render.md`（`always: true`，注入 system prompt，让 AI 知道何时使用 `$$...$$`）

---

## 二、代码优化

### 2.1 删除死代码：`_generate_reply` 方法

**文件**：`core/qq/gateway.py`  
**删除行数**：293 行（原文件 1969 行 → 1680 行，减少 **15%**）

**背景**：`_generate_reply` 是历史遗留的同步回复生成方法，所有消息处理流程已全部迁移到 `_make_task_coro_factory`（基于异步任务池），`_generate_reply` 从未被任何代码调用。

**风险**：无。该方法在整个代码库中没有任何调用点（通过全文 grep 确认）。

---

### 2.2 清理未使用的 import

**文件**：`core/qq/gateway.py`

| 移除的 import | 原因 |
|--------------|------|
| `ReActConfig, ReActLoop` | 计划中的重构尚未实现，代码中只有注释提及 |
| `format_group_context` | 从 `onebot_events` 导入但从未调用 |
| `SkillExecutor, SkillRegistry` | 从 `.skills` 导入但从未调用（`init_skill_registry` 来自 `.tools`，保留）|
| `Event`（基类）| 只用到具体子类（`GroupMsgEvent` 等），基类本身未使用 |

同时移除了 `_clean_reply` 静态方法内部的重复 `import re`（顶层已经导入）。

---

### 2.3 修复裸 `except:` 异常捕获

**文件**：`core/model_layer.py`（3 处）

裸 `except:` 会捕获 `KeyboardInterrupt`、`SystemExit` 等系统级异常，导致程序无法被正常停止。

| 位置 | 原代码 | 修复后 |
|------|--------|--------|
| OpenAI 流式解析 JSON | `except:` | `except (json.JSONDecodeError, KeyError, IndexError):` |
| Ollama 流式解析 JSON | `except:` | `except (json.JSONDecodeError, KeyError):` |
| 模型分类器结果解析 | `except:` | `except Exception:` |

---

### 2.4 修复静默吞掉的异常（无日志）

**文件**：`core/qq/gateway.py`（4 处）

原代码在 `except` 块中直接 `return` 或 `return []`，不记录任何日志，导致数据库故障时完全无法排查。

| 方法 | 原代码 | 修复后 |
|------|--------|--------|
| `_get_recent_messages` | `except Exception: return []` | `except Exception as e: logger.debug(...); return []` |
| `_get_long_term_memory` | `except Exception: return ""` | `except Exception as e: logger.debug(...); return ""` |
| `_maybe_compress` | `except Exception: return` | `except Exception as e: logger.debug(...); return` |
| 路由文本解析 | `except Exception: decision_text = "LOCAL"` | `except Exception as _re: logger.debug(f"路由文本解析失败: {_re}"); ...` |

---

## 三、配置整理

### 3.1 删除废弃配置文件

| 文件 | 处置 |
|------|------|
| `data/config.json` | **移除**（备份为 `config.json.bak`）。该文件是旧版系统的遗留，整个代码库无任何引用 |
| `data/qq_config.json` | **唯一生效的配置文件**，`run_qq.py` 从此读取所有设置 |

### 3.2 重新整理 `qq_config.json` 结构

- 删除无效字段 `bot_qq`（代码中从未读取）
- 按功能重新分组（机器人基础 → 网络 → 模型 → TTS → 群聊行为 → 主动发言 → 记忆 → 触发词 → LLM 超时 → 其他）
- 每个模型增加 `_注释` 字段说明用途
- 顶部增加 `_注意` 字段说明这是唯一配置文件

### 3.3 切换 BASE 模型

| 项目 | 原值 | 新值 |
|------|------|------|
| 模型名称 | `qwen2.5:14b` | `qwen3.6-35B` |
| 接入点 | `http://localhost:11434`（本地 Ollama） | `http://192.168.12.167:8907/v1` |
| API Key | 无 | `sk-ahRV0NpiN5DTHqm1zmGbpA` |
| LOCAL 最大输出 | 600 tokens | 4096 tokens（35B 输出质量高，不必限死）|
| `num_ctx` | 8192（Ollama 专有字段）| 移除（OpenAI 兼容 API 不需要）|

---

---

## 四、后续补充改动（同日下午）

本节记录优化报告写完后继续完成的功能与修复。

---

### 4.1 路由器回退本地 Ollama

**背景**：将 BASE 模型切换为 qwen3.6-35B 后，路由器（`max_tokens=20`）因 thinking 模式无法在 20 token 内同时输出思考链和决策词，导致路由结果为空。

**修复**：路由器 (`qwen-router`) 回退到 `qwen2.5:14b` @ `http://localhost:11434`，轻量 Ollama 模型不走 thinking 模式，无此问题。

---

### 4.2 Thinking 模型空结果问题

**现象**：qwen3.6-35B 回复空消息或把思考内容直接发到群里。

**根因**：
- vllm 服务的 Qwen3 默认开启 thinking 模式
- thinking 内容输出为 `<think>...</think>`，`_clean_reply` 正则剥除后正文为空
- 尝试的 `enable_thinking: false` 参数被该 vllm 服务器忽略

**最终修复**（`core/model_layer.py`）：
- `ModelEndpoint` 新增 `thinking: Optional[str]` 字段，取值 `"disable"` / `None`
- OpenAI adapter `chat()` 中：若 `thinking == "disable"`，在 payload 加 `enable_thinking: false`，并在 system prompt 末尾注入 `/no_think`（Qwen3 chat-template 级别指令，不依赖服务器参数支持）

**配置变更**（`data/qq_config.json`）：
```json
{ "model_id": "qwen-local", "thinking": "disable", "capabilities": ["vision", "tool_call"] }
```

---

### 4.3 模型能力声明（capabilities）

**背景**：`ModelEndpoint.capabilities` 字段早已存在但从未被读取，所有模型都被无条件传入 vision 图片和 tool schemas。

**改动**（`core/qq/gateway.py` + `core/model_layer.py`）：
- `_build_router()` 从配置读取 `capabilities` 和 `thinking` 字段写入 `ModelEndpoint`
- 图片附加前检查 `"vision" in adapter.endpoint.capabilities`，非 vision 模型不传图片数据

**当前各模型声明**：

| model_id | capabilities |
|----------|-------------|
| qwen-router | `[]` |
| qwen-local | `["vision", "tool_call"]` |
| deepseek-cloud | `["tool_call"]`（未声明，默认空） |
| deepseek-pro | `["tool_call"]`（未声明，默认空） |

后续若换用支持 vision 的 CLOUD/PRO 模型，只需在配置加 `"vision"` 即可，代码不用动。

---

### 4.4 图片 Vision 支持

#### 4.4.1 图片接收与传递

**之前**：图片 URL 追加为 `[用户发送了图片: https://...]` 文本，模型看到的是字符串。  
**现在**：
- 事件处理器提取原始 attachment data dict（含 `file` 字段），文本侧仅写 `[图片]` 占位符
- `_make_task_coro_factory(image_atts=...)` 接收附件元数据

#### 4.4.2 NapCat 图片获取（`_att_to_b64`）

三级获取策略，依次尝试：

| 优先级 | 方式 | 说明 |
|--------|------|------|
| 1 | NapCat `get_file` WebSocket API | 返回本地缓存路径，直接读文件，无需网络 |
| 2 | 直接读本地文件路径 | `file` 字段本身就是绝对路径时 |
| 3 | HTTP URL 下载 | QQ CDN（当前服务器 DNS 无法解析，基本失败，保留作兜底）|

**关键发现**：NapCat NTQQ 版本不支持旧接口 `get_image`（超时），正确接口是 `get_file`，图片缓存在 `/root/.config/QQ/nt_qq_.../nt_data/Emoji/emoji-recv/` 下。

#### 4.4.3 Vision 消息格式（`_attach_images_to_last_msg`）

对 vision-capable adapter，将最后一条 user 消息从字符串格式转为 OpenAI vision list 格式：
```json
{"role": "user", "content": [
  {"type": "text", "text": "用户: 帮我看看这张图"},
  {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
]}
```

#### 4.4.4 非 vision 模型的图片描述中转（`_describe_images`）

若路由选中的 adapter 无 vision 但 local 有 vision：
1. 先调用 local adapter，system prompt 为"描述图片内容，不超过 200 字"
2. 描述结果注入消息：`[图片]` → `[图片内容：图中有一块单片机电路板…]`
3. 清空 `image_atts`，原 CLOUD/PRO adapter 正常接收带描述的文本消息
4. 若描述失败，降级到 local 直接处理

**完整路由决策树**：
```
有图片？
├── 否 → 正常路由
└── 是 → active adapter 有 vision？
          ├── 是 → 直接附加图片 base64（vision 直连）
          └── 否，local 有 vision？
                ├── 是 → local 描述图片 → 描述注入消息 → 原 adapter 处理
                └── 否 → 保留 [图片] 占位，模型知道有图但看不见
```

---

### 4.5 `_clean_reply` 改进

新增 Qwen3 thinking fallback：`<think>` 块剥除后若正文为空，取最后一段思考内容作为回复（防止思考过程无正文时发出空消息）。

---

## 五、代码质量专项（下午第二轮）

继续在上一轮基础上做代码审查，三个代理并行检查后发现并修复以下问题。

### 5.1 提取代理环境变量逻辑（`model_layer.py`）

`OpenAICompatibleAdapter` 和 `OllamaAdapter` 各有两个方法（`chat` + `chat_stream`），都包含相同的 14 行代理设置/还原块，共 4 份拷贝。

**修复**：在 `BaseModelAdapter` 上新增 `_get_proxy()` + `@staticmethod _clear_proxy_env()` context manager，每个调用点从 14 行缩减为 2 行：

```python
_proxy, _proxy_ctx = self._get_proxy()
with _proxy_ctx:
    async with aiohttp.ClientSession(...) as session:
        ...
```

### 5.2 简化 `/no_think` 注入（`model_layer.py`）

原来用 `for msg in full_messages: ... break; else: insert` 的 for-else 结构。由于 system prompt 在构建时始终被 `prepend` 到首位，直接检查 `full_messages[0]["role"] == "system"` 即可。

### 5.3 gateway.py 清理（死代码、冗余）

| 项 | 改动 |
|----|------|
| `from ..model_layer import ModelLayer, ModelRole` | 删除 `_run` 闭包内的重复 import（顶层已导入） |
| `import pathlib` × 2 | 删除 `_att_to_b64` 内的函数级 import，改用顶层 `Path` |
| `/no_think` in `_describe_images` system prompt | 删除（adapter 自身的 thinking disable 逻辑已注入） |
| `getattr(endpoint, "capabilities", [])` × 3 | 改为直接 `.endpoint.capabilities`（字段有 default_factory） |
| `getattr(getattr(active_adapter,"endpoint",None),"max_tokens",8192)` | 改为 `active_adapter.endpoint.max_tokens` |
| `# 获取昵称` | 删除（函数名已自文档化） |

### 5.4 并行图片下载（`gateway.py`）

`_describe_images` 和 `_attach_images_to_last_msg` 原来串行 `await` 每张图片。改为 `asyncio.gather(*[self._att_to_b64(att) for att in image_atts])`，多图时并行下载。

### 5.5 Tool-call 能力门控（`gateway.py`）

新增：仅当 `"tool_call" in active_adapter.endpoint.capabilities` 时才构建 tool schemas，否则传空列表（不会发给 API，`if tools:` 在 adapter 层已拦截）。同步更新 `qq_config.json`：deepseek-cloud/pro 显式声明 `"capabilities": ["tool_call"]`，qwen-router 声明 `"capabilities": []`。

### 5.6 图片占位符优化（`gateway.py`）

`[图片]` → `[图片（需要视觉理解）]`，路由器在 3 条上下文消息中看到此文本时更容易判断需要 vision。对应的 `replace()` 和 `re.sub()` 正则同步更新。

---

## 六、Bug 修复专项（下午第三轮）

三代理并行代码审查后发现的真实 bug，全部修复。

### 6.1 DB 连接在异常路径泄漏（gateway.py + pool.py）

原代码模式：
```python
conn = sqlite3.connect(...)
conn.execute(...)
conn.commit()
conn.close()   # 若 execute/commit 抛异常，这行不会执行
```

**影响方法**：`_save_message`、`_get_recent_messages`、`_get_long_term_memory`、`_maybe_compress`（gateway.py），`TaskPool._save`（pool.py）。

**修复**：将 `conn = connect()` 移到 `try` 外，`conn.close()` 移到 `finally` 块。

### 6.2 后台任务无引用导致 GC 取消 + 异常静默（`gateway.py`）

原代码：
```python
asyncio.create_task(self._compress_memory(session_key))  # 无引用
asyncio.create_task(self._fetch_and_cache_group_name(group_id))
```

Python 文档明确指出：若没有强引用保存 Task，GC 可能在任务完成前将其取消。且任务内抛出的异常无处可见。

**修复**：新增 `_bg_tasks: set` 和 `_create_bg_task()` 辅助方法：

```python
def _create_bg_task(self, coro) -> asyncio.Task:
    t = asyncio.create_task(coro)
    self._bg_tasks.add(t)
    t.add_done_callback(self._bg_tasks.discard)
    t.add_done_callback(lambda task: logger.warning(...) if task.exception() else None)
    return t
```

所有 `asyncio.create_task()` 调用改为 `self._create_bg_task()`。

### 6.3 Ollama adapter 内函数级 logging import（`model_layer.py`）

`OllamaAdapter.chat()` 内有 `import logging as _logging; _logging.getLogger(__name__).info(...)` —— 每次调用都重新 import，且绕过了模块统一的 logger 管理。

**修复**：在 `model_layer.py` 顶部增加 `import logging` 和 `logger = logging.getLogger(__name__)`，函数内改为 `logger.info(...)`。

### 6.4 `should_use_special()` 异常静默（`model_layer.py`）

```python
except Exception:
    pass   # JSON 解析失败、网络错误、ModelRole 非法值，一律无声吞掉
```

**修复**：改为 `except Exception as e: logger.debug(f"should_use_special 解析失败: {e}")`。

### 6.5 scheduler/main.py 裸 `except:`（`data/skills/scheduler/main.py`）

3 处裸 `except:` 会捕获 `KeyboardInterrupt`、`SystemExit`，导致脚本无法被 Ctrl+C 停止。

**修复**：全部改为 `except Exception:`。

---

## 七、变更统计（全日汇总）

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `core/qq/gateway.py` | 删死代码、清 import、修异常、vision 管线、bug 修复 | 净 -295 行（早期）+ vision+gating 约 +150 行 |
| `core/model_layer.py` | 提取 proxy、修 except、`thinking`、`/no_think`、logger | **±60 行** |
| `core/qq/formula.py` | 新增（公式渲染模块） | **+243 行** |
| `core/tasks/pool.py` | DB 连接泄漏修复 | **±5 行** |
| `data/qq_config.json` | 重整结构、切模型、capabilities/thinking 补全 | 重写 |
| `data/skills/formula_render.md` | 新增（技能文件） | 新增 |
| `data/skills/scheduler/main.py` | 裸 except 修复 | **3 行** |
| `data/config.json` | 归档（移除） | -73 行 |

---

## 八、已知遗留问题（暂不处理）

| 问题 | 位置 | 说明 |
|------|------|------|
| `OpenAICompatibleAdapter` 与 `OllamaAdapter` `chat_stream` 逻辑几乎相同 | `model_layer.py` | 可提取到基类，改动面较广，留待专项重构 |
| `scheduler/main.py` 硬编码 `NAPCAT_API = "http://127.0.0.1:3002"` | `data/skills/scheduler/` | 需从配置读取 |
| 历史消息中 `[图片（需要视觉理解）]` 占位符永久存储于 DB | `gateway.py` | 对历史 vision 消息有一定帮助（告知模型曾有图），暂不清除 |
| `os.environ` 在 `parallel_chat()` 并发时潜在竞争 | `model_layer.py` | 当前配置无 `proxy=""` 的 adapter，不触发；若未来添加需加锁 |
| async generator `_busy` 未完全消费时重置依赖 GC | `model_layer.py` | `chat_stream` 目前在主流程未大量使用，低优先级 |

---

## 九、下一步方向

### 优先级 A：功能完善

1. **消息历史图片回溯**  
   当前图片 base64 只在当前轮传给模型，不持久化。历史消息中只有文字占位符。  
   方案：messages 表增加 `attachments TEXT` 列，存储 `file_id` JSON 列表。`_build_messages` 重建时对最近 N 条含图消息重新拉取 base64（或在压缩时生成文字摘要替换占位符）。

2. **CLOUD/PRO Vision 支持**  
   当 DeepSeek API 未来支持 vision 时，只需在 `qq_config.json` 对应 model 加 `"vision"` 到 capabilities，代码零改动。  
   目前 `deepseek-v4-flash/pro` 不支持，配置正确反映了现状。

3. **主动发言质量**  
   `ProactiveManager` 当前用固定的 system prompt。可接入 SOUL.md + 当前群上下文，让主动发言更自然。

### 优先级 B：稳定性

4. **`_compress_memory` 失败时重试或降级**  
   压缩任务是后台任务，失败只 warning。消息条数若持续累积（一直没有成功压缩），会导致 context 越来越长。可在失败时记录失败时间，下次触发时跳过或重试。

5. **数据库连接池**  
   当前每个 DB 操作新建/销毁连接。高并发群消息场景下有开销。可用 `threading.local` 维护线程本地连接，或用 `aiosqlite` 改为全异步操作。

6. **`scheduler/main.py` 从配置读 `NAPCAT_API`**  
   目前硬编码 `http://127.0.0.1:3002`，与 `qq_config.json` 的 `napcat_ws_url` 分离，改配置时容易漏改。

### 优先级 C：架构

7. **`MessageBuilder` 独立类**  
   `_build_messages`、`_build_system_prompt`、图片注入、描述注入逻辑目前都散落在 `_make_task_coro_factory` 闭包内。提取到独立类后可单独测试，也便于未来支持多模态历史消息。

8. **`chat_stream` 统一用法**  
   目前 `chat_stream` 存在于两个 adapter 但在主流程未使用（所有回复走非流式 `chat()`）。若未来加打字机效果，需要确保流式路径的异常处理和 `_busy` 重置都正确。
