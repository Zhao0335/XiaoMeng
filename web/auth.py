"""
QQ 验证码鉴权（HTML 管理面板）

复刻 run_live2d.py 的 auth_required → login_request → code_sent → verify_code → auth_ok
握手协议，并多加最低权限等级检查（默认 ADMIN）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import string
from typing import Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from core.qq.permissions import PermLevel, QQPermissionManager

logger = logging.getLogger(__name__)


class QQVerifyAuth:
    """通过 QQ 私聊验证码确认用户身份。"""

    def __init__(
        self,
        napcat,
        perm_mgr: QQPermissionManager,
        *,
        code_ttl: int = 300,
        min_level: PermLevel = PermLevel.ADMIN,
    ):
        self._napcat = napcat
        self._perm_mgr = perm_mgr
        self._code_ttl = code_ttl
        self._min_level = min_level
        self._pending: Dict[int, str] = {}

    async def _send_code(self, qq: int) -> None:
        code = "".join(random.choices(string.digits, k=6))
        self._pending[qq] = code

        async def _expire():
            await asyncio.sleep(self._code_ttl)
            self._pending.pop(qq, None)

        asyncio.create_task(_expire())
        try:
            await self._napcat.call_api(
                "send_private_msg",
                {
                    "user_id": qq,
                    "message": f"小萌管理面板验证码：{code}（5 分钟内有效）",
                },
            )
            logger.info(f"管理面板验证码已发送给 QQ {qq}")
        except Exception as e:
            logger.warning(f"发送验证码失败: {e}")

    async def handshake(self, ws: WebSocket) -> Optional[int]:
        """
        跑完整的握手流程。返回通过鉴权的 QQ；任何失败/断开都返回 None。
        握手期间发的所有消息都从 ws 收，结果通过 ws 发。
        """

        async def _send(obj: dict):
            await ws.send_text(json.dumps(obj, ensure_ascii=False))

        await _send({"type": "auth_required", "message": "请输入你的 QQ 号以验证身份"})

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")

                if etype == "login_request":
                    try:
                        qq = int(event["qq"])
                    except (KeyError, ValueError, TypeError):
                        await _send({"type": "auth_fail", "reason": "无效的 QQ 号"})
                        continue
                    await self._send_code(qq)
                    await _send({"type": "code_sent", "qq": qq})

                elif etype == "verify_code":
                    try:
                        qq = int(event["qq"])
                        code = str(event["code"]).strip()
                    except (KeyError, ValueError, TypeError):
                        await _send({"type": "auth_fail", "reason": "格式错误"})
                        continue

                    if self._pending.get(qq) != code:
                        await _send({"type": "auth_fail", "reason": "验证码错误或已过期"})
                        continue

                    self._pending.pop(qq, None)
                    level = self._perm_mgr.get_level(qq)
                    if level < self._min_level:
                        await _send({
                            "type": "auth_fail",
                            "reason": f"需要 {self._min_level.label()} 及以上权限（当前：{level.label()}）",
                        })
                        return None

                    await _send({
                        "type": "auth_ok",
                        "qq": qq,
                        "level": level.name,
                        "label": level.label(),
                    })
                    logger.info(f"管理面板 QQ {qq} 鉴权通过，权限 {level.name}")
                    return qq

        except WebSocketDisconnect:
            logger.info("管理面板：连接在鉴权阶段断开")
            return None
