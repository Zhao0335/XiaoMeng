# 小萌 QQ Bot 图片理解能力实现文档

> 最后更新：2026-05-21  
> 基于 NapCatQQ + OneBot v11 + qwen3.6-35B (litellm 代理)

---

## 一、模型架构与图片处理策略

| model_id | 模型 | 角色 | vision | thinking |
|----------|------|------|--------|---------|
| qwen-router | qwen2.5:14b（Ollama） | 路由判断 | ✗ | ✗ |
| qwen-local | qwen2.5:14b（Ollama） | LOCAL 聊天主力 | ✗ | ✗ |
| qwen-vision | qwen3.6-35B（litellm） | 专职图片描述/转述 | ✓ | 禁用（`"thinking":"disable"`） |
| deepseek-cloud | DeepSeek flash | CLOUD | ✗（可扩展） | ✗ |
| deepseek-pro | DeepSeek pro | PRO | ✗（可扩展） | ✗ |

**设计原则：**
- `qwen-local`（14b）负责 LOCAL 路由的实时聊天，秒级响应，不做图片处理
- `qwen-vision`（35B）专职图片描述，始终在后台运行，不参与主流程路由，不阻塞用户
- LOCAL 聊天超时时自动降级 CLOUD，而非直接报错

**图片处理决策树：**

```
收到图片
    │
    ├─ 后台 _bg_classify_and_save（每条含图消息都触发，vision_adapter，timeout=120s）
    │       → 描述存入 DB，供后续历史上下文使用
    │
    └─ Bot 决定响应？
        ├─ active adapter 有 vision（未来扩展）
        │   ├─ 直接附 base64 发给模型回答
        │   └─ 后台 _save_img_desc_to_db（vision_adapter，timeout=120s）
        │
        └─ active adapter 无 vision（当前所有路由）
            ├─ vision_adapter 存在 → _describe_images(timeout=120s, allow_thinking)
            │       ├─ 成功 → 描述注入消息，发给 active adapter
            │       └─ 失败 → 直接切换 vision_adapter 带图回答
            └─ vision_adapter 不存在 → 无图片上下文，直接回答
```

---

## 二、关键问题与解决方案

### 2.1 图片文件权限问题

**问题：** NapCat 运行在 Docker 容器中，以 root 身份创建图片文件。文件权限为 `0600`（仅 root 可读），Bot 进程以 `qwq` 用户运行，读取时报 `Permission denied`。

**双重坑：**
- NapCat 返回的是容器内部路径 `/root/.config/QQ/...`
- 宿主机实际路径是 `/home/qwq/napcat_xiaomeng/qq_volume/...`

**解决方案：**

**① 路径重映射（`gateway.py` 中 `_att_to_b64`）：**
```python
if str(p).startswith("/root/.config/QQ/"):
    p = Path("/home/qwq/napcat_xiaomeng/qq_volume") / str(p)[len("/root/.config/QQ/"):]
```

**② 新文件权限修复（systemd 服务 `qq-img-chmod`）：**

QQ 每下载一张新图，inotifywait 立即 `chmod o+r`：

```bash
# /usr/local/bin/qq-img-chmod.sh
inotifywait -m -r -e create,moved_to --format '%w%f' \
    /home/qwq/napcat_xiaomeng/qq_volume 2>/dev/null |
while IFS= read -r file; do
    chmod o+r "$file" 2>/dev/null || true
done
```

服务文件 `/etc/systemd/system/qq-img-chmod.service` 开机自启。

> **注意：** `setfacl` 默认 ACL 在此场景无效，因为 Docker 容器写文件时设置的 umask 导致 ACL mask 为 `---`，使 ACL 权限失效。必须用 inotifywait 事后 chmod。

---

### 2.2 视觉模型返回空内容（reasoning_content fallback）

**问题：** 调用 qwen3.6-35B（经 litellm 代理）时，`content` 字段为空。

**根因：** litellm 代理将 Qwen3 的 thinking 过程放入 `reasoning_content`，`content` 留空。

