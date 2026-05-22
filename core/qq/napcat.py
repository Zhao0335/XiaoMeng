"""
NapCat WebSocket 客户端
连接到 NapCat（OneBot v11 协议），接收事件，发送 API 请求
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class NapCatClient:
    """
    连接到 NapCat 的 WebSocket 客户端。
    NapCat 作为 WS Server，本客户端作为 WS Client 连接过去。
    """

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:3001",
        access_token: str = "",
        reconnect_interval: float = 5.0,
        api_timeout: float = 15.0,
        ping_interval: float = 20,
        ping_timeout: float = 20,
    ):
        self._url = ws_url
        self._token = access_token
        self._reconnect_interval = reconnect_interval
        self._api_timeout = api_timeout
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._ws = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._event_handlers: list[Callable] = []
        self._running = False
        self._self_id: Optional[int] = None  # bot 的 QQ 号，连接后通过 lifecycle 获取

    # ──────────────────────────────────────────────
    # 公开 API
    # ──────────────────────────────────────────────

    def on_event(self, handler: Callable) -> None:
        """注册事件回调（async def handler(raw: dict)）"""
        self._event_handlers.append(handler)

    async def start(self) -> None:
        """启动客户端（自动重连循环，永不返回直到 stop() 被调用）"""
        self._running = True
        while self._running:
            try:
                await self._connect_and_run()
            except Exception as e:
                if self._running:
                    logger.warning(f"NapCat 断连: {e}，{self._reconnect_interval}s 后重连")
                    await asyncio.sleep(self._reconnect_interval)

    async def stop(self) -> None:
        """停止客户端"""
        self._running = False
        if self._ws:
            await self._ws.close()

    async def call_api(
        self, action: str, params: Dict[str, Any] = None, timeout: float = None
    ) -> Dict[str, Any]:
        if timeout is None:
            timeout = self._api_timeout
        """调用 OneBot API，等待响应"""
        if self._ws is None:
            raise RuntimeError("WebSocket 未连接")
        echo = str(uuid.uuid4())
        payload = {"action": action, "params": params or {}, "echo": echo}
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[echo] = fut
        await self._ws.send(json.dumps(payload, ensure_ascii=False))
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            raise TimeoutError(f"API {action} 超时")

    # ──────────────────────────────────────────────
    # 便捷方法
    # ──────────────────────────────────────────────

    async def send_private_msg(self, user_id: int, message: str) -> Dict:
        return await self.call_api("send_private_msg", {"user_id": user_id, "message": message})

    async def send_group_msg(self, group_id: int, message: str) -> Dict:
        return await self.call_api("send_group_msg", {"group_id": group_id, "message": message})

    async def set_friend_add_request(self, flag: str, approve: bool, remark: str = "") -> Dict:
        return await self.call_api(
            "set_friend_add_request",
            {"flag": flag, "approve": approve, "remark": remark},
        )

    async def set_group_add_request(
        self, flag: str, sub_type: str, approve: bool, reason: str = ""
    ) -> Dict:
        return await self.call_api(
            "set_group_add_request",
            {"flag": flag, "sub_type": sub_type, "approve": approve, "reason": reason},
        )

    async def get_stranger_info(self, user_id: int) -> Dict:
        try:
            result = await self.call_api("get_stranger_info", {"user_id": user_id})
            return result.get("data", {})
        except Exception:
            return {}

    async def get_group_info(self, group_id: int) -> Dict:
        try:
            result = await self.call_api("get_group_info", {"group_id": group_id})
            return result.get("data", {})
        except Exception:
            return {}

    async def get_group_member_info(self, group_id: int, user_id: int) -> Dict:
        try:
            result = await self.call_api(
                "get_group_member_info", {"group_id": group_id, "user_id": user_id}
            )
            return result.get("data", {})
        except Exception:
            return {}

    async def get_login_info(self) -> Dict:
        try:
            result = await self.call_api("get_login_info", {})
            return result.get("data", {})
        except Exception:
            return {}

    # ──────────────────────────────────────────────
    # 内部实现
    # ──────────────────────────────────────────────

    async def _connect_and_run(self) -> None:
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        logger.info(f"连接 NapCat: {self._url}")
        # websockets >= 14 renamed extra_headers → additional_headers
        ws_version = tuple(int(x) for x in websockets.__version__.split(".")[:2])
        header_kwarg = "additional_headers" if ws_version >= (14, 0) else "extra_headers"
        async with websockets.connect(
            self._url, **{header_kwarg: headers}, ping_interval=self._ping_interval, ping_timeout=self._ping_timeout
        ) as ws:
            self._ws = ws
            logger.info("NapCat 已连接")

            # 获取 self_id — 作为 task 与消息循环并发，避免死锁
            async def _fetch_self_id():
                try:
                    info = await self.get_login_info()
                    self._self_id = info.get("user_id")
                    logger.info(f"Bot QQ: {self._self_id}")
                except Exception:
                    pass
            asyncio.create_task(_fetch_self_id())

            try:
                async for raw_msg in ws:
                    await self._handle_raw(raw_msg)
            except ConnectionClosed:
                pass
            finally:
                self._ws = None
                # 取消所有挂起的 API 调用
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(RuntimeError("连接断开"))
                self._pending.clear()

    async def _handle_raw(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # API 响应
        if "echo" in data and data["echo"] in self._pending:
            fut = self._pending.pop(data["echo"])
            if not fut.done():
                fut.set_result(data)
            return

        # 事件
        if "post_type" in data:
            for handler in self._event_handlers:
                asyncio.create_task(self._safe_call(handler, data))

    @staticmethod
    async def _safe_call(handler: Callable, data: dict) -> None:
        try:
            await handler(data)
        except Exception as e:
            logger.error(f"事件处理器出错: {e}", exc_info=True)
