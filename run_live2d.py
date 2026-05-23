#!/usr/bin/env python3
"""
Live2D 后端入口

QQ 验证登录流程：
  1. 前端 WS 发 {"type": "login_request", "qq": 12345678}
  2. 后端通过 NapCat 给该 QQ 发验证码
  3. 前端发 {"type": "verify_code", "qq": 12345678, "code": "XXXXXX"}
  4. 验证通过 → Pipeline 启动，session_key = "private:{qq}"

启动：
  cd XiaoMeng
  uvicorn run_live2d:app --host 0.0.0.0 --port 8765
"""
import asyncio
import contextlib
import json
import logging
import os
import random
import sys
import string
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_live2d")

# ── 配置 ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    cfg_path = Path("data/qq_config.json")
    if not cfg_path.exists():
        logger.error("找不到 data/qq_config.json，请先运行 python setup.py")
        sys.exit(1)
    return json.loads(cfg_path.read_text(encoding="utf-8"))

_cfg = _load_config()
_live2d_cfg: dict = _cfg.get("live2d", {})

# ── XiaoMeng 核心组件 ────────────────────────────────────────────────

from core.model_layer import ModelLayerRouter, ModelEndpoint, ModelLayer, ModelRole
from core.qq.napcat import NapCatClient
from core.qq.permissions import QQPermissionManager, PermLevel
from core.qq.tools import load_skills_prompt
from core.live2d_provider import XiaoMengLLMProvider

# ── llm-live2d 库 ────────────────────────────────────────────────────

from llm_live2d.core.pipeline import Pipeline, PipelineConfig
from llm_live2d.core.actions import (
    Action, TurnStartAction, TurnEndAction, StopAction,
)
from llm_live2d.core import serialize, parse_inbound, UserMessage, InterruptSignal
from llm_live2d.providers.memory_sink import InMemoryAudioSink
from llm_live2d.core.providers import TTSProvider, TTSResult

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ── 全局单例 ─────────────────────────────────────────────────────────

def _build_router() -> ModelLayerRouter:
    r = ModelLayerRouter()
    for m in _cfg.get("models", []):
        if not m.get("enabled", True):
            continue
        ep = ModelEndpoint(
            model_id=m.get("model_id", m["model_name"]),
            layer=ModelLayer(m.get("layer", "basic")),
            role=ModelRole(m.get("role", "chat")),
            endpoint=m["endpoint"],
            model_name=m["model_name"],
            api_key=m.get("api_key"),
            max_tokens=m.get("max_tokens", 4096),
            temperature=m.get("temperature", 0.85),
            enabled=True,
            priority=m.get("priority", 1),
            proxy=m.get("proxy"),
            num_ctx=m.get("num_ctx"),
        )
        r.register_model(ep)
    return r

_router = _build_router()

_data_dir = Path(_cfg.get("data_dir", "data"))
_db_path = str(_data_dir / "qq_bot.db")
_soul_path = _cfg.get("persona_path", "data/persona/SOUL.md")
_skills_dir = str(_data_dir / "skills")

_perm_mgr = QQPermissionManager(
    data_dir=str(_data_dir),
    owner_qq=_cfg["owner_qq"],
)

_sink = InMemoryAudioSink()


class _SoVITSProvider(TTSProvider):
    """GPT-SoVITS API TTS，使用参考音频克隆音色。"""
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:9882",
        ref_audio: str = "",
        ref_text: str = "",
        ref_lang: str = "zh",
        text_lang: str = "zh",
        text_split_method: str = "cut0",
        request_timeout: float = 60,
    ):
        self._api_url = api_url.rstrip("/")
        self._ref_audio = ref_audio
        self._ref_text = ref_text
        self._ref_lang = ref_lang
        self._text_lang = text_lang
        self._text_split_method = text_split_method
        self._request_timeout = request_timeout

    async def synthesize(self, text: str, **_) -> TTSResult:
        import httpx
        payload = {
            "text": text,
            "text_lang": self._text_lang,
            "ref_audio_path": self._ref_audio,
            "prompt_text": self._ref_text,
            "prompt_lang": self._ref_lang,
            "text_split_method": self._text_split_method,
            "batch_size": 1,
            "speed_factor": 1.0,
            "streaming_mode": False,
        }
        async with httpx.AsyncClient(timeout=self._request_timeout) as client:
            resp = await client.post(f"{self._api_url}/tts", json=payload)
            resp.raise_for_status()
        return TTSResult(audio_bytes=resp.content, mime="audio/wav")


class _GTTSProvider(TTSProvider):
    """Google TTS 备用（无需 API Key）。"""
    async def synthesize(self, text: str, **_) -> TTSResult:
        import io
        from gtts import gTTS
        def _synth():
            tts = gTTS(text, lang="zh-CN")
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            return buf.getvalue()
        data = await asyncio.to_thread(_synth)
        return TTSResult(audio_bytes=data, mime="audio/mpeg")


