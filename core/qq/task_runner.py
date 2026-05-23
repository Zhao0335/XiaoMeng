"""
Task runner mixin for QQGateway.
Extracted from gateway.py to reduce file size.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional

from ..model_layer import ModelLayer, ModelRole
from .permissions import PermLevel
from .skills import ModelTier, SkillContext, UserLevel
from .tools import (
    TOOL_SCHEMAS,
    QQToolExecutor,
    build_context_skills_prompt,
    get_tool_schemas_for_context,
)

logger = logging.getLogger(__name__)


class TaskRunnerMixin:
    """Mixin providing the main LLM task coroutine factory for QQGateway."""

    def _make_task_coro_factory(
        self,
        image_atts: List[Dict] = None,
        user_msg_id: Optional[int] = None,
        forced_level: Optional["PermLevel"] = None,
        forced_route: Optional[str] = None,  # "LOCAL" / "CLOUD" / "PRO"
    ):
        """返回一个 coro factory，用于 TaskPool.create_and_run"""

        async def _run(task):
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
                    # 把历史折叠为单条 user 消息：避免模型在 assistant role 后续写小萌台词
                    _hist_rows = self._get_recent_messages(
                        session_key, self._routing_context_limit
                    )
                    _ctx_lines = [
                        f"{'用户' if r['role'] == 'user' else '小萌'}: {r['content'][:120]}"
                        for r in _hist_rows
                    ]
                    routing_ctx = [{
                        "role": "user",
                        "content": (
                            "Recent conversation (for context only, do NOT reply):\n"
                            + "\n".join(_ctx_lines)
                            + "\n\nClassify the LAST user message. Output exactly one word: LOCAL, CLOUD, or PRO."
                        ),
                    }]

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
                if len(user_text) >= 8:
                    _auto_mem = tool_executor._search_memory(user_text[:120])
                    if _auto_mem and _auto_mem not in ("没找到相关记忆", "搜索词不能为空"):
                        system += f"\n\n## 自动检索到的相关记忆\n\n{_auto_mem}"
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
                            if len(user_text) >= 8:
                                _auto_mem = tool_executor._search_memory(user_text[:120])
                                if _auto_mem and _auto_mem not in ("没找到相关记忆", "搜索词不能为空"):
                                    _cloud_system += f"\n\n## 自动检索到的相关记忆\n\n{_auto_mem}"
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

                # 后台将本次交流压缩成小萌的感受，写入内心世界事件流
                _local_adapter = self._router.get_available_adapter(ModelLayer.BASIC, ModelRole.CHAT)
                if _local_adapter is not None:
                    from core.inner_world.events import compress_session_to_event
                    _last_exchange = f"用户：{user_text[:200]}\n小萌：{final_text[:200]}"
                    self._create_bg_task(compress_session_to_event(
                        session_key, _last_exchange, _local_adapter, self._inner_world_event_logger,
                        soul=soul,
                        sender_name=nick,
                    ))

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
