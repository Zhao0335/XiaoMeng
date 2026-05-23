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
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
from .tools import (
    QQToolExecutor,
    init_skill_registry,
)
from .tts import SoVITSTTS
from ..inner_world import InnerWorldAgent, InnerWorldEventLogger
from .memory import MemoryMixin
from .identity import IdentityMixin
from .prompt_builder import PromptBuilderMixin
from .task_runner import TaskRunnerMixin

logger = logging.getLogger(__name__)





# ──────────────────────────────────────────────
# 主类
# ──────────────────────────────────────────────


class QQGateway(MemoryMixin, IdentityMixin, PromptBuilderMixin, TaskRunnerMixin):
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

        # 内心世界：idle 触发阈值（秒）
        _iw_cfg = config.get("inner_world", {})
        self._iw_idle_threshold: int = _iw_cfg.get("idle_threshold", 900)   # 15min
        self._iw_cooldown: int = _iw_cfg.get("cooldown", 1800)              # 30min
        self._last_any_msg_time: float = time.time()
        self._last_inner_world_time: float = 0.0
        self._inner_world_agent = InnerWorldAgent(
            router=self._router,
            executor_factory=self._make_inner_world_executor,
            skills_dir=self._skills_dir,
            data_dir=self._data_dir,
            soul_path=self._soul_path,
            memory_md_path=self._memory_md_path,
            plugin_manager=self._plugin_manager,
            timeout=self._timeout_cloud,
        )
        self._inner_world_event_logger = InnerWorldEventLogger(self._data_dir)

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
        await self._napcat.start()
        # 恢复未完成的任务
        restored = self._task_manager.load_running_tasks_from_db(
            self._make_task_coro_factory()
        )
        if restored:
            logger.info(f"恢复未完成任务: {restored}")
        # 启动内心世界 watchdog + 每小时情绪标注 + MEMORY.md 二次压缩
        self._create_bg_task(self._inner_world_watchdog())
        self._create_bg_task(self._inner_world_enricher_loop())
        self._create_bg_task(self._memory_md_compressor_loop())

    async def stop(self) -> None:
        self._proactive.stop_all()
        await self._napcat.stop()

    # ── 内心世界 ──────────────────────────────────────────────

    def _make_inner_world_executor(self):
        """为内心世界活动创建工具执行器（OWNER 权限，无群聊 session）。"""
        return QQToolExecutor(
            db_path=self._db_path,
            soul_path=self._soul_path,
            data_dir=self._data_dir,
            session_key="inner_world",
            sender_qq=self._owner_qq,
            level=PermLevel.OWNER,
            identity="owner",
            proxy=self._proxy,
            napcat=self._napcat,
            tts=self._tts,
            target_id=self._owner_qq,
            is_private=True,
            task=None,
            plugin_manager=self._plugin_manager,
        )

    async def _inner_world_watchdog(self) -> None:
        """每 60s 检查一次，满足条件时触发内心世界。"""
        while True:
            await asyncio.sleep(60)
            try:
                now = time.time()
                hour = datetime.now().hour
                if self._in_quiet_hours(hour):
                    continue
                if now - self._last_any_msg_time < self._iw_idle_threshold:
                    continue
                active = any(
                    t.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.WAITING_USER)
                    for t in self._task_manager._tasks.values()
                )
                if active:
                    continue
                if now - self._last_inner_world_time < self._iw_cooldown:
                    continue
                self._last_inner_world_time = now
                logger.info("内心世界触发条件满足，注入任务")
                self._create_bg_task(self._inner_world_agent.run())
            except Exception as e:
                logger.warning(f"内心世界 watchdog 异常: {e}")

    async def _inner_world_enricher_loop(self) -> None:
        """每小时用 CLOUD 模型为 events.jsonl 里缺失情绪标签的条目批量标注。"""
        while True:
            await asyncio.sleep(3600)
            try:
                from ..model_layer import ModelLayer, ModelRole
                cloud = self._router.get_available_adapter(ModelLayer.BRAIN, ModelRole.CHAT)
                if cloud is None:
                    continue
                soul = self._read_soul()
                n = await self._inner_world_event_logger.enrich_with_cloud(cloud, soul=soul)
                if n:
                    logger.info(f"inner_world events 已标注 {n} 条")
            except Exception as e:
                logger.warning(f"inner_world enricher 异常: {e}")

    async def _memory_md_compressor_loop(self) -> None:
        """每 30 分钟检查 MEMORY.md，超过阈值时用 CLOUD 二次压缩，维持文件长度。"""
        _THRESHOLD = 8000
        _KEEP_TAIL = 3000
        while True:
            await asyncio.sleep(1800)
            try:
                if not self._memory_md_path.exists():
                    continue
                content = self._memory_md_path.read_text(encoding="utf-8")
                if len(content) <= _THRESHOLD:
                    continue
                from ..model_layer import ModelLayer, ModelRole
                cloud = self._router.get_available_adapter(ModelLayer.BRAIN, ModelRole.CHAT)
                if cloud is None:
                    continue
                tail = content[-_KEEP_TAIL:]
                old_part = content[:-_KEEP_TAIL]
                system_prompt = (
                    "你是小萌的记忆整理助手。以下是 MEMORY.md 文件的早期部分，"
                    "包含私聊摘要和主人的规则设定。\n"
                    "请压缩整合：\n"
                    "1. 完整保留所有主人要求、规则、小萌的性格设定\n"
                    "2. 提炼对话摘要为关键人物信息和重要事件（每条一句话）\n"
                    "3. 删除重复/过时/无实质内容\n"
                    "4. 输出格式：每条以「- 」开头，控制在 2500 字以内\n"
                    "5. 只输出压缩后的内容，不加解释"
                )
                resp = await asyncio.wait_for(
                    cloud.chat(
                        [{"role": "user", "content": old_part}],
                        system_prompt=system_prompt,
                        max_tokens=1500,
                    ),
                    timeout=60,
                )
                compressed = (resp.content or "").strip()
                if not compressed:
                    continue
                new_content = "# 小萌的重要记忆（已压缩）\n\n" + compressed + "\n\n---\n\n" + tail
                self._memory_md_path.write_text(new_content, encoding="utf-8")
                logger.info(f"MEMORY.md 压缩完成：{len(content)} → {len(new_content)} 字符")
            except asyncio.TimeoutError:
                logger.debug("MEMORY.md 压缩超时")
            except Exception as e:
                logger.warning(f"MEMORY.md 压缩异常: {e}")

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

        if isinstance(event, (PrivateMsgEvent, GroupMsgEvent)):
            self._last_any_msg_time = time.time()

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
