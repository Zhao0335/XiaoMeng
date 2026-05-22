"""
QQ Gateway
将 NapCat 事件串联到 LLM 推理、记忆管理、权限检查、命令处理、主动发言等全部组件

数据存储：SQLite（qq_bot.db），位于 data/ 目录
"""

import asyncio
import base64
import json
import logging
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiohttp import web as _aiohttp_web

from ..model_layer import (
    ModelEndpoint,
    ModelLayer,
    ModelLayerRouter,
    ModelProvider,
    ModelRole,
)
from ..plugins import PluginManager
from ..tasks import AsyncTask, TaskPool, TaskStatus
from .commands import QQCommandParser
from .napcat import NapCatClient
from .onebot_events import (
    FriendRequestEvent,
    GroupInviteEvent,
    GroupMsgEvent,
    NoticeEvent,
    PrivateMsgEvent,
    parse_event,
)
from .permissions import PermLevel, QQPermissionManager
from .proactive import ProactiveManager
from .skills import (
    ModelTier,
    SkillContext,
    UserLevel,
)
from .tools import (
    TOOL_PROGRESS_MSG,
    TOOL_SCHEMAS,
    QQToolExecutor,
    build_context_skills_prompt,
    get_tool_schemas_for_context,
    init_skill_registry,
    load_skills_prompt,
)
from .tts import SoVITSTTS

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# DB Schema
# ──────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key  TEXT    NOT NULL,
    role         TEXT    NOT NULL,
    sender_qq    INTEGER,
    sender_name  TEXT,
    content      TEXT    NOT NULL,
    attachments  TEXT    NOT NULL DEFAULT '[]',
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_key, id);

CREATE TABLE IF NOT EXISTS long_term_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key  TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    memory_type  TEXT    NOT NULL DEFAULT 'summary',
    importance   INTEGER DEFAULT 1,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ltm_session ON long_term_memory(session_key);