**解决方案（`model_layer.py`）：**
```python
content = msg.get("content") or ""
reasoning_content = (
    msg.get("reasoning_content")
    or msg.get("reasoning")
    or choice.get("reasoning_content")
    or ""
)
if not content and reasoning_content:
    content = reasoning_content
```

---

### 2.3 图片描述超时：thinking 策略与超时分层

**根本原则：LOCAL/路由器禁止 thinking（快速响应）；描述/转述任务可以 thinking（不阻塞用户）。**

**分层 timeout：**

| 调用路径 | timeout | allow_thinking | 是否阻塞用户 |
|----------|---------|----------------|------------|
| CLOUD/PRO 转述用描述 | 120s | ✓ | 是，但必要步骤 |
| 后台 `_bg_classify_and_save` | 120s | ✓ | 否 |
| 后台 `_save_img_desc_to_db` | 120s | ✓ | 否 |

**实现要点：**
- `model_layer.py` 的 `chat()` 支持 `allow_thinking=True` kwarg，跳过 `enable_thinking: False` 注入
- `request_timeout` kwarg 直接覆盖 aiohttp 层的 `ClientTimeout`（关键：endpoint.timeout 默认 60s 会先触发，必须显式传入）
- 所有模型调用都传 `request_timeout=first_timeout`，确保超时行为与配置一致

---

### 2.4 CLOUD fallback 兼容性问题

LOCAL/视觉模型空结果或超时时降级 CLOUD，`task.loop_messages` 里有两类字段需要处理：

**① `reasoning_content`（必须剥离）**

LOCAL（qwen3.6-35B）的 thinking 产生 `reasoning_content`，传给 DeepSeek 时报错：
```
"reasoning_content in thinking mode must be passed back to the API"
```

**修复：** 构建 `_fb_msgs` 时过滤掉 `reasoning_content`：
```python
_fb_msg = {k: v for k, v in _m.items() if k != "reasoning_content"}
```

**② `image_url` 内容（视情况剥离）**

DeepSeek 当前不支持 vision 格式，传入 `image_url` 报错：
```
"unknown variant `image_url`, expected `text`"
```
**修复：** 根据 CLOUD 是否有 vision capability 决定是否剥离：
```python
_cloud_has_vision = "vision" in cloud_adapter.endpoint.capabilities
if isinstance(_c, list) and not _cloud_has_vision:
    _c = " ".join(p["text"] for p in _c if p.get("type") == "text")
```

---

### 2.5 LOCAL 超时自动降级 CLOUD

**问题：** GPU 机器（192.168.12.167）负载高时，LOCAL 聊天（原来 35B）超时，用户收到"请稍后重试"。

**解决方案：** LOCAL/PRO 超时时自动降级 CLOUD 回答，CLOUD 也失败才报错。

```python
except asyncio.TimeoutError:
    if active_adapter is not cloud_adapter and cloud_adapter is not None:
        # 重建 _fb_msgs（剥离 reasoning_content + 视情况剥离 image_url）
        # 用 CLOUD 回答
        ...
    # CLOUD 也失败或本来就是 CLOUD → 报超时
```

---

### 2.6 LOCAL 聊天与视觉模型分离（当前架构）

**问题：** qwen3.6-35B 生成速度慢（~25 token/s），GPU 忙时请求排队超时，用户体验差。

**解决方案：** 将聊天和视觉分离为两个独立 adapter：

- **`qwen-local`（BASIC/CHAT）= qwen2.5:14b**：负责 LOCAL 路由的实时聊天，Ollama 本地推理，秒级响应
- **`qwen-vision`（BASIC/VISION）= qwen3.6-35B**：专职图片描述，仅在后台或无视觉模型时调用

代码中分别获取：
```python
local_adapter  = router.get_available_adapter(ModelLayer.BASIC, ModelRole.CHAT)   # 14b
vision_adapter = router.get_available_adapter(ModelLayer.BASIC, ModelRole.VISION)  # 35B
```

所有 `_describe_images`、`_bg_classify_and_save`、`_save_img_desc_to_db` 统一使用 `vision_adapter`。