def _make_silent_wav(duration_ms: int = 200) -> bytes:
    """生成一小段静音 WAV，用于无法连接 EdgeTTS 时的兜底。"""
    import struct
    sr = 16000
    samples = sr * duration_ms // 1000
    data = b'\x00\x00' * samples
    hdr = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(data), b'WAVE',
        b'fmt ', 16, 1, 1, sr, sr * 2, 2, 16,
        b'data', len(data))
    return hdr + data

class _SilentTTS(TTSProvider):
    """网络不通时的静音兜底 TTS（字幕仍正常显示）。"""
    async def synthesize(self, text: str, **_) -> TTSResult:
        return TTSResult(audio_bytes=_make_silent_wav(), mime="audio/wav", duration_ms=200)

async def _try_build_tts() -> TTSProvider:
    """依次尝试 GPT-SoVITS → gTTS → 静音兜底。"""
    tts_cfg = _cfg.get("tts", {})
    try:
        tts = _SoVITSProvider(
            api_url=tts_cfg.get("api_url", "http://127.0.0.1:9882"),
            ref_audio=tts_cfg.get("ref_audio", ""),
            ref_text=tts_cfg.get("ref_text", ""),
            ref_lang=tts_cfg.get("ref_lang", "zh"),
            text_lang=tts_cfg.get("text_lang", "zh"),
            text_split_method=tts_cfg.get("text_split_method", "cut0"),
            request_timeout=tts_cfg.get("request_timeout", 60),
        )
        await asyncio.wait_for(tts.synthesize("你好"), timeout=30)
        logger.info("GPT-SoVITS 可用，使用本地 TTS")
        return tts
    except Exception as e:
        logger.warning(f"GPT-SoVITS 不可用（{e}），尝试 gTTS")
    # 备用：gTTS
    try:
        tts = _GTTSProvider()
        await asyncio.wait_for(tts.synthesize("测试"), timeout=10)
        logger.info("gTTS 可用，使用 Google TTS")
        return tts
    except Exception as e:
        logger.warning(f"gTTS 不可用（{e}），降级为静音模式")
        return _SilentTTS()

_tts: TTSProvider = _SilentTTS()  # lifespan 里会尝试替换成 EdgeTTS

# NapCat：仅用于发验证码，启动后台任务连接
_napcat = NapCatClient(
    ws_url=_cfg.get("napcat_ws_url", "ws://127.0.0.1:3001"),
    access_token=_cfg.get("napcat_token", ""),
    reconnect_interval=_cfg.get("napcat_reconnect_interval", 5.0),
    api_timeout=_cfg.get("napcat_api_timeout", 15.0),
    ping_interval=_cfg.get("napcat_ping_interval", 20),
    ping_timeout=_cfg.get("napcat_ping_timeout", 20),
)