CREATE TABLE IF NOT EXISTS pending_friend_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_qq    INTEGER NOT NULL,
    requester_nick  TEXT,
    comment         TEXT,
    flag            TEXT    NOT NULL,
    received_at     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS pending_group_invites (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id     INTEGER NOT NULL,
    group_name   TEXT,
    inviter_qq   INTEGER,
    flag         TEXT    NOT NULL,
    sub_type     TEXT,
    received_at  TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS group_info (
    group_id     INTEGER PRIMARY KEY,
    group_name   TEXT,
    updated_at   TEXT
);
"""

# 路由模型的基础 prompt（输出 LOCAL / CLOUD / PRO）
_ROUTER_BASE_PROMPT = """\
You are a routing assistant. Read the user message and output exactly one word:
- PRO    → heavy engineering tasks: write/debug/deploy code, server management, \
script writing, architecture design, system design, complete implementations, \
detailed technical plans
- CLOUD  → needs real-time info, web search, news, current events, \
complex reasoning, math, long writing, deep analysis, \
verifying specific facts (does X exist? is X real? when did X happen?), \
questions about specific songs/albums/releases/events, \
voice message requests (发语音/语音回复/用语音说/念一下/朗读)
- LOCAL  → casual chat, greetings, simple opinions, short emotional replies, \
vague questions that don't require facts

Output only one word: LOCAL, CLOUD, or PRO"""


# ──────────────────────────────────────────────
# 主类
# ──────────────────────────────────────────────


class QQGateway:
    """
    QQ Bot 的顶层协调器。
    初始化所有组件，注册 NapCat 事件回调，开始运行。
    """

    def __init__(self, config: dict):
        self._cfg = config
        self._data_dir = Path(config.get("data_dir", "./data"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._data_dir / "qq_bot.db")
        # web search 专用代理（与 API 代理分开）
        self._proxy: str = config.get("web_search_proxy", "")

        # 基础组件
        self._napcat = NapCatClient(
            ws_url=config.get("napcat_ws_url", "ws://127.0.0.1:3001"),
            access_token=config.get("napcat_token", ""),
            reconnect_interval=config.get("napcat_reconnect_interval", 5.0),
            api_timeout=config.get("napcat_api_timeout", 15.0),
            ping_interval=config.get("napcat_ping_interval", 20),
            ping_timeout=config.get("napcat_ping_timeout", 20),
        )
        self._perm = QQPermissionManager(
            data_dir=str(self._data_dir),
            owner_qq=config["owner_qq"],
        )
        self._router = self._build_router(config)
        self._commands = QQCommandParser(
            perm=self._perm,
            napcat=self._napcat,
            db_path=self._db_path,
        )
        # TTS（语音合成）
        tts_cfg = config.get("tts", {})
        self._tts = SoVITSTTS(
            api_url=tts_cfg.get("api_url"),
            ref_audio=tts_cfg.get("ref_audio"),
            ref_text=tts_cfg.get("ref_text"),
            ref_lang=tts_cfg.get("ref_lang", "zh"),
            text_lang=tts_cfg.get("text_lang", "zh"),
            text_split_method=tts_cfg.get("text_split_method", "cut0"),
            request_timeout=tts_cfg.get("request_timeout", 60),
        )

        self._proactive = ProactiveManager(
            db_path=self._db_path,
            router=self._router,
            napcat=self._napcat,
            bot_name=config.get("bot_name", "小萌"),
            config=config,
            soul_path=config.get("persona_path", "./data/persona/SOUL.md"),
        )

        # 配置参数
        self._owner_qq: int = config["owner_qq"]
        self._bot_name: str = config.get("bot_name", "小萌")
        self._group_resp_prob: float = config.get("group_response_prob", 0.08)
        self._admin_prob_mult: int = config.get("group_response", {}).get(
            "admin_prob_multiplier", 4
        )
        self._admin_prob_cap: float = config.get("group_response", {}).get(
            "admin_prob_cap", 0.4
        )
        self._quiet_prob_factor: float = config.get("group_response", {}).get(
            "quiet_prob_factor", 0.15
        )
        self._quiet_start: int = config.get("quiet_hours", {}).get("start", 1)
        self._quiet_end: int = config.get("quiet_hours", {}).get("end", 8)
        self._typing_ms_per_char: int = config.get("typing_ms_per_char", 30)
        self._typing_max_ms: int = config.get("typing_max_ms", 4000)
        self._typing_jitter_ms: int = config.get("typing_jitter_ms", 500)
        self._compress_every: int = config.get("memory", {}).get("compress_every", 20)
        self._short_term_keep: int = config.get("memory", {}).get("short_term_keep", 10)
        self._recent_msg_limit: int = config.get("memory", {}).get(
            "recent_messages_limit", 30
        )
        self._knowledge_truncate: int = config.get("memory", {}).get(
            "knowledge_truncate_chars", 3000
        )
        self._pro_keywords: list = config.get("pro_trigger_keywords", [])
        self._cloud_trigger_min_chars: int = config.get("cloud_trigger", {}).get(
            "min_chars", 200
        )
        self._cloud_trigger_keywords: list = config.get("cloud_trigger", {}).get(
            "keywords", []
        )
        self._timeout_pro: int = config.get("llm_timeouts", {}).get("pro", 300)
        self._timeout_cloud: int = config.get("llm_timeouts", {}).get("cloud", 180)
        self._timeout_local: int = config.get("llm_timeouts", {}).get("local", 90)
        self._timeout_routing: int = config.get("llm_timeouts", {}).get("routing", 15)
        self._routing_context_limit: int = config.get("llm_timeouts", {}).get(
            "routing_context_limit", 3
        )
        self._max_tool_loops: int = config.get("loop_limits", {}).get(
            "max_tool_loops", 10
        )
        self._max_searches_before_write: int = config.get("loop_limits", {}).get(
            "max_searches_before_write", 4
        )
        self._fallback_max_tokens_pro: int = config.get(
            "loop_max_tokens_fallback", {}
        ).get("pro", 65536)
        self._fallback_max_tokens_cloud: int = config.get(
            "loop_max_tokens_fallback", {}
        ).get("cloud", 8192)
        self._fallback_max_tokens_local: int = config.get(
            "loop_max_tokens_fallback", {}
        ).get("local", 600)
        self._progress_last_sent: Dict[str, float] = {}  # session_key → timestamp
        self._bg_tasks: set = set()  # keeps strong refs so GC doesn't cancel fire-and-forget tasks

        # persona 文件路径（动态读，不缓存内容）
        self._soul_path = Path(config.get("persona_path", "./data/persona/SOUL.md"))
        self._memory_md_path = (
            Path(config.get("data_dir", "./data")) / "persona" / "MEMORY.md"
        )
        # 按人存储的记忆文件目录：data/memory/{identity}.md
        self._memory_dir = self._data_dir / "memory"
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        # identity_links.json：QQ 号 → canonical 身份名（每次消息时读取，不缓存）
        self._identity_links_path = self._data_dir / "identity_links.json"
        # routing_hints.md：可学习的路由规则，每次路由时动态读取
        self._routing_hints_path = self._data_dir / "routing_hints.md"
        # skills 目录
        self._skills_dir = str(self._data_dir / "skills")

        # 初始化 SkillRegistry（启动时加载所有技能文件）
        init_skill_registry(self._skills_dir)

        # 插件系统：扫描 data/plugins/，延迟到 start() 中异步初始化
        _plugins_dir = self._data_dir / "plugins"
        _plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugin_manager = PluginManager(_plugins_dir, auto_load=True, auto_initialize=False)

        # 公式渲染缓存目录
        from .formula import init_cache_dir as _init_formula_cache
        self._formula_cache_dir = _init_formula_cache(str(self._data_dir))

        # 异步任务池（支持并发）
        self._task_manager = TaskPool(
            db_path=self._db_path,
            send_message=self._send_task_progress,
            user_event_timeout=config.get("async_task", {}).get(
                "user_event_timeout", 600
            ),
            max_concurrent=config.get("async_task", {}).get("max_concurrent", 3),
        )

        # 初始化 DB
        self._init_db()
        # 注册事件回调
        self._napcat.on_event(self._on_event)

    async def start(self) -> None:
        """启动 gateway（持续运行直到停止）"""
        logger.info("QQGateway 启动中...")
        # 异步初始化插件（需要 event loop，不能在 __init__ 里做）
        plugin_results = await self._plugin_manager.initialize_all()
        if plugin_results:
            ok = sum(1 for v in plugin_results.values() if v)
            logger.info(f"插件系统: {ok}/{len(plugin_results)} 个插件初始化成功")
        # 将各插件目录下的 SKILL.md 注册到 SkillRegistry
        self._register_plugin_skills()
        # 启动本地 HTTP 中继（供 scheduler 等进程发消息）
        relay_port = self._cfg.get("bot_relay_port", 3003)
        await self._start_relay_server(relay_port)
        await self._napcat.start()
        # 恢复未完成的任务
        restored = self._task_manager.load_running_tasks_from_db(
            self._make_task_coro_factory()
        )
        if restored:
            logger.info(f"恢复未完成任务: {restored}")

    async def stop(self) -> None:
        self._proactive.stop_all()
        if hasattr(self, "_relay_runner"):
            await self._relay_runner.cleanup()
        await self._napcat.stop()

    def _register_plugin_skills(self) -> None:
        """将 data/plugins/<name>/SKILL.md 注册到 SkillRegistry。"""
        from .skills import SkillRegistry, SkillLoader
        registry = SkillRegistry.get_instance()
        count = 0
        for name, plugin in self._plugin_manager.initialized.items():
            skill_md = plugin.plugin_dir / "SKILL.md"
            if skill_md.exists():
                loader = SkillLoader(str(plugin.plugin_dir))
                skill_def = loader.load_single("SKILL.md")
                if skill_def:
                    registry.register(skill_def, override=True)
                    count += 1
                    logger.info(f"插件 {name} 的 SKILL.md 已注册")
        if count:
            logger.info(f"从插件目录注册了 {count} 个技能文档")

    # ── 本地 HTTP 中继（供 scheduler 等独立进程发消息）────────

    async def _start_relay_server(self, port: int) -> None:
        """启动本地 HTTP 中继，监听 127.0.0.1:<port>。

        支持的接口：
          POST /send_msg  {"message": str, "group_id": int}
                         {"message": str, "user_id": int}
        """
        async def handle_send_msg(request: _aiohttp_web.Request) -> _aiohttp_web.Response:
            try:
                body = await request.json()
            except Exception:
                return _aiohttp_web.Response(status=400, text="invalid json")
            text = body.get("message", "")
            if not text:
                return _aiohttp_web.Response(status=400, text="missing message")
            try:
                if "group_id" in body:
                    await self._napcat.send_group_msg(int(body["group_id"]), text)
                elif "user_id" in body:
                    await self._napcat.send_private_msg(int(body["user_id"]), text)
                else:
                    return _aiohttp_web.Response(status=400, text="missing group_id or user_id")
                return _aiohttp_web.Response(text="ok")
            except Exception as e:
                logger.error(f"中继发送失败: {e}")
                return _aiohttp_web.Response(status=500, text=str(e))

        async def handle_instruct(request: _aiohttp_web.Request) -> _aiohttp_web.Response:
            """触发小萌执行 AI 指令并将结果发到指定 target。"""
            try:
                body = await request.json()
            except Exception:
                return _aiohttp_web.Response(status=400, text="invalid json")
            prompt = body.get("prompt", "").strip()
            target = body.get("target", {})
            if not prompt:
                return _aiohttp_web.Response(status=400, text="missing prompt")
            group_id = int(target.get("group_id") or 0)
            user_id = int(target.get("user_id") or 0)
            if not group_id and not user_id:
                return _aiohttp_web.Response(status=400, text="missing target group_id or user_id")
            # session_key 用 scheduler: 前缀隔离，不污染群/私聊对话历史
            # 同一 task_id 的任务共享 session，便于早/晚题目相互引用
            session_key = body.get("session_key") or (
                f"scheduler:group:{group_id}" if group_id else f"scheduler:private:{user_id}"
            )
            route = (body.get("route") or "").upper() or None
            try:
                self._save_message(session_key, "user", prompt, sender_qq=0, sender_name="定时指令")
                task = await self._task_manager.create_and_run(
                    session_key=session_key,
                    sender_qq=0,
                    group_id=group_id,
                    coro_factory=self._make_task_coro_factory(
                        forced_level=PermLevel.ADMIN,
                        forced_route=route,
                    ),
                )
                logger.info(f"定时指令任务 {task.task_id} 已创建 session={session_key}")
                return _aiohttp_web.json_response({"task_id": task.task_id})
            except Exception as e:
                logger.error(f"定时指令创建失败: {e}")
                return _aiohttp_web.Response(status=500, text=str(e))

        app = _aiohttp_web.Application()
        app.router.add_post("/send_msg", handle_send_msg)
        app.router.add_post("/instruct", handle_instruct)
        runner = _aiohttp_web.AppRunner(app)
        await runner.setup()
        site = _aiohttp_web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        self._relay_runner = runner
        logger.info(f"本地消息中继已启动: http://127.0.0.1:{port}")

    # ── 任务进度消息发送（供 TaskPool 回调）──────────────────

    async def _send_task_progress(self, task: AsyncTask, text: str) -> None:
        parts = [p.strip() for p in text.split("\n\n")]
        parts = [p for p in parts if p] or [text]
        for part in parts:
            await self._typing_delay(part)
            if task.group_id:
                await self._napcat.send_group_msg(task.group_id, part)
            else:
                await self._napcat.send_private_msg(task.sender_qq, part)

    # ──────────────────────────────────────────────
    # 事件入口
    # ──────────────────────────────────────────────

    async def _on_event(self, raw: dict) -> None:
        event = parse_event(raw)
        if event is None:
            return

        if isinstance(event, PrivateMsgEvent):
            await self._handle_private(event)
        elif isinstance(event, GroupMsgEvent):
            await self._handle_group(event)
        elif isinstance(event, FriendRequestEvent):
            await self._handle_friend_request(event)
        elif isinstance(event, GroupInviteEvent):
            await self._handle_group_invite(event)
        elif isinstance(event, NoticeEvent):
            await self._handle_notice(event)

    # ──────────────────────────────────────────────
    # 私聊消息
    # ──────────────────────────────────────────────

    async def _handle_private(self, event: PrivateMsgEvent) -> None:
        qq = event.user_id
        level = self._get_effective_level(qq)
        logger.info(f"私聊消息 from {qq} ({level.name}): {event.message[:40]}")

        if level == PermLevel.BLACKLIST:
            return

        session_key = f"private:{qq}"
        text = event.message
        _all_img_atts = [a["data"] for a in event.attachments if a.get("type") == "image"]
        _emoji_atts = [a for a in _all_img_atts if a.get("sub_type", 0) == 1]
        _img_atts = [a for a in _all_img_atts if a.get("sub_type", 0) != 1]
        if _emoji_atts:
            text += "\n" + "[表情]" * len(_emoji_atts)
        if _img_atts:
            text += "\n" + "[图片（需要视觉理解）]" * len(_img_atts)
        # 下载 QQ 发来的文件，告诉 LLM 路径
        _file_atts = [a["data"] for a in event.attachments if a.get("type") == "file"]
        for _f in _file_atts:
            _saved = await self._download_qq_file(_f, group_id=0)
            if _saved:
                text += f"\n[文件已保存到 uploads/{_saved.name}，可用 read_file 读取]"
            else:
                text += f"\n[文件 {_f.get('name', '未知')} 下载失败]"

        # ── 任务管理命令 ────────────────────────────────────────────
        if text.strip().startswith("/取消任务 "):
            task_id = text.strip().split("/取消任务 ", 1)[1].strip()
            ok = await self._task_manager.cancel_task(task_id)
            if ok:
                await self._send_private_delayed(qq, f"✅ 任务 {task_id} 已取消")
            else:
                await self._send_private_delayed(
                    qq, f"❌ 未找到或无法取消任务 {task_id}"
                )
            return
        if text.strip().startswith("/任务 "):
            task_id = text.strip().split("/任务 ", 1)[1].strip()
            task = self._task_manager.get_task(task_id)
            if task:
                summary = self._task_manager.get_status_summary(task)
                await self._send_private_delayed(qq, summary)
            else:
                await self._send_private_delayed(qq, f"❌ 未找到任务 {task_id}")
            return
        if text.strip() == "/任务列表":
            active = [
                t
                for t in self._task_manager._tasks.values()
                if t.status
                in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.WAITING_USER)
            ]
            if active:
                lines = [f"📋 活跃任务（共 {len(active)} 个）："]
                for t in active:
                    lines.append(f"  • {t.task_id} [{t.status}] {t.session_key}")
            else:
                lines = ["📋 当前没有活跃任务"]
            await self._send_private_delayed(qq, "\n".join(lines))
            return

        # 管理命令
        cmd_result = await self._commands.handle(text, qq, session_key)
        if cmd_result is not None:
            if cmd_result.reply:
                await self._send_private_delayed(qq, cmd_result.reply)
            return

        # ── 异步任务检测 ────────────────────────────────────────────
        active_task = self._task_manager.get_active_task_for_session(session_key)

        if active_task and active_task.status == TaskStatus.WAITING_USER:
            ok = await self._task_manager.submit_to_task(active_task.task_id, text)
            if ok:
                await self._send_private_delayed(
                    qq, f"收到！小萌继续处理任务 {active_task.task_id} ~"
                )
            return

        # 多任务支持：允许并发，不提示
        if active_task and active_task.status in (
            TaskStatus.RUNNING,
            TaskStatus.PENDING,
        ):
            pass  # 不 return，继续创建新任务

        # ── 创建新任务 ───────────────────────────────────────────────
        nick = event.sender.nickname or str(qq)
        _att_records = [{"file": a.get("file") or a.get("file_id", ""), "sub_type": 0} for a in _img_atts]
        _user_msg_id = self._save_message(session_key, "user", text, qq, nick, attachments=_att_records)
        if _img_atts and _user_msg_id:
            self._create_bg_task(self._bg_classify_and_save(_img_atts, _user_msg_id, session_key))
        self._init_person_memory_if_needed(qq, nick)

        task = await self._task_manager.create_and_run(
            session_key=session_key,
            sender_qq=qq,
            group_id=0,
            coro_factory=self._make_task_coro_factory(image_atts=_img_atts, user_msg_id=_user_msg_id),
        )

        logger.info(f"任务 {task.task_id} 已创建 (私聊 {qq})")

    # ──────────────────────────────────────────────
    # 群消息
    # ──────────────────────────────────────────────

    async def _handle_group(self, event: GroupMsgEvent) -> None:
        qq = event.user_id
        level = self._get_effective_level(qq)

        if level == PermLevel.BLACKLIST:
            return

        group_id = event.group_id
        session_key = f"group:{group_id}"
        text = event.message
        # 图片附件：sub_type=1 为 QQ 内置表情，0 为真实图片（待视觉模型进一步分类）
        _all_img_atts = [a["data"] for a in event.attachments if a.get("type") == "image"]
        _emoji_atts = [a for a in _all_img_atts if a.get("sub_type", 0) == 1]
        _img_atts = [a for a in _all_img_atts if a.get("sub_type", 0) != 1]
        if _emoji_atts:
            text += "\n" + "[表情]" * len(_emoji_atts)
        if _img_atts:
            text += "\n" + "[图片（需要视觉理解）]" * len(_img_atts)
        # 下载 QQ 发来的文件，告诉 LLM 路径
        _file_atts = [a["data"] for a in event.attachments if a.get("type") == "file"]
        for _f in _file_atts:
            _saved = await self._download_qq_file(_f, group_id=group_id)
            if _saved:
                text += f"\n[文件已保存到 uploads/{_saved.name}，可用 read_file 读取]"
            else:
                text += f"\n[文件 {_f.get('name', '未知')} 下载失败]"
        nick = event.sender.card or event.sender.nickname or str(qq)
        logger.info(f"群消息 {group_id} from {qq} at_bot={event.at_bot}: {text[:40]}")

        # 更新群信息缓存
        self._proactive.ensure_group(group_id)
        self._cache_group_name(group_id)

        # 保存用户消息，attachments 存真实图片 file_id（无论是否回复）
        _att_records = [{"file": a.get("file") or a.get("file_id", ""), "sub_type": 0} for a in _img_atts]
        _user_msg_id = self._save_message(session_key, "user", text, qq, nick, attachments=_att_records)

        # 有真实图片时，后台立即描述/分类，更新 DB（不阻塞消息处理）
        if _img_atts and _user_msg_id:
            self._create_bg_task(self._bg_classify_and_save(_img_atts, _user_msg_id, session_key))

        # ── 任务管理命令（群聊，仅被 @ 时响应） ─────────────────────
        if event.at_bot:
            if text.strip().startswith("/取消任务 "):
                task_id = text.strip().split("/取消任务 ", 1)[1].strip()
                ok = await self._task_manager.cancel_task(task_id)
                reply = (
                    f"✅ 任务 {task_id} 已取消" if ok else f"❌ 未找到任务 {task_id}"
                )
                await self._send_group_delayed(group_id, reply)
                return
            if text.strip().startswith("/任务 "):
                task_id = text.strip().split("/任务 ", 1)[1].strip()
                task = self._task_manager.get_task(task_id)
                reply = (
                    self._task_manager.get_status_summary(task)
                    if task
                    else f"❌ 未找到任务 {task_id}"
                )
                await self._send_group_delayed(group_id, reply)
                return

        # 管理命令（仅管理员及以上）
        if level >= PermLevel.ADMIN:
            cmd_result = await self._commands.handle(text, qq, session_key)
            if cmd_result is not None:
                if cmd_result.reply:
                    await self._send_group_delayed(group_id, cmd_result.reply)
                return

        # 决定是否回复
        if not self._should_respond_group(event, level):
            return

        # ── 异步任务检测 ────────────────────────────────────────────
        active_task = self._task_manager.get_active_task_for_session(session_key)

        if active_task and active_task.status == TaskStatus.WAITING_USER:
            ok = await self._task_manager.submit_to_task(active_task.task_id, text)
            if ok:
                # 群聊回复
                self._save_message(session_key, "assistant", "收到！小萌继续处理~")
            return

        if active_task and active_task.status in (
            TaskStatus.RUNNING,
            TaskStatus.PENDING,
        ):
            # 群聊中允许并发，但给发送者私信提示
            # 不 return，继续创建新任务
            pass

        # ── 创建新任务 ───────────────────────────────────────────────
        task = await self._task_manager.create_and_run(
            session_key=session_key,
            sender_qq=qq,
            group_id=group_id,
            coro_factory=self._make_task_coro_factory(image_atts=_img_atts, user_msg_id=_user_msg_id),
        )
        logger.info(f"任务 {task.task_id} 已创建 (群 {group_id})")

    # ──────────────────────────────────────────────
    # 异步任务核心：工具调用循环（后台运行，不阻塞消息接收）
    # ──────────────────────────────────────────────

    def _make_task_coro_factory(
        self,
        image_atts: List[Dict] = None,
        user_msg_id: Optional[int] = None,
        forced_level: Optional["PermLevel"] = None,
        forced_route: Optional[str] = None,  # "LOCAL" / "CLOUD" / "PRO"
    ):
        """返回一个 coro factory，用于 TaskPool.create_and_run"""

        async def _run(task: AsyncTask):
            session_key = task.session_key
            group_id = task.group_id
            sender_qq = task.sender_qq
            is_group = bool(group_id)

            # 取最近消息（含第一条用户消息）
            rows = self._get_recent_messages(session_key, self._recent_msg_limit)
            user_text = next(
                (r["content"] for r in reversed(rows) if r.get("role") == "user"), ""
            )
            nick = next(
                (
                    r.get("sender_name") or str(r.get("sender_qq", sender_qq))
                    for r in rows
                    if r.get("role") == "user"
                ),
                str(sender_qq),
            )

            soul = self._read_soul()
            skills_section = load_skills_prompt(self._skills_dir)
            level = forced_level if forced_level is not None else self._get_effective_level(sender_qq)

            local_adapter = self._router.get_available_adapter(
                ModelLayer.BASIC, ModelRole.CHAT
            )
            if local_adapter is None:
                await self._task_manager.send_progress(task, "（模型不可用，任务失败）")
                return "模型不可用"

            # 专职视觉模型（仅用于图片描述/转述，不参与主流程路由）
            vision_adapter = self._router.get_available_adapter(
                ModelLayer.BASIC, ModelRole.VISION
            )

            cloud_adapter = self._router.get_available_adapter(
                ModelLayer.BRAIN, ModelRole.REASONING
            )
            pro_adapter = self._router.get_available_adapter(
                ModelLayer.PRO, ModelRole.REASONING
            )
            router_adapter = self._router.get_available_adapter(
                ModelLayer.BASIC, ModelRole.ROUTER
            )

            identity = self._resolve_identity(sender_qq) if sender_qq else ""
            tool_executor = QQToolExecutor(
                db_path=self._db_path,
                soul_path=self._soul_path,
                data_dir=self._data_dir,
                session_key=session_key,
                sender_qq=sender_qq,
                level=level,
                identity=identity,
                proxy=self._proxy,
                napcat=self._napcat,
                tts=self._tts,
                target_id=group_id if is_group else sender_qq,
                is_private=not is_group,
                task=task,
                plugin_manager=self._plugin_manager,
            )

            skill_ctx = SkillContext.from_gateway(
                route="LOCAL",  # 先默认 LOCAL，路由后更新
                perm_level=level,
                identity=identity,
                session_key=session_key,
                sender_qq=sender_qq,
                tool_executor=tool_executor,
            )

            try:
                # ── 路由判断 ─────────────────────────────────────────
                if forced_route:
                    route = forced_route.upper()
                    logger.info(f"任务 {task.task_id} 强制路由: {route}")
                else:
                  route = "LOCAL"
                cloud_hint = False
                if not forced_route:
                  if self._cloud_trigger_keywords and any(
                      kw in user_text for kw in self._cloud_trigger_keywords
                  ):
                      cloud_hint = True
                  if (
                      self._cloud_trigger_min_chars
                      and len(user_text) >= self._cloud_trigger_min_chars
                  ):
                      cloud_hint = True
                if not forced_route and router_adapter is not None:
                    # 当前消息已在 _save_message 后存入 DB，_get_recent_messages
                    # 拿到的最后一条就是当前消息，不需要再手动 append
                    routing_ctx = []
                    for r in self._get_recent_messages(
                        session_key, self._routing_context_limit
                    ):
                        role = "user" if r["role"] == "user" else "assistant"
                        routing_ctx.append(
                            {"role": role, "content": r["content"][:120]}
                        )

                    try:
                        routing_decision = await asyncio.wait_for(
                            router_adapter.chat(
                                routing_ctx,
                                system_prompt=self._build_router_prompt(),
                                max_tokens=20,
                            ),
                            timeout=self._timeout_routing,
                        )
                        decision_text = (routing_decision.content or "").strip()
                        decision_text = (
                            re.sub(
                                r"<think>.*?</think>",
                                "",
                                decision_text,
                                flags=re.DOTALL,
                            )
                            .strip()
                            .upper()
                        )
                    except Exception as _re:
                        logger.debug(f"路由文本解析失败，降级 LOCAL: {_re}")
                        decision_text = "LOCAL"

                    if "PRO" in decision_text and pro_adapter is not None:
                        route = "PRO"
                    elif (
                        "CLOUD" in decision_text or cloud_hint
                    ) and cloud_adapter is not None:
                        route = "CLOUD"
                    logger.info(
                        f"任务 {task.task_id} 路由: {decision_text!r} cloud_hint={cloud_hint} → {route}"
                    )

                # ── 选定 adapter ──────────────────────────────────────
                if route == "PRO" and pro_adapter is not None:
                    active_adapter = pro_adapter
                    first_timeout = self._timeout_pro
                elif route in ("PRO", "CLOUD") and cloud_adapter is not None:
                    active_adapter = cloud_adapter
                    first_timeout = self._timeout_cloud
                    if route == "PRO":
                        logger.warning("PRO adapter 不可用，降级到 CLOUD")
                        route = "CLOUD"
                else:
                    active_adapter = local_adapter
                    first_timeout = self._timeout_local

                # 有图片时的处理策略：
                # - active adapter 支持 vision → 直接附加图片（后面统一处理）
                # - active adapter 不支持 vision，但 local 支持 →
                #     先用 local 描述图片，把描述注入消息，再交给 active adapter
                _img_desc: Optional[str] = None
                _cur_atts: List[Dict] = list(image_atts) if image_atts else []
                if _cur_atts:
                    if "vision" not in active_adapter.endpoint.capabilities and vision_adapter is not None:
                        logger.info(f"任务 {task.task_id} 含图片，用 vision 描述后交给 {route}")
                        _desc = await self._describe_images(_cur_atts, vision_adapter)
                        if _desc:
                            _img_desc = _desc
                            _cur_atts = []
                        else:
                            # 描述失败，直接让 vision 模型带图回答
                            active_adapter = vision_adapter
                            first_timeout = self._timeout_local
                            route = "LOCAL"

                loop_max_tokens = active_adapter.endpoint.max_tokens

                is_local = active_adapter is local_adapter

                # 更新 SkillContext 的模型层级
                skill_ctx.model_tier = ModelTier.from_route(route)
                user_lv = (
                    UserLevel.OWNER
                    if level == PermLevel.OWNER
                    else (
                        UserLevel.ADMIN
                        if level == PermLevel.ADMIN
                        else UserLevel.STRANGER
                    )
                )
                skill_ctx.user_level = user_lv

                # 使用 SkillRegistry 构建上下文感知的技能 prompt
                skills_section = build_context_skills_prompt(
                    self._skills_dir,
                    skill_ctx.model_tier,
                    skill_ctx.user_level,
                    identity,
                )

                system = self._build_system_prompt(
                    session_key,
                    nick,
                    level,
                    is_group,
                    group_id,
                    soul,
                    skills_section,
                    sender_qq=sender_qq,
                    local=is_local,
                )
                # 基础工具：LOCAL 只给轻量工具，CLOUD/PRO 给全部
                # skill 工具由 SkillRegistry 按模型层级自动过滤（LOCAL → 空）
                LOCAL_OK_TOOLS = {"search_memory", "recall_conversations"}
                base_tools = (
                    [
                        t
                        for t in TOOL_SCHEMAS
                        if t.get("function", {}).get("name") in LOCAL_OK_TOOLS
                    ]
                    if is_local
                    else TOOL_SCHEMAS
                )
                active_tools = (
                    get_tool_schemas_for_context(
                        base_tools,
                        skill_ctx.model_tier,
                        skill_ctx.user_level,
                        identity,
                        plugin_manager=self._plugin_manager,
                    )
                    if "tool_call" in active_adapter.endpoint.capabilities
                    else []
                )

                messages = self._build_messages(session_key)
                # 清掉 _build_messages 加的临时字段（历史图片用 DB 里的文字描述即可，不重复 fetch 原图）
                for _m in messages:
                    _m.pop("_attachments", None)
                    _m.pop("_msg_id", None)
                task.loop_messages = list(messages)

                # 图片描述模式：把 local 生成的描述注入最后一条 user 消息，并回写 DB
                if _img_desc:
                    _img_repl = _img_desc if _img_desc.startswith("[表情") else f"[图片内容：{_img_desc}]"
                    for _m in reversed(task.loop_messages):
                        if _m["role"] == "user" and isinstance(_m.get("content"), str):
                            _m["content"] = _m["content"].replace("[图片（需要视觉理解）]", _img_repl)
                            break
                    if user_msg_id:
                        rows = self._get_recent_messages(session_key, 1)
                        if rows:
                            old = rows[-1]["content"]
                            self._update_message_content(user_msg_id, old.replace("[图片（需要视觉理解）]", _img_repl))

                if _cur_atts and "vision" in active_adapter.endpoint.capabilities:
                    # Vision 路径：附加图片同时异步生成描述存 DB（用 vision_adapter，不阻塞主流程）
                    await self._attach_images_to_last_msg(task.loop_messages, _cur_atts)
                    if user_msg_id and vision_adapter is not None:
                        async def _save_img_desc_to_db(atts, msg_id, skey):
                            _d = await self._describe_images(atts, vision_adapter, timeout=120)
                            if _d:
                                _r = _d if _d.startswith("[表情") else f"[图片内容：{_d}]"
                                rows = self._get_recent_messages(skey, 1)
                                if rows:
                                    old = rows[-1]["content"]
                                    self._update_message_content(msg_id, old.replace("[图片（需要视觉理解）]", _r))
                        self._create_bg_task(_save_img_desc_to_db(_cur_atts, user_msg_id, session_key))

                if task.is_cancelled():
                    return "任务已取消"

                try:
                    response = await active_adapter.chat(
                        task.loop_messages,
                        system_prompt=system,
                        tools=active_tools,
                        max_tokens=loop_max_tokens,
                        request_timeout=first_timeout,
                    )
                except asyncio.TimeoutError:
                    # LOCAL 超时时尝试降级 CLOUD，而不是直接报错
                    if active_adapter is not cloud_adapter and cloud_adapter is not None:
                        logger.warning(f"任务 {task.task_id} {route} 超时，降级 CLOUD")
                        try:
                            _cloud_has_vision = "vision" in cloud_adapter.endpoint.capabilities
                            _fb_msgs = []
                            for _m in task.loop_messages:
                                _c = _m.get("content", "")
                                if isinstance(_c, list) and not _cloud_has_vision:
                                    _c = " ".join(p["text"] for p in _c if p.get("type") == "text")
                                _fb_msg = {k: v for k, v in _m.items() if k != "reasoning_content"}
                                _fb_msg["content"] = _c
                                _fb_msgs.append(_fb_msg)
                            _cloud_system = self._build_system_prompt(
                                session_key, nick, level, is_group, group_id, soul,
                                skills_section, sender_qq=sender_qq, local=False,
                            )
                            _fb = await cloud_adapter.chat(
                                _fb_msgs,
                                system_prompt=_cloud_system,
                                max_tokens=self._fallback_max_tokens_cloud,
                                request_timeout=self._timeout_cloud,
                            )
                            _fb_text = self._clean_reply(_fb.content or "")
                            if _fb_text.strip():
                                task.loop_messages.append({"role": "assistant", "content": _fb_text})
                                await self._task_manager.send_progress(task, _fb_text)
                                return _fb_text
                        except Exception as _fe:
                            logger.warning(f"任务 {task.task_id} CLOUD 降级失败: {_fe}")
                    timeout_msg = (
                        f"模型响应超时（{first_timeout}秒），请稍后重试或简化问题~"
                    )
                    await self._task_manager.send_progress(task, timeout_msg)
                    return timeout_msg

                # ── 工具调用循环 ───────────────────────────────────────
                search_count = 0
                wrote_something = False
                WRITE_TOOLS = {"write_file", "add_memory", "update_soul"}

                for _ in range(self._max_tool_loops):
                    if task.is_cancelled():
                        return "任务已取消"

                    tool_calls = response.tool_calls
                    if not tool_calls:
                        break

                    asst_msg: Dict = {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {
                                "id": tc.get("id", f"call_{i}"),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(
                                        tc.get("arguments", {}), ensure_ascii=False
                                    ),
                                },
                            }
                            for i, tc in enumerate(tool_calls)
                        ],
                    }
                    if response.reasoning_content:
                        asst_msg["reasoning_content"] = response.reasoning_content
                    task.loop_messages.append(asst_msg)

                    for tc in tool_calls:
                        if task.is_cancelled():
                            return "任务已取消"
                        name = tc.get("name", "")
                        args = tc.get("arguments", {})

                        if name == "web_search":
                            search_count += 1
                        elif name in WRITE_TOOLS:
                            wrote_something = True

                        result = await tool_executor.execute(name, args)
                        logger.info(f"任务 {task.task_id} 工具 {name}: {result[:60]}")

                        task.loop_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": result,
                            }
                        )

                    if (
                        search_count >= self._max_searches_before_write
                        and not wrote_something
                    ):
                        task.loop_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "【系统】你已经搜索了足够多的资料，不要再继续搜索了。"
                                    "现在必须立刻调用 write_file 或 add_memory 保存。"
                                ),
                            }
                        )

                    try:
                        response = await active_adapter.chat(
                            task.loop_messages,
                            system_prompt=system,
                            tools=active_tools,
                            max_tokens=loop_max_tokens,
                            request_timeout=first_timeout,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"任务 {task.task_id} 工具循环超时")
                        break

                # 若循环跑满退出时模型仍在调工具，response.content 是中间规划文字
                # 补一次无工具的请求，让模型给出真正的最终回答
                if response.tool_calls:
                    task.loop_messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {"id": tc.get("id", f"call_{i}"), "type": "function",
                             "function": {"name": tc.get("name", ""),
                                          "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False)}}
                            for i, tc in enumerate(response.tool_calls)
                        ],
                    })
                    task.loop_messages.append({
                        "role": "user",
                        "content": "【系统】工具调用次数已达上限，请根据已获取的信息直接给出最终回答，不要再调用任何工具。",
                    })
                    try:
                        response = await active_adapter.chat(
                            task.loop_messages,
                            system_prompt=system,
                            max_tokens=loop_max_tokens,
                            request_timeout=first_timeout,
                        )
                    except asyncio.TimeoutError:
                        pass

                final_text = self._clean_reply(response.content or "")

                if not final_text.strip():
                    logger.warning(
                        f"任务 {task.task_id} {route} 空结果 "
                        f"(raw={response.content!r:.80}), 降级 CLOUD"
                    )
                    if cloud_adapter is not None and active_adapter is not cloud_adapter:
                        try:
                            _cloud_has_vision = "vision" in cloud_adapter.endpoint.capabilities
                            _fb_msgs = []
                            for _m in task.loop_messages:
                                _c = _m.get("content", "")
                                if isinstance(_c, list) and not _cloud_has_vision:
                                    _c = " ".join(p["text"] for p in _c if p.get("type") == "text")
                                _fb_msg = {k: v for k, v in _m.items() if k != "reasoning_content"}
                                _fb_msg["content"] = _c
                                _fb_msgs.append(_fb_msg)
                            _fb = await cloud_adapter.chat(
                                _fb_msgs,
                                system_prompt=system,
                                max_tokens=self._fallback_max_tokens_cloud,
                                request_timeout=self._timeout_cloud,
                            )
                            final_text = self._clean_reply(_fb.content or "")
                        except Exception as _fe:
                            logger.warning(f"任务 {task.task_id} CLOUD 降级失败: {_fe}")
                    if not final_text.strip():
                        return ""

                task.loop_messages.append(
                    {
                        "role": "assistant",
                        "content": final_text,
                    }
                )

                # ── LaTeX 公式处理 ────────────────────────────────────
                # 若回复含 $$...$$ 公式，先发带占位符的文字，再逐个发图
                from .formula import extract_formulas, strip_formula_markers, send_formulas_from_text
                _formulas = extract_formulas(final_text) if "$$" in final_text else []
                _display_text = strip_formula_markers(final_text) if _formulas else final_text

                try:
                    await self._task_manager.send_progress(task, _display_text)
                except Exception as send_err:
                    logger.error(f"任务 {task.task_id} 发送结果失败: {send_err}")

                if _formulas:
                    _target_id = group_id if is_group else sender_qq
                    try:
                        await send_formulas_from_text(
                            final_text, self._napcat, is_group, _target_id,
                            self._formula_cache_dir,
                        )
                    except Exception as _fe:
                        logger.error(f"任务 {task.task_id} 公式发送失败: {_fe}")

                self._save_message(session_key, "assistant", final_text)
                self._maybe_compress(session_key)

                return final_text

            except asyncio.TimeoutError:
                timeout_msg = f"任务执行超时，请稍后重试~"
                logger.error(f"任务 {task.task_id} 超时")
                try:
                    await self._task_manager.send_progress(task, timeout_msg)
                except Exception:
                    pass
                return timeout_msg
            except Exception as e:
                logger.error(f"任务 {task.task_id} LLM 调用失败: {e}", exc_info=True)
                error_msg = f"任务执行失败: {e}"
                try:
                    await self._task_manager.send_progress(task, error_msg)
                except Exception:
                    pass
                return error_msg

        return _run

    # ──────────────────────────────────────────────
    # 好友申请
    # ──────────────────────────────────────────────

    async def _handle_friend_request(self, event: FriendRequestEvent) -> None:
        qq = event.user_id
        level = self._get_effective_level(qq)

        if level == PermLevel.BLACKLIST:
            return

        info = await self._napcat.get_stranger_info(qq)
        nick = info.get("nickname") or str(qq)

        # 保存到 DB
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """INSERT OR REPLACE INTO pending_friend_requests
               (requester_qq, requester_nick, comment, flag, received_at, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (qq, nick, event.comment, event.flag, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        # 通知主人
        notice = (
            f"有人想加我为好友！\n"
            f"QQ：{qq}\n"
            f"昵称：{nick}\n"
            f"留言：{event.comment or '（无）'}\n\n"
            f"回复以下命令来处理：\n"
            f"/同意好友 {qq}\n"
            f"/拒绝好友 {qq}"
        )
        try:
            await self._napcat.send_private_msg(self._owner_qq, notice)
        except Exception as e:
            logger.warning(f"通知主人失败: {e}")

    # ──────────────────────────────────────────────
    # 群邀请
    # ──────────────────────────────────────────────

    async def _handle_group_invite(self, event: GroupInviteEvent) -> None:
        inviter_level = self._get_effective_level(event.user_id)

        if event.sub_type == "invite":
            if inviter_level >= PermLevel.ADMIN:
                # 管理员/主人邀请，自动接受
                try:
                    await self._napcat.set_group_add_request(event.flag, "invite", True)
                    logger.info(
                        f"自动接受群邀请: 群 {event.group_id}，邀请人 {event.user_id}"
                    )
                except Exception as e:
                    logger.warning(f"接受群邀请失败: {e}")
            else:
                # 陌生人邀请，通知主人
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    """INSERT OR REPLACE INTO pending_group_invites
                       (group_id, inviter_qq, flag, sub_type, received_at, status)
                       VALUES (?, ?, ?, ?, ?, 'pending')""",
                    (
                        event.group_id,
                        event.user_id,
                        event.flag,
                        event.sub_type,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                conn.close()

                notice = (
                    f"有人邀请我进群！\n"
                    f"群号：{event.group_id}\n"
                    f"邀请人：{event.user_id}\n\n"
                    f"回复以下命令来处理：\n"
                    f"/同意入群 {event.group_id}\n"
                    f"/拒绝入群 {event.group_id}"
                )
                try:
                    await self._napcat.send_private_msg(self._owner_qq, notice)
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # 通知事件
    # ──────────────────────────────────────────────

    async def _handle_notice(self, event: NoticeEvent) -> None:
        if event.notice_type == "group_decrease":
            if event.raw.get("sub_type") == "kick_me":
                group_id = event.raw.get("group_id")
                if group_id:
                    self._proactive._agents.pop(group_id, None)
                    logger.info(f"被踢出群 {group_id}，停止主动发言")

    # ──────────────────────────────────────────────
    @staticmethod
    def _clean_reply(text: str) -> str:
        """清理不应发送给用户的内容（残留工具调用标签等）。"""
        # 移除任何残留的 DSML 工具调用块
        P = "｜｜DSML｜｜"
        tc_open = f"<{P}tool_calls>"
        tc_close = f"</{P}tool_calls>"
        while tc_open in text:
            s = text.find(tc_open)
            e = text.find(tc_close, s)
            if e == -1:
                text = text[:s]
                break
            text = text[:s] + text[e + len(tc_close) :]
        # 移除 <think>...</think> 推理块；若正文剩余为空（Qwen3 thinking 模型），
        # 则把思考内容本身作为回复，避免发出空消息
        _think_re = re.compile(r"<think>(.*?)</think>", re.DOTALL)
        think_contents = _think_re.findall(text)
        cleaned = _think_re.sub("", text).strip()
        if not cleaned and think_contents:
            cleaned = think_contents[-1].strip()
        return cleaned

    async def _describe_images(
        self, image_atts: List[Dict], vision_adapter, timeout: float = 120
    ) -> Optional[str]:
        """用 vision adapter 把图片描述成文字，供非 vision 模型使用。"""
        content = [
            {"type": "text", "text": (
                "判断这张图片是【表情包/贴纸/reaction图】还是【真实图片/截图/照片/文字/图表】。\n"
                "- 若是表情包/贴纸：只输出 [表情:简短描述表情含义]，例如 [表情:捂脸大笑]\n"
                "- 若是真实图片：简洁中文描述内容，重点关注文字、代码、图表、关键物体，不超过200字\n"
                "不要加任何前缀或解释，直接输出结果。"
            )}
        ]
        b64_list = await asyncio.gather(*[self._att_to_b64(att) for att in image_atts])
        for b64 in b64_list:
            if b64:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        if len(content) == 1:
            return None

        try:
            resp = await vision_adapter.chat(
                [{"role": "user", "content": content}],
                system_prompt="你是图片描述助手，只输出描述文字，不加任何前缀。",
                max_tokens=3000,
                allow_thinking=True,  # 描述/转述允许思考，reasoning_content fallback 兜底
                request_timeout=timeout,
            )
            desc = self._clean_reply(resp.content or "").strip()
            desc = self._extract_img_desc(desc)
            logger.info(f"图片描述完成: raw={resp.content!r:.120} → {desc[:60]!r}")
            return desc or None
        except Exception as e:
            logger.warning(f"图片描述失败: {e}")
            return None

    @staticmethod
    def _extract_img_desc(text: str) -> str:
        """从 reasoning_content fallback 的原始思考文本里提取实际图片描述。
        若 content 字段正常（模型直接输出），文本已是干净描述，直接返回。
        若是思考过程（以元描述开头），则提取实质内容。
        """
        if not text:
            return text

        # 已经是期望格式（表情包 or 纯描述文字，无思考前缀）
        if text.startswith("[表情"):
            return text
        META_PREFIXES = (
            "这个任务", "我需要", "让我", "首先", "接下来", "然后来",
            "好的", "好，", "嗯，", "根据", "现在我", "我来",
        )
        if not any(text.startswith(p) for p in META_PREFIXES) and "**" not in text[:40]:
            return text

        # 思考文本里找 [表情:...] 标记
        m = re.search(r'\[表情[：:][^\]]*\]', text)
        if m:
            return m.group()

        # 找结论行：模型通常在末尾写"输出：xxx"/"结论：xxx"/"因此输出：xxx"
        conclusion = re.search(
            r'(?:最终输出|最终答案|输出结果|结论|因此输出|所以输出)[：:]\s*(.+?)(?:\n|$)',
            text,
        )
        if conclusion:
            result = conclusion.group(1).strip()
            if 8 < len(result) < 300:
                return result

        # 剥掉 markdown，提取 bullet 点里的实质内容
        cleaned_lines = []
        for line in text.split('\n'):
            line = re.sub(r'^\s*[\*\-]\s*', '', line)        # bullet marker
            line = re.sub(r'\*\*[^*]*\*\*[：:：]?\s*', '', line)  # **bold**：
            line = re.sub(r'^\s*\d+\.\s*', '', line)          # 1. 编号
            line = line.strip()
            if not line or len(line) < 8:
                continue
            if any(line.startswith(p) for p in META_PREFIXES + ("分析", "判断", "综上", "总结")):
                continue
            cleaned_lines.append(line)

        if cleaned_lines:
            result = '。'.join(cleaned_lines[:4])
            return result[:250] if len(result) > 250 else result

        return ""

    async def _bg_classify_and_save(self, atts: List[Dict], msg_id: int, session_key: str) -> None:
        """后台：用视觉模型描述/分类图片，并把结果更新到 DB。"""
        vision_adapter = self._router.get_available_adapter(ModelLayer.BASIC, ModelRole.VISION)
        if vision_adapter is None:
            return
        _d = await self._describe_images(atts, vision_adapter, timeout=120)
        if not _d:
            return
        rows = self._get_recent_messages(session_key, 3)
        row = next((r for r in reversed(rows) if r.get("id") == msg_id), None)
        if row:
            # 模型输出 [表情:xxx] 时直接用，否则包成 [图片内容：xxx]
            replacement = _d if _d.startswith("[表情") else f"[图片内容：{_d}]"
            new_c = row["content"].replace("[图片（需要视觉理解）]", replacement, 1)
            self._update_message_content(msg_id, new_c)

    async def _att_to_b64(self, att: Dict) -> Optional[str]:
        """
        把一个 OneBot 图片 attachment data dict 转为 base64 字节串。
        优先用 NapCat get_image API 取本地缓存文件，失败才尝试 HTTP URL。
        """
        import aiohttp

        # 1. NapCat get_image → 本地文件路径
        file_id = att.get("file") or att.get("file_id") or att.get("file_unique")
        if file_id:
            try:
                result = await self._napcat.call_api("get_file", {"file": file_id}, timeout=8)
                local_path = (
                    (result.get("data") or {}).get("file")
                    or result.get("file")
                )
                if local_path:
                    p = Path(local_path)
                    # NapCat reports Docker-internal path; remap to host path unconditionally
                    if str(p).startswith("/root/.config/QQ/"):
                        p = Path("/home/qwq/napcat_xiaomeng/qq_volume") / str(p)[len("/root/.config/QQ/"):]
                    if p.exists():
                        b64 = base64.b64encode(p.read_bytes()).decode()
                        logger.info(f"get_file 本地读取 ({len(b64)//1024}KB): {p.name}")
                        return b64
                    logger.warning(f"get_file 路径不存在: {p}")
                else:
                    logger.warning(f"get_file 路径为空: result={result!r:.200}")
            except Exception as e:
                logger.warning(f"get_file 失败 ({str(file_id)[:40]}): {e}")

        # 2. 直接本地路径（file 字段本身就是路径）
        if file_id and (file_id.startswith("/") or (len(file_id) > 2 and file_id[1] == ":")):
            try:
                p = Path(file_id)
                if p.exists():
                    return base64.b64encode(p.read_bytes()).decode()
            except Exception:
                pass

        # 3. HTTP URL（最后兜底，QQ CDN 在当前服务器可能无法访问）
        url = att.get("url")
        if url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            b64 = base64.b64encode(data).decode()
                            logger.debug(f"HTTP 下载图片 ({len(b64)//1024}KB): {url[:60]}")
                            return b64
                        logger.warning(f"图片 HTTP {resp.status}: {url[:60]}")
            except Exception as e:
                logger.warning(f"图片 HTTP 下载失败: {e}")

        return None

    async def _download_qq_file(self, att_data: Dict, group_id: int = 0) -> Optional[Path]:
        """下载 QQ 发来的非图片文件到 data/uploads/，返回本地绝对路径（失败返回 None）。"""
        import shutil
        import aiohttp as _aiohttp

        file_id = att_data.get("file_id") or att_data.get("file") or ""
        file_name = att_data.get("name") or att_data.get("file_name") or att_data.get("file") or "unknown_file"
        file_name = Path(file_name).name or "unknown_file"

        uploads_dir = self._data_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        dest = uploads_dir / file_name

        async def _http_download(url: str) -> bool:
            try:
                async with _aiohttp.ClientSession() as sess:
                    async with sess.get(url, timeout=_aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status == 200:
                            dest.write_bytes(await resp.read())
                            logger.info(f"QQ 文件已保存(HTTP): {dest.name} ({dest.stat().st_size // 1024}KB)")
                            return True
                        logger.warning(f"HTTP 下载失败 {resp.status}: {url[:80]}")
            except Exception as e:
                logger.warning(f"HTTP 下载异常: {e}")
            return False

        try:
            # 步骤1：群文件用 get_group_file_url 拿下载链接
            if group_id and file_id:
                try:
                    r = await self._napcat.call_api(
                        "get_group_file_url",
                        {"group_id": group_id, "file_id": file_id},
                        timeout=10,
                    )
                    url = (r.get("data") or {}).get("url") or r.get("url", "")
                    if url and await _http_download(url):
                        return dest
                except Exception as e:
                    logger.debug(f"get_group_file_url 失败: {e}")

            # 步骤2：get_file（enableLocalFile2Url=true 时直接返回 base64）
            result = await self._napcat.call_api("get_file", {"file": file_id}, timeout=30)
            data = result.get("data") or {}
            b64_content = data.get("base64") or result.get("base64", "")
            local_path = data.get("file") or result.get("file", "")
            url = data.get("url") or result.get("url", "") or att_data.get("url", "")

            if b64_content:
                import base64 as _b64
                dest.write_bytes(_b64.b64decode(b64_content))
                logger.info(f"QQ 文件已保存(base64): {dest.name} ({dest.stat().st_size // 1024}KB)")
                return dest

            if url and await _http_download(url):
                return dest

            if local_path:
                p = Path(local_path)
                if str(p).startswith("/root/.config/QQ/"):
                    p = Path("/home/qwq/napcat_xiaomeng/qq_volume") / str(p)[len("/root/.config/QQ/"):]
                    if p.exists():
                        shutil.copy2(p, dest)
                        logger.info(f"QQ 文件已保存(挂载卷): {dest.name}")
                        return dest
                # 尝试 docker cp
                proc = await asyncio.create_subprocess_exec(
                    "docker", "cp", f"xiaomeng-napcat:{local_path}", str(dest),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode == 0 and dest.exists():
                    logger.info(f"QQ 文件已保存(docker cp): {dest.name}")
                    return dest
                logger.debug(f"docker cp 失败: {stderr.decode()[:100]}")

            logger.warning(f"所有下载方式均失败，file_id={file_id}, result={result!r:.200}")
        except Exception as e:
            logger.warning(f"QQ 文件下载失败 ({file_name}): {e}")
        return None

    async def _attach_images_to_last_msg(
        self, messages: List[Dict], image_atts: List[Dict]
    ) -> None:
        """把 image_atts 转为 base64 后附加到 messages 中最后一条 user 消息，转为 vision 格式。"""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] != "user":
                continue
            text = messages[i]["content"]
            if not isinstance(text, str):
                break
            text = re.sub(r"(\[图片（需要视觉理解）\])+", "", text).rstrip()
            content: List[Dict] = [{"type": "text", "text": text}]
            b64_list = await asyncio.gather(*[self._att_to_b64(att) for att in image_atts])
            for att, b64 in zip(image_atts, b64_list):
                if b64 is None:
                    logger.warning(f"跳过无法获取的图片: {att.get('file', '')[:60]}")
                    continue
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
            if len(content) > 1:
                messages[i]["content"] = content
                logger.info(f"vision 消息：{len(content)-1} 张图片已附加")
            break

    def _read_soul(self) -> str:
        """每次调用都从文件读取，改了立即生效。"""
        try:
            soul = self._soul_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            soul = "你是小萌，温柔可爱的 AI 伙伴。"
        # 附加 MEMORY.md（如果存在）
        if self._memory_md_path.exists():
            mem = self._memory_md_path.read_text(encoding="utf-8").strip()
            if mem:
                soul += f"\n\n---\n\n# 小萌的记忆\n\n{mem}"
        return soul

    def _build_system_prompt(
        self,
        session_key: str,
        nick: str,
        level: PermLevel,
        is_group: bool,
        group_id: int = 0,
        soul: str = "",
        skills_section: str = "",
        sender_qq: int = 0,
        local: bool = False,  # True = 精简版，给本地小模型用
    ) -> str:
        level_desc = {
            PermLevel.OWNER: "这是你的主人，全权信任，尽力满足他/她的请求",
            PermLevel.ADMIN: "这是管理员，可以信任",
            PermLevel.STRANGER: "这是陌生人，保持礼貌友好",
        }.get(level, "陌生人")

        # 人级别记忆：identity 文件 + 跨账号私聊摘要（不含当前 session，避免重复）
        user_ltm = ""
        if sender_qq:
            identity = self._resolve_identity(sender_qq)
            user_ltm = self._load_person_memory(
                identity, sender_qq, exclude_session=session_key
            )

        # 会话级摘要：当前群/私聊的压缩历史
        session_ltm = self._get_long_term_memory(session_key)

        # 通用知识库：data/memory/knowledge.md
        knowledge_ltm = self._load_knowledge()

        memory_section = ""
        if knowledge_ltm:
            memory_section += f"\n\n## 小萌学到的知识：\n{knowledge_ltm}"
        if user_ltm:
            memory_section += (
                f"\n\n## 你对「{nick}」的了解（跨对话记住的）：\n{user_ltm}"
            )
        if session_ltm:
            label = "这个群" if is_group else "你们之前的对话"
            memory_section += f"\n\n## 关于{label}的摘要：\n{session_ltm}"

        scene = "QQ群聊" if is_group else "QQ私聊"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        skills_block = f"\n\n{skills_section}" if skills_section else ""

        # 身份说明（不同等级给不同的直接指令）
        if level == PermLevel.OWNER:
            identity_note = (
                f"**对方是你的主人**（QQ {sender_qq}，昵称「{nick}」）。"
                "这是系统通过 QQ 号码技术验证的，不是对方自己说的——你已经确认了，无需再要求对方证明身份。"
                "主人说什么你都可以信任，全力配合。"
            )
        elif level == PermLevel.ADMIN:
            identity_note = f"对方是管理员（QQ {sender_qq}，昵称「{nick}」），系统已验证，可以信任。"
        elif level == PermLevel.BLACKLIST:
            identity_note = f"对方（QQ {sender_qq}）在黑名单中，不要理会。"
        else:
            identity_note = (
                f"对方是陌生人（QQ {sender_qq}，昵称「{nick}」），保持礼貌但有距离。"
            )

        if local:
            return f"""{soul}

---

## 当前对话

- 场景：{scene}
- 当前时间：{now}
- {identity_note}
{memory_section}

保持你的性格自然回复，1~3 句话。"""

        return f"""{soul}

---

## 当前对话

- 场景：{scene}
- 当前时间：{now}
- {identity_note}
{memory_section}{skills_block}

## 你的 workspace（data/ 目录）

你对以下文件有完整的读写权限：
- `persona/SOUL.md` — 你的灵魂/人设（用 update_soul 工具专门处理）
- `persona/MEMORY.md` — 对话流水账
- `memory/` — 每个人的记忆文件（如 memory/owner.md、memory/user_123.md）
- `identity_links.json` — 身份映射（把同一个人的多个 QQ 号关联起来）
- `routing_hints.md` — 路由学习文件，记录什么样的问题应该用云端/本地模型
- `skills/` — 可用的技能文件

主人或管理员叫你修改文件时：先用 read_file 读当前内容，理解后用 write_file 修改。
改 identity_links.json 后立即生效。
如果你发现自己用本地模型答错了某类问题（或主人指出应该用云端），用 write_file 在 routing_hints.md 末尾追加一条学习记录，格式：`- [日期] <描述> → CLOUD`。

## 工具使用（重要：不确定时先查工具，不要凭空回答）

- 查不到的事实、最新信息 → web_search
- 对方说了名字/职业/喜好/重要信息 → **立即** add_memory(scope="person")，跨群聊私聊都有效
- 想回忆之前聊过的事 → search_memory
- 读 workspace 里的文件 → read_file
- 修改文件（需管理员权限）→ write_file；删除文件 → delete_file
- 想装新 skill：用 web_search 找内容，write_file 写到 skills/ 目录下（.md 文件），技能立即生效
- 执行服务器命令（**仅主人**）→ run_command，可以管服务、看日志、装包、重启程序等
- 这次对话让你有了新感受 → update_soul（真实的一两句话）
- **对方要求语音回复 / 发语音 / 用语音说 / 朗读 → 必须调用 send_voice**，不能只用文字回复

**以下情况必须先用工具查，禁止直接用文字敷衍：**
- 有人让你「研究/深入了解/查一下/介绍」某个话题 → **必须先 web_search**，搜完再回答，不能只说"我去研究一下"而不搜
- 问某首歌/某个乐队/某个人物是否真实存在、有什么成员、发了什么作品 → **必须 web_search**
- 有人问「你还记得我们私信聊什么吗」「之前说过什么」→ 立即用 recall_conversations 搜索，搜到了再回答
- 有人问「最近群里/私信里有没有提到xxx」→ 用 recall_conversations(query="xxx") 搜
- 主人/管理员问「你最近和谁聊了」→ recall_conversations 查近期记录

**搜到信息之后必须保存：**
- web_search 搜到了有价值的事实（乐队成员、作品列表、事件、人物介绍等）→ **必须紧接着 add_memory(scope="knowledge", content="...")** 把关键信息存下来，这样下次不用再搜
- 对方分享了关于自己的信息（名字、喜好、职业、经历）→ **必须 add_memory(scope="person")** 立即存，不能只在脑子里记着

你有能力查历史对话和上网搜索，不要说"我看不到"或只承诺"我去查"而不实际查。

**重要：不要用文字承诺你要做什么，直接调工具做。**
- 错误示范：回复"好的，我马上把这些整理到文件" → 然后什么都没调
- 正确示范：直接在这条回复里调用 write_file 或 add_memory，写完再回话
- 如果你搜完了资料还没有保存，**必须继续调工具保存**，不能只说"保存好了"

## 回复要求

- 保持你的性格，自然真实
- 日常聊天控制在 1~3 句话以内，不要啰嗦
- 不要重复对方说过的话
- 如果对方在群里 @ 你，正常回复
- 历史消息中可能包含图片内容（标注为 [图片内容：...]），仅作为上下文参考；用户没有主动提及时，不要主动评论历史图片
"""

    def _build_messages(self, session_key: str) -> List[Dict]:
        rows = self._get_recent_messages(session_key, self._recent_msg_limit)
        msgs = []
        for r in rows:
            role = r["role"]
            content = r["content"]
            if role == "user":
                sender_name = r.get("sender_name") or "对方"
                msgs.append({
                    "role": "user",
                    "content": f"{sender_name}: {content}",
                    "_attachments": json.loads(r.get("attachments") or "[]"),
                    "_msg_id": r.get("id"),
                })
            else:
                msgs.append({"role": "assistant", "content": content})
        return msgs

    async def _inject_history_images(self, msgs: List[Dict], vision_adapter) -> List[Dict]:
        """为 vision 模型把最近 N 条有图的历史消息转成 vision 格式，其余消息保持文本。"""
        _MAX_HIST_IMGS = 3  # 最多回溯 3 条含图消息，避免 token 过多
        img_count = 0
        result = []
        for msg in reversed(msgs):
            atts = msg.pop("_attachments", [])
            msg.pop("_msg_id", None)
            if atts and img_count < _MAX_HIST_IMGS and msg.get("role") == "user":
                b64_list = await asyncio.gather(*[self._att_to_b64(a) for a in atts])
                valid = [b for b in b64_list if b]
                if valid:
                    content_list = [{"type": "text", "text": msg["content"]}]
                    for b64 in valid:
                        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
                    msg = {**msg, "content": content_list}
                    img_count += 1
            result.append(msg)
        result.reverse()
        return result

    # ──────────────────────────────────────────────
    # 决策辅助
    # ──────────────────────────────────────────────

    def _should_respond_group(self, event: GroupMsgEvent, level: PermLevel) -> bool:
        if event.at_bot:
            return True
        hour = datetime.now().hour
        in_quiet = self._in_quiet_hours(hour)
        prob = self._group_resp_prob
        if level >= PermLevel.ADMIN:
            prob = min(prob * self._admin_prob_mult, self._admin_prob_cap)
        if in_quiet:
            prob *= self._quiet_prob_factor
        return random.random() < prob

    def _in_quiet_hours(self, hour: int) -> bool:
        s, e = self._quiet_start, self._quiet_end
        if s <= e:
            return s <= hour < e
        return hour >= s or hour < e

    # ──────────────────────────────────────────────
    # 发送辅助（模拟打字延迟）
    # ──────────────────────────────────────────────

    async def _send_private_delayed(self, user_id: int, text: str) -> None:
        await self._typing_delay(text)
        await self._napcat.send_private_msg(user_id, text)

    async def _send_group_delayed(self, group_id: int, text: str) -> None:
        await self._typing_delay(text)
        await self._napcat.send_group_msg(group_id, text)

    async def _typing_delay(self, text: str) -> None:
        delay_ms = min(len(text) * self._typing_ms_per_char, self._typing_max_ms)
        delay_ms += random.randint(0, self._typing_jitter_ms)
        await asyncio.sleep(delay_ms / 1000)

    # ──────────────────────────────────────────────
    # 记忆管理
    # ──────────────────────────────────────────────

    def _create_bg_task(self, coro) -> asyncio.Task:
        """创建后台任务并保持强引用，防止 GC 取消，同时记录未捕获异常。"""
        t = asyncio.create_task(coro)
        self._bg_tasks.add(t)
        t.add_done_callback(self._bg_tasks.discard)

        def _log_exc(task: asyncio.Task):
            if not task.cancelled() and task.exception():
                logger.warning(f"后台任务异常: {task.exception()}")

        t.add_done_callback(_log_exc)
        return t

    def _save_message(
        self,
        session_key: str,
        role: str,
        content: str,
        sender_qq: int = None,
        sender_name: str = None,
        attachments: list = None,
    ) -> Optional[int]:
        conn = sqlite3.connect(self._db_path)
        try:
            cur = conn.execute(
                """INSERT INTO messages (session_key, role, sender_qq, sender_name, content, attachments, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_key,
                    role,
                    sender_qq,
                    sender_name,
                    content,
                    json.dumps(attachments or [], ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
            return None
        finally:
            conn.close()

    def _update_message_content(self, msg_id: int, content: str) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("UPDATE messages SET content=? WHERE id=?", (content, msg_id))
            conn.commit()
        except Exception as e:
            logger.error(f"更新消息失败: {e}")
        finally:
            conn.close()

    def _get_recent_messages(self, session_key: str, limit: int = 30) -> List[dict]:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                """SELECT id, role, sender_qq, sender_name, content, attachments, created_at
                   FROM messages WHERE session_key=?
                   ORDER BY id DESC LIMIT ?""",
                (session_key, limit),
            )
            rows = [dict(r) for r in c.fetchall()]
            return list(reversed(rows))
        except Exception as e:
            logger.debug(f"读取最近消息失败 ({session_key}): {e}")
            return []
        finally:
            conn.close()

    def _get_long_term_memory(self, session_key: str, limit: int = 5) -> str:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                """SELECT content FROM long_term_memory WHERE session_key=?
                   ORDER BY importance DESC, id DESC LIMIT ?""",
                (session_key, limit),
            )
            rows = [r["content"] for r in c.fetchall()]
            return "\n".join(rows)
        except Exception as e:
            logger.debug(f"读取长期记忆失败 ({session_key}): {e}")
            return ""
        finally:
            conn.close()

    def _maybe_compress(self, session_key: str) -> None:
        """异步触发记忆压缩"""
        conn = sqlite3.connect(self._db_path)
        try:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM messages WHERE session_key=?", (session_key,)
            )
            count = c.fetchone()[0]
        except Exception as e:
            logger.debug(f"检查压缩阈值失败 ({session_key}): {e}")
            return
        finally:
            conn.close()

        if count > 0 and count % self._compress_every == 0:
            self._create_bg_task(self._compress_memory(session_key))

    async def _compress_memory(self, session_key: str) -> None:
        """将旧消息压缩为长期记忆摘要，同步写到 MEMORY.md，并触发 soul 反思。"""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                """SELECT id, role, sender_name, content FROM messages
                   WHERE session_key=? ORDER BY id ASC""",
                (session_key,),
            )
            all_rows = [dict(r) for r in c.fetchall()]
            conn.close()

            if len(all_rows) <= self._short_term_keep:
                return

            to_compress = all_rows[: -self._short_term_keep]
            lines = []
            for r in to_compress:
                name = r.get("sender_name") or (
                    self._bot_name if r["role"] == "assistant" else "用户"
                )
                lines.append(f"{name}: {r['content']}")
            conversation_text = "\n".join(lines)

            adapter = self._router.get_basic_adapter()
            if adapter is None:
                return

            is_private = session_key.startswith("private:")

            # ── 1a. 对话摘要（写 SQLite + MEMORY.md，记录"聊了什么"）─────────
            if is_private:
                conv_prompt = (
                    "以下是一段私信对话记录。请用中文简洁总结这段对话的主要话题和重要信息，"
                    "以要点列表输出（最多6条，每条以'- '开头）。\n"
                    "只写实际发生的事情，不要评价，不要重复废话。\n\n"
                    f"对话记录：\n{conversation_text}"
                )
            else:
                conv_prompt = (
                    "以下是一段群聊记录。请用中文提取其中值得记住的信息，"
                    "以要点列表输出（最多8条，每条以'- '开头）。\n"
                    "包含：重要话题、有价值的信息、谁说了什么值得记录的事。\n"
                    "格式：'- [昵称] 说了/提到了…' 或 '- 群里讨论了…'\n"
                    "忽略：打招呼、无实质内容的闲聊、重复性内容。\n\n"
                    f"对话记录：\n{conversation_text}"
                )

            summary_resp = await adapter.chat(
                [{"role": "user", "content": conv_prompt}],
                max_tokens=250,
            )
            summary = summary_resp.content.strip()
            if not summary:
                return

            # ── 1b. 人物档案更新（仅私聊，提取关于那个人的事实）──────────────
            person_facts = ""
            if is_private:
                person_prompt = (
                    "以下是一段私信对话记录。请只提取**对方（人类用户）**透露的个人信息，"
                    "以简洁要点列表输出（最多6条，每条以'- '开头）。\n\n"
                    "要提取的内容（关于对方的）：\n"
                    "  - 他/她的名字、职业、年龄、所在地等基本信息\n"
                    "  - 他/她表达的喜好、偏好、观点、情感\n"
                    "  - 他/她提到的重要事情、约定、请求\n\n"
                    "严格不要写的：\n"
                    "  - AI（小萌）自己的行为、能力、回答内容\n"
                    "  - 打招呼、泛泛的对话\n"
                    "  - 对方没有明确说出的推测\n\n"
                    "如果对话中对方几乎没透露个人信息，直接回复 SKIP。\n\n"
                    f"对话记录：\n{conversation_text}"
                )
                facts_resp = await adapter.chat(
                    [{"role": "user", "content": person_prompt}],
                    max_tokens=200,
                )
                facts = facts_resp.content.strip()
                if facts and facts.upper() != "SKIP" and len(facts) > 5:
                    person_facts = facts

            # ── 2. 删旧消息 + 写 SQLite 摘要 ─────────────────────────────────
            ids_to_delete = [r["id"] for r in to_compress]
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids_to_delete))})",
                ids_to_delete,
            )
            conn.execute(
                """INSERT INTO long_term_memory (session_key, content, memory_type, importance, created_at)
                   VALUES (?, ?, 'summary', 1, ?)""",
                (session_key, summary, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()

            # ── 3. 写 MEMORY.md 流水账 ────────────────────────────────────────
            self._append_memory_md(session_key, summary)

            # ── 4. 私聊：把人物事实写入 memory/{identity}.md ──────────────────
            if is_private and person_facts:
                try:
                    qq = int(session_key.split(":", 1)[1])
                    identity = self._resolve_identity(qq)
                    mem_file = self._memory_dir / f"{identity}.md"
                    now_str = datetime.now().strftime("%Y-%m-%d")
                    entry = f"\n## {now_str} 新增了解\n\n{person_facts}\n"
                    with open(mem_file, "a", encoding="utf-8") as f:
                        f.write(entry)
                    logger.info(f"身份记忆文件已更新: memory/{identity}.md")
                except Exception as e:
                    logger.debug(f"写身份记忆文件失败: {e}")

            logger.info(f"会话 {session_key} 记忆已压缩")

        except Exception as e:
            logger.error(f"记忆压缩失败: {e}")

    def _append_memory_md(self, session_key: str, summary: str) -> None:
        """将摘要追加到 data/persona/MEMORY.md，保持 OpenClaw 格式。"""
        try:
            self._memory_md_path.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = f"\n## {now}  [{session_key}]\n\n{summary}\n"
            with open(self._memory_md_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"写 MEMORY.md 失败: {e}")

    # ──────────────────────────────────────────────
    # 动态路由 prompt（附加从文件学到的规则）
    # ──────────────────────────────────────────────

    def _build_router_prompt(self) -> str:
        """每次路由时动态读 routing_hints.md，把学到的规则附加到 base prompt 后。"""
        try:
            if self._routing_hints_path.exists():
                hints = self._routing_hints_path.read_text(encoding="utf-8").strip()
                if hints:
                    return (
                        _ROUTER_BASE_PROMPT
                        + f"\n\nAdditional learned rules (higher priority):\n{hints}"
                    )
        except Exception:
            pass
        return _ROUTER_BASE_PROMPT

    # ──────────────────────────────────────────────
    # Identity 解析
    # ──────────────────────────────────────────────

    def _load_identity_links(self) -> dict:
        """
        读取 identity_links.json，兼容三种格式，统一返回 {str(qq): identity_name}。
          格式 A（原始）: {"links": {"qq:3797723137": "owner"}}
          格式 B（简洁）: {"3797723137": "owner"}
          格式 v2（当前）: {"_schema":"v2", "owner": {"qq_list":[...], "level":"owner"}, ...}
        """
        try:
            if not self._identity_links_path.exists():
                return {}
            data = json.loads(self._identity_links_path.read_text(encoding="utf-8"))
            result = {}

            # 格式 v2：有 _schema 字段，结构为 {identity_name: {qq_list: [...]}}
            if data.get("_schema") == "v2":
                for identity_name, info in data.items():
                    if identity_name.startswith("_") or not isinstance(info, dict):
                        continue
                    for qq in info.get("qq_list", []):
                        result[str(qq)] = identity_name
                return result

            # 格式 A：有 links 键
            if "links" in data and isinstance(data["links"], dict):
                for k, v in data["links"].items():
                    if not isinstance(v, str):
                        continue
                    platform_id = k.split(":", 1)[1] if ":" in k else k
                    result[platform_id] = v
                return result

            # 格式 B：直接 QQ 号 → identity（可能是字符串或 dict）
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, str):
                    result[k] = v
                elif isinstance(v, dict):
                    identity = v.get("alias") or v.get("identity")
                    if identity:
                        result[k] = identity
            return result
        except Exception as e:
            logger.debug(f"读取 identity_links 失败: {e}")
            return {}

    def _resolve_identity(self, qq: int) -> str:
        """将 QQ 号解析为 canonical 身份名，每次读文件保证即时生效。"""
        links = self._load_identity_links()
        return links.get(str(qq), f"user_{qq}")

    def _init_person_memory_if_needed(self, qq: int, nick: str) -> None:
        """
        第一次和某人说话时，自动在 data/memory/ 建立基础档案。
        只写一次（文件存在就跳过），后续由 LLM add_memory 工具填充细节。
        """
        try:
            identity = self._resolve_identity(qq)
            mem_file = self._memory_dir / f"{identity}.md"
            if not mem_file.exists():
                now = datetime.now().strftime("%Y-%m-%d")
                content = f"# 关于 {nick}（QQ: {qq}）\n\n首次见面：{now}\n"
                mem_file.write_text(content, encoding="utf-8")
                logger.info(f"建立记忆档案: memory/{identity}.md ({nick})")
        except Exception as e:
            logger.debug(f"建立记忆档案失败: {e}")

    def _get_effective_level(self, qq: int) -> PermLevel:
        """
        综合权限判断：先查 QQPermissionManager，再查 identity_links。
        如果某个 QQ 和 owner_qq 共享同一个 identity，视为 OWNER。
        这样多个 QQ 号绑定到同一身份后，全部享有相同权限等级。
        """
        level = self._perm.get_level(qq)
        if level == PermLevel.OWNER:
            return level
        if level == PermLevel.BLACKLIST:
            return level
        # 检查 identity 是否和主人相同
        try:
            owner_identity = self._resolve_identity(self._owner_qq)
            this_identity = self._resolve_identity(qq)
            # 只有明确映射过的 identity 才提升权限（排除 "user_{qq}" 默认值）
            if this_identity == owner_identity and not this_identity.startswith(
                "user_"
            ):
                return PermLevel.OWNER
        except Exception:
            pass
        return level

    def _get_identity_sessions(self, identity: str) -> List[str]:
        """
        返回所有映射到这个 identity 的平台账号对应的 private session_key 列表。
        格式：platform:id → private:{id}（跨平台通用）
        """
        links = self._load_identity_links()
        return [
            f"private:{platform_id}"
            for platform_id, ident in links.items()
            if ident == identity
        ]

    def _load_person_memory(
        self, identity: str, sender_qq: int, exclude_session: str = ""
    ) -> str:
        """
        加载某人的跨对话、跨平台记忆。
        来源优先级：
          1. data/memory/{identity}.md（手动/压缩写入，最权威）
          2. SQLite long_term_memory user:{qq}（add_memory tool 写入）
          3. SQLite long_term_memory private:{qq}（压缩摘要）
          4. messages 表中未压缩的私聊消息（最近 10 条）← 这是关键兜底
        """
        parts: List[str] = []

        # 1. identity 记忆文件
        mem_file = self._memory_dir / f"{identity}.md"
        if mem_file.exists():
            content = mem_file.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)

        # 2. 显式记忆（add_memory tool 写入）
        explicit = self._get_long_term_memory(f"user:{sender_qq}")
        if explicit:
            parts.append(explicit)

        # 3. 私聊压缩摘要（long_term_memory 表）
        private_sk = f"private:{sender_qq}"
        if private_sk != exclude_session:
            ltm = self._get_long_term_memory(private_sk)
            if ltm:
                parts.append(ltm)

        # 4. 同一 identity 其他账号的压缩摘要
        for sk in self._get_identity_sessions(identity):
            if sk in (exclude_session, private_sk):
                continue
            ltm = self._get_long_term_memory(sk)
            if ltm:
                parts.append(ltm)

        # 5. 未压缩的私聊原始消息（messages 表直取，弥补压缩阈值前的空窗期）
        #    只在不是当前 session 时加载（私聊时 exclude_session=private:{qq}，不重复）
        if private_sk != exclude_session:
            raw = self._get_recent_messages(private_sk, 12)
            if raw:
                lines = []
                for r in raw:
                    name = r.get("sender_name") or (
                        self._bot_name if r["role"] == "assistant" else "对方"
                    )
                    lines.append(f"{name}: {r['content'][:120]}")
                parts.append(f"（与此人的私信记录）\n" + "\n".join(lines))

        return "\n\n".join(parts)

    # ──────────────────────────────────────────────

    def _load_knowledge(self) -> str:
        """读取 data/memory/knowledge.md（通用知识库），限制长度避免撑爆 context。"""
        knowledge_file = self._memory_dir / "knowledge.md"
        if not knowledge_file.exists():
            return ""
        try:
            text = knowledge_file.read_text(encoding="utf-8").strip()
            # 只取最后 3000 字符，防止知识库过大
            if len(text) > self._knowledge_truncate:
                text = "…（更早的知识已省略）\n" + text[-self._knowledge_truncate :]
            return text
        except Exception:
            return ""

    # ──────────────────────────────────────────────
    # 初始化辅助
    # ──────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA journal_mode=WAL")
        # 迁移：给旧表加 attachments 列
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT NOT NULL DEFAULT '[]'")
            conn.commit()
        except Exception:
            pass  # 列已存在
        conn.commit()
        conn.close()
        logger.info(f"数据库已初始化: {self._db_path}")

    @staticmethod
    def _build_router(config: dict) -> ModelLayerRouter:
        router = ModelLayerRouter()
        models_cfg = config.get("models", [])
        for m in models_cfg:
            # 解析 provider：显式配置优先，否则 None 走自动检测
            provider_raw = m.get("provider")
            provider = None
            if provider_raw:
                try:
                    provider = ModelProvider(provider_raw)
                except ValueError:
                    logger.warning(
                        f"未知的 provider '{provider_raw}'，将自动检测，已知: "
                        f"{[p.value for p in ModelProvider]}"
                    )

            endpoint = ModelEndpoint(
                model_id=m.get("model_id", m["model_name"]),
                layer=ModelLayer(m.get("layer", "basic")),
                role=ModelRole(m.get("role", "chat")),
                endpoint=m["endpoint"],
                model_name=m["model_name"],
                api_key=m.get("api_key"),
                max_tokens=m.get("max_tokens", 4096),
                temperature=m.get("temperature", 0.85),
                enabled=m.get("enabled", True),
                priority=m.get("priority", 1),
                proxy=m.get("proxy"),
                num_ctx=m.get("num_ctx"),
                provider=provider,
                thinking=m.get("thinking"),
                capabilities=m.get("capabilities", []),
            )
            router.register_model(endpoint)
        return router

    def _cache_group_name(self, group_id: int) -> None:
        """尝试从 NapCat 获取群名并缓存（异步，不阻塞）"""
        self._create_bg_task(self._fetch_and_cache_group_name(group_id))

    async def _fetch_and_cache_group_name(self, group_id: int) -> None:
        try:
            info = await self._napcat.get_group_info(group_id)
            name = info.get("group_name") or info.get("name") or ""
            if name:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT OR REPLACE INTO group_info (group_id, group_name, updated_at) VALUES (?, ?, ?)",
                    (group_id, name, datetime.now().isoformat()),
                )
                conn.commit()
                conn.close()
        except Exception:
            pass
