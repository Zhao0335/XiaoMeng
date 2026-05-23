"""
web - 二次元风格 HTML Config Manager

挂载到 run_live2d.py 的 FastAPI 实例上，提供：
- /admin           登录 + 配置管理 UI
- /admin/ws        WebSocket：QQ 验证码鉴权 + 配置 CRUD
- /admin/static/*  静态资源
"""

from .routes import register_admin_routes

__all__ = ["register_admin_routes"]