def _build_system_prompt() -> str:
    try:
        soul = Path(_soul_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        soul = "你是小萌，温柔可爱的 AI 伙伴。"
    skills = load_skills_prompt(_skills_dir)
    # 表情/动作名由具体模型决定，通过配置覆盖
    emotions = _live2d_cfg.get("emotions", ["f01", "f02", "f03", "f04"])
    motions  = _live2d_cfg.get("motions",  ["tapBody", "flick_head", "pinch_in", "shake"])
    live2d_hint = (
        "\n\n【Live2D 模式 — 以下规则覆盖上面所有说话风格】\n"
        "你正在通过 Live2D 虚拟形象和主人交流，文字会被 TTS 朗读出来。\n\n"
        "★ 禁止使用颜文字（如 (｡･ω･｡) ≧▽≦ 等），改用表情标签控制 Live2D 面部动作。\n"
        f"可用表情标签：{' '.join(f'[emotion:{e}]' for e in emotions)}\n"
        f"可用动作标签：{' '.join(f'[motion:{m}]' for m in motions)}\n"
        "内心独白：<think>这里写不朗读的内容</think>\n\n"
        "示例：[emotion:f01]好久不见，主人~今天过得怎么样？\n\n"
        "其他规范：\n"
        "- 回复是自然口语，不用 Markdown\n"
        "- 保持简短（1-3 句）\n"
        "- 不复述搜索结果原文，用自己的话总结"
    )
    parts = [soul]
    if skills:
        parts.append(skills)
    parts.append(live2d_hint)
    return "\n\n".join(parts)

_system_prompt = _build_system_prompt()

# ── 验证码管理 ───────────────────────────────────────────────────────

_pending_codes: Dict[int, str] = {}  # qq → code
_CODE_TTL = 300  # 5 分钟

def _gen_code() -> str:
    return "".join(random.choices(string.digits, k=6))

async def _send_code(qq: int) -> str:
    code = _gen_code()
    _pending_codes[qq] = code
    # 5 分钟后自动清理
    async def _expire():
        await asyncio.sleep(_CODE_TTL)
        _pending_codes.pop(qq, None)
    asyncio.create_task(_expire())
    try:
        await _napcat.call_api(
            "send_private_msg",
            {"user_id": qq, "message": f"小萌 Live2D 验证码：{code}（5分钟内有效）"},
        )
        logger.info(f"验证码已发送给 QQ {qq}")
    except Exception as e:
        logger.warning(f"发送验证码失败: {e}（NapCat 可能未连接）")
    return code

# ── FastAPI 应用 ─────────────────────────────────────────────────────

@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    global _tts
    _tts = await _try_build_tts()
    task = asyncio.create_task(_napcat.start())
    logger.info("Live2D 后端已启动")
    yield
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

_FRONTEND = Path(__file__).parent.parent / ".llm-live2d" / "frontend" / "public"

app = FastAPI(lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def _health():
    return {"ok": True}

# 前端静态文件（最后挂载，避免遮住 /ws /audio 路由）

@app.get("/audio/{key}")
async def _get_audio(key: str):
    result = await _sink.get(key)
    if result is None:
        return Response(status_code=404)
    return Response(content=result.audio_bytes, media_type=result.mime)

@app.websocket("/ws")
async def _ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("新 WebSocket 连接")

    async def _send(obj: dict):
        await websocket.send_text(json.dumps(obj, ensure_ascii=False))

    # ── Phase 1：QQ 验证登录 ────────────────────────────────────────
    authenticated_qq: Optional[int] = None

    await _send({"type": "auth_required", "message": "请输入你的 QQ 号以验证身份"})

    try:
        while authenticated_qq is None:
            raw = await websocket.receive_text()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            etype = event.get("type")

            if etype == "login_request":
                try:
                    qq = int(event["qq"])
                except (KeyError, ValueError):
                    await _send({"type": "auth_fail", "reason": "无效的 QQ 号"})
                    continue
                await _send_code(qq)
                await _send({"type": "code_sent", "qq": qq})

            elif etype == "verify_code":
                try:
                    qq = int(event["qq"])
                    code = str(event["code"]).strip()
                except (KeyError, ValueError):
                    await _send({"type": "auth_fail", "reason": "格式错误"})
                    continue

                if _pending_codes.get(qq) == code:
                    _pending_codes.pop(qq, None)
                    authenticated_qq = qq
                    level = _perm_mgr.get_level(qq)
                    await _send({"type": "auth_ok", "qq": qq, "level": level.name})
                    logger.info(f"QQ {qq} 验证成功，权限: {level.name}")
                else:
                    await _send({"type": "auth_fail", "reason": "验证码错误或已过期"})

    except WebSocketDisconnect:
        logger.info("连接在验证阶段断开")
        return

    # ── Phase 2：Pipeline 对话 ──────────────────────────────────────
    level = _perm_mgr.get_level(authenticated_qq)
    provider = XiaoMengLLMProvider(
        router=_router,
        db_path=_db_path,
        soul_path=_soul_path,
        data_dir=str(_data_dir),
        sender_qq=authenticated_qq,
        level=level,
        pro_keywords=_cfg.get("pro_trigger_keywords", []),
        proxy=_cfg.get("web_search_proxy", ""),
    )
    pipeline = Pipeline(
        llm=provider,
        tts=_tts,
        sink=_sink,
        config=PipelineConfig(
            system_prompt=_system_prompt,
            history_max_turns=_live2d_cfg.get("history_max_turns", 20),
        ),
    )

    current_task: Optional[asyncio.Task] = None

    async def _run_turn(text: str):
        try:
            async for action in pipeline.handle_user_message(text):
                await websocket.send_text(serialize(action))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("turn 执行出错")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                event = parse_inbound(raw)
            except (ValueError, KeyError) as e:
                logger.warning(f"无效消息: {raw[:80]} ({e})")
                continue

            if isinstance(event, UserMessage):
                if current_task and not current_task.done():
                    await pipeline.interrupt()
                    with contextlib.suppress(BaseException):
                        await current_task
                current_task = asyncio.create_task(_run_turn(event.text))

            elif isinstance(event, InterruptSignal):
                if current_task and not current_task.done():
                    await pipeline.interrupt(event.turn_id or None)

    except WebSocketDisconnect:
        logger.info(f"QQ {authenticated_qq} 断开连接")
    finally:
        if current_task and not current_task.done():
            await pipeline.interrupt()
            with contextlib.suppress(BaseException):
                await current_task

# ── HTML 管理面板（必须先挂载，避免被根 SPA 遮住） ───────────────────
try:
    from web import register_admin_routes
    register_admin_routes(app, _napcat, _perm_mgr, _data_dir)
    logger.info("HTML 管理面板已挂载: /admin")
except Exception as e:
    logger.warning(f"挂载 HTML 管理面板失败: {e}")

# 前端静态文件（挂在最后，不遮住 API 路由）
if _FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
else:
    logger.warning(f"前端目录不存在: {_FRONTEND}")
