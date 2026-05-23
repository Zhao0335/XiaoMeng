"""
把 HTML Config Manager 挂到 run_live2d.py 已有的 FastAPI app 上。

入口：register_admin_routes(app, napcat, perm_mgr, data_dir)
路由：
  GET  /admin               → 登录 + 管理面板（SPA）
  GET  /admin/static/*      → 静态资源
  WS   /admin/ws            → 鉴权 + 配置 CRUD
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.qq.permissions import PermLevel, QQPermissionManager

from .auth import QQVerifyAuth
from .config_io import ConfigIO

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


def register_admin_routes(
    app: FastAPI,
    napcat,
    perm_mgr: QQPermissionManager,
    data_dir: Path,
) -> None:
    auth = QQVerifyAuth(napcat, perm_mgr, min_level=PermLevel.ADMIN)
    cio = ConfigIO(Path(data_dir))

    # 静态资源（CSS/JS/图片）
    app.mount(
        "/admin/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="admin-static",
    )

    @app.get("/admin")
    async def _admin_index():
        return FileResponse(_STATIC_DIR / "index.html")

    @app.websocket("/admin/ws")
    async def _admin_ws(websocket: WebSocket):
        await websocket.accept()
        qq = await auth.handshake(websocket)
        if qq is None:
            try:
                await websocket.close()
            except Exception:
                pass
            return

        async def _send(obj: dict):
            await websocket.send_text(json.dumps(obj, ensure_ascii=False))

        # 推送可管理的文件清单
        await _send({"type": "files", "items": cio.list_keys()})

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                t = msg.get("type")

                try:
                    if t == "load":
                        key = msg["key"]
                        await _send({"type": "config", "key": key, **cio.read(key)})

                    elif t == "reveal":
                        key = msg["key"]
                        path = msg.get("path") or []
                        val = cio.reveal_field(key, path)
                        await _send({
                            "type": "revealed",
                            "key": key,
                            "path": path,
                            "value": val,
                        })

                    elif t == "save":
                        key = msg["key"]
                        result = cio.write(key, msg["data"])
                        await _send({"type": "saved", "key": key, **result})

                    elif t == "history":
                        key = msg["key"]
                        items = cio.list_history(key)
                        await _send({"type": "history", "key": key, "items": items})

                    elif t == "diff":
                        # 返回快照文本供前端做 diff
                        name = msg["name"]
                        try:
                            text = cio.get_snapshot(name)
                            await _send({"type": "snapshot", "name": name, "text": text})
                        except (FileNotFoundError, PermissionError) as e:
                            await _send({"type": "error", "message": f"快照不可用: {e}"})

                    elif t == "restore":
                        key = msg["key"]
                        cio.restore(key, msg["name"])
                        await _send({"type": "restored", "key": key, "name": msg["name"]})

                    else:
                        await _send({"type": "error", "message": f"未知操作 {t}"})

                except KeyError as e:
                    await _send({"type": "error", "message": f"缺少字段: {e}"})
                except Exception as e:
                    logger.exception("管理面板操作失败")
                    await _send({"type": "error", "message": str(e)})

        except WebSocketDisconnect:
            logger.info(f"管理面板 QQ {qq} 断开")
