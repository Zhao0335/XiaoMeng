# 小萌 · HTML 管理面板（web/）

二次元风格的 web 配置管理器，与 `tui/`（Textual 终端 UI）平级。

## 功能
- QQ 私聊验证码登录（复用 `run_live2d.py` 的鉴权流程）
- 仅允许 **ADMIN 及以上**权限进入
- 一处编辑 5 类配置：`qq_config.json` / `qq_permissions.json` / `identity_links.json` / `persona/SOUL.md` / `persona/MEMORY.md`
- 敏感字段（`api_key` / `token` 等）默认 mask 显示，眼睛按钮临时取真值
- 输入框 datalist 自动填充（localStorage，每字段最近 5 次值）
- 每次保存自动写时间戳快照到 `data/.config_history/`，可在右侧抽屉里 diff & 一键恢复（每文件保留 20 份）

## 启动方式
HTML 管理面板**寄宿**在 `run_live2d.py` 的 FastAPI 进程里，不另起服务。

```bash
cd XiaoMeng
uvicorn run_live2d:app --host 0.0.0.0 --port 8765
# 浏览器访问 http://127.0.0.1:8765/admin
```

## 文件结构
```
web/
├── __init__.py
├── routes.py           # 把路由挂到 FastAPI 上
├── auth.py             # QQVerifyAuth：复刻 live2d 鉴权 + 权限门
├── config_io.py        # 读写 + 快照 + 敏感字段 mask/merge
└── static/
    ├── index.html
    ├── style.css       # 樱花粉/粉雾蓝调色板，纯 CSS 樱花飘落动画
    ├── app.js          # vanilla JS，无依赖
    └── images/         # 把 mascot.png 丢这里就会出现在右下角
```

## 自定义吉祥物
把图片命名为 `mascot.png` 放进 `web/static/images/` 即可（也支持 .jpg/.gif/.webp）。
没图片时自动用内置 SVG 兜底。