---

### 2.7 表情包 vs 真实图片的区分

**两道过滤：**

**① 协议层（`sub_type` 字段）：**
- `sub_type=1`：QQ 内置表情/贴纸，直接存 `[表情]`，不调用视觉模型
- `sub_type=0`：可能是真图，也可能是用户上传的表情包，进入第二道

**② 视觉模型判断（prompt）：**
```
判断这张图片是【表情包/贴纸/reaction图】还是【真实图片/截图/照片/文字/图表】。
- 若是表情包/贴纸：只输出 [表情:简短描述表情含义]，例如 [表情:捂脸大笑]
- 若是真实图片：简洁中文描述内容，重点关注文字、代码、图表、关键物体，不超过200字
不要加任何前缀或解释，直接输出结果。
```

---

### 2.8 历史图片回溯（先发图后问）

1. **DB 存储 attachments**：`messages` 表记录 file_id，无论 bot 是否响应
2. **后台分类（每条含图消息都触发）**：`_bg_classify_and_save` 异步描述，更新 DB
3. **历史图片只用文字描述**：`_inject_history_images` 已停用；历史图片靠 `[图片内容：...]` 提供上下文，只有**当前消息**的图片才附加 base64

---

### 2.9 描述质量：从 reasoning_content 提取实际描述

**问题：** `reasoning_content` fallback 返回原始思考文本（"这个任务需要我..."），不是干净描述。

**解决方案（`_extract_img_desc` 静态方法）：**
- 干净文本（无思考前缀）直接返回
- 在思考文本中搜索 `[表情:...]` 标记
- 搜索结论行（`最终输出:`、`结论:` 等）
- fallback：剥掉 markdown bullet/bold，提取实质行，截断 250 字

---

## 三、图片处理完整流程

```
消息到达
├── 解析 attachments
│   ├── sub_type=1 → text += "[表情]"
│   └── sub_type=0 → text += "[图片（需要视觉理解）]"，file_id 存入 attachments 列
│
├── 保存消息到 DB
│
├── 有 sub_type=0 图片 → 启动后台 _bg_classify_and_save（vision_adapter，timeout=120s）
│
└── Bot 决定响应？
    ├── active adapter 有 vision（未来扩展）
    │   ├─ 直接附 base64（_attach_images_to_last_msg）
    │   └─ 后台 _save_img_desc_to_db（vision_adapter，timeout=120s）
    └── active adapter 无 vision，vision_adapter 存在
        ├─ _describe_images(vision_adapter, timeout=120s) → 描述注入消息
        └─ 描述失败 → 切换为 vision_adapter 直接处理（附图）
            └─ vision_adapter 空结果/超时 → CLOUD fallback（剥 reasoning_content + 视情况剥 image_url）
```

---

## 四、System Prompt 说明

历史消息中可能出现 `[图片内容：...]` 或 `[表情:...]`，system prompt 中加入：

> 历史消息中可能包含图片内容（标注为 [图片内容：...]），仅作为上下文参考；用户没有主动提及时，不要主动评论历史图片。

---

## 五、已知限制

1. **DNS 不通** — 服务器无法访问 `multimedia.nt.qq.com.cn`，HTTP 下载图片的兜底路径永远失败。只能依赖本地文件缓存（`get_file` API）。
2. **新文件权限时序** — inotifywait + chmod 存在极短的时间窗口（<100ms），极端情况下 bot 可能抢先读到权限未修复的文件。概率极低，可接受。
3. **thinking fallback 描述质量** — `reasoning_content` 被当作描述时，内容是思考过程而非直接答案，`_extract_img_desc` 尽力提取但不能保证 100% 准确。GPU 负载高时仍可能在 120s 内无结果。
4. **表情包误判** — `sub_type=0` 的用户上传表情包（梗图、截图表情）依赖视觉模型判断，不能保证 100% 准确。
5. **GPU 负载** — vision_adapter（qwen3.6-35B）在 GPU 繁忙时响应慢，但因为全部在后台/阻塞描述路径运行，不影响普通文字聊天速度。
