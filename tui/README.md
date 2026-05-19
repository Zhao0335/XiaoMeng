"""
============================================================
  LingMeng TUI — 现代终端用户界面（模块化重构版本）
============================================================

技术选型文档 / Technology Selection Document
------------------------------------------------------------

## 1. 技术栈选择：Textual 8.x + Rich 14.x

### 选型理由

在全面评估当前主流TUI框架后，选择 **Textual 8.2.6** 作为核心框架，理由如下：

| 框架            | 语言   | 现代化 | 视觉表现 | 异步 | CSS | 生态 |
|----------------|--------|--------|---------|------|-----|------|
| Textual 8.x    | Python | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅  | ✅  | ⭐⭐⭐⭐ |
| Ratatui        | Rust   | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐  | ✅  | ❌  | ⭐⭐⭐ |
| Bubble Tea     | Go     | ⭐⭐⭐⭐  | ⭐⭐⭐⭐  | ✅  | ❌  | ⭐⭐⭐ |
| urwid          | Python | ⭐⭐    | ⭐⭐    | ✅  | ❌  | ⭐⭐⭐ |
| Rich (solo)    | Python | ⭐⭐⭐   | ⭐⭐⭐⭐⭐ | ❌  | ❌  | ⭐⭐⭐⭐⭐ |

### 核心优势分析

1. **CSS 样式系统**：Textual 提供完整的 CSS 解析引擎，支持 60+ 属性，
   包括布局(fr/%)、颜色(rgb/hex)、边框样式(heavy/solid/dashed)、
   动画过渡、滚动条定制等。这使得设计"炫酷"的视觉效果变得极其便捷。

2. **响应式布局**：内置 Flexbox-like 布局系统，支持 fr 单位、百分比、
   固定宽度混合使用。终端窗口调整大小时自动适配。

3. **Reactive 数据绑定**：类似 React/Vue 的响应式属性系统，
   数据变化自动触发UI更新，大幅简化状态管理。

4. **原生异步**：基于 Python asyncio，非阻塞IO，保证界面流畅不卡顿。

5. **内置组件丰富**：TabbedContent, Tree, DataTable, ProgressBar,
   LoadingIndicator 等开箱即用。

6. **Rich 渲染引擎**：继承 Rich 的全部渲染能力，支持 Markdown、
   Syntax Highlighting、Table、Panel 等高级渲染。

7. **屏幕管理**：内置 Screen 栈管理，支持 push/pop/switch 导航。

8. **主题系统**：支持多主题切换，CSS变量系统。

### 与 curses 的对比（旧版 vs 新版）

| 特性              | curses (旧v2)         | Textual (新v3)           |
|------------------|----------------------|--------------------------|
| 样式定义          | 数字颜色对            | CSS + 设计令牌            |
| 布局             | 手动坐标计算          | CSS Flexbox 自动布局      |
| 状态管理          | 手动全局变量          | Reactive 响应式属性       |
| 组件化           | 单一巨类              | 模块化Widget/Screen      |
| 异步             | threading            | 原生 asyncio             |
| 滚动条           | 手动实现              | 内置ScrollView           |
| 主题             | 硬编码                | 可切换主题系统            |
| 扩展性           | 困难                  | 极佳                     |

## 2. 模块架构设计

```
XiaoMeng/tui/
├── __init__.py          # Package 入口，版本信息
├── __main__.py          # python -m XiaoMeng.tui 入口
├── app.py               # LingMengApp 主应用 + 全局 CSS
├── theme.py             # 设计令牌：颜色、样式函数
├── events.py            # 自定义消息体系
│
├── screens/             # 屏幕层（页面级组件）
│   ├── __init__.py
│   ├── splash.py        # 启动动画屏（渐变进度条+吉祥物）
│   └── main.py          # 主界面（侧边栏+Tab内容区）
│
├── widgets/             # 控件层（可复用UI组件）
│   ├── __init__.py
│   ├── mascot.py        # 吉祥物渲染（多种表情）
│   ├── chat_view.py     # 聊天消息列表 + 输入栏
│   ├── config_tree.py   # 配置树形编辑器
│   ├── status_view.py   # 系统状态面板
│   └── help_view.py     # 帮助文档面板
│
├── services/            # 服务层（业务逻辑）
│   ├── __init__.py
│   └── engine.py        # AI聊天引擎（路由+流式响应）
│
└── utils/               # 工具层（辅助函数）
    ├── __init__.py
    └── config.py        # 配置读写、敏感信息掩码
```

### 分层设计原则

- **Screen → Widget → Service → Utils** 自上而下的依赖关系
- 高层（Screen）只依赖抽象（Widget接口），不直接依赖实现细节
- 跨层通信通过 Message 事件系统，实现松耦合
- 每个 Widget 拥有独立的 CSS 样式作用域

## 3. 视觉设计系统

### 色彩体系（Cyber-Fantasy 暗色主题）

```
背景层次：
  BG_DEEP   #0a0a14 ← 最深背景
  BG_PANEL  #12122a ← 面板背景
  BG_SURFACE #1a1a3e ← 卡片/输入框表面
  BG_HOVER  #222255 ← 悬停高亮

功能色：
  ACCENT   #b8a0ff ← 主强调色（紫色调）
  SUCCESS  #5fd7af ← 成功/在线（绿色调）
  WARNING  #ffaf5f ← 警告（橙色调）
  ERROR    #ff5f87 ← 错误（粉红色调）
  INFO     #5fafff ← 信息（蓝色调）

前景文字：
  FG_PRIMARY   #e0e0f0 ← 主文字
  FG_SECONDARY #8888aa ← 次要文字
  FG_DIM       #555577 ← 暗淡文字
  FG_MUTED     #333355 ← 最淡文字
```

### 视觉特效

1. **启动动画**：吉祥物 ASCII Art + 渐变进度条 + 打字机效果文字揭示
2. **分层边框**：heavy 粗边框分隔面板，solid 细边框分隔卡片
3. **自定义滚动条**：深色轨道 + 紫色滑块，hover/active 状态变色
4. **Tab 激活态**：底部 heavy 强调色边框 + 文字高亮
5. **聊天气泡**：用户消息右对齐紫色背景，助手消息左对齐绿色背景
6. **状态指示器**：● 绿色运行 / ✗ 红色错误

## 4. 核心功能对照

| 旧版功能 (TUI_v2.py)         | 新版实现                          | 改进                          |
|-----------------------------|----------------------------------|------------------------------|
| 启动画面 (SplashScene)        | SplashScreen                     | 富文本渲染 + CSS动画           |
| 分栏布局                     | CSS Horizontal + fr 布局         | 响应式自动适配                 |
| 4 Tab 切换                   | TabbedContent 组件               | 内置键盘导航 + 激活态样式       |
| 聊天消息 + 气泡              | ChatView + ChatInputBar          | Rich Panel 气泡 + Markdown    |
| 配置树编辑器                 | ConfigTreeWidget (Tree组件)      | 原生展开/折叠 + 图标           |
| 状态面板                     | StatusViewWidget (Rich Table)    | 结构化表格 + 彩色状态          |
| 帮助面板                     | HelpViewWidget                   | 分区面板 + 键盘指示器          |
| 吉祥物渲染 (Mascot)          | MascotWidget + 12种表情          | 模块化 + 动态切换              |
| AI 聊天引擎                  | ChatEngine (services/)           | 独立服务层，易于测试           |
| 配置保存/加载                | utils/config.py                  | 独立工具模块                   |
| 敏感信息掩码                 | utils/config.py (mask_value)     | 一致化处理                    |

## 5. 使用指南

### 启动方式

```bash
# 方式一：模块运行
cd XiaoMeng
python -m tui

# 方式二：直接运行
cd XiaoMeng
python tui/app.py

# 方式三：Textual 开发模式（支持热重载）
cd XiaoMeng
textual run tui/app.py
```

### 键盘快捷键

全局：
- Tab / Shift+Tab — 切换面板
- Ctrl+S — 保存配置
- Ctrl+Q — 退出（有未保存修改时需按两次）
- i — 聚焦聊天输入框
- Esc — 取消输入/失去焦点

聊天面板：
- i / Enter — 开始输入
- Esc — 取消输入
- j / ↓ — 下滚
- k / ↑ — 上滚
- PgDn / PgUp — 翻页

配置面板：
- j / ↓ — 下移光标
- k / ↑ — 上移光标
- Enter — 展开节点 / 编辑叶节点
- Space — 切换布尔值

状态面板：
- j / ↓ — 下滚
- k / ↑ — 上滚
- r — 刷新

### 依赖安装

```bash
pip install textual rich
```

### 兼容性

- ✅ Linux (xterm, gnome-terminal, alacritty, kitty, tmux)
- ✅ macOS (Terminal.app, iTerm2)
- ✅ Windows (Windows Terminal, PowerShell)
- ✅ True Color (24-bit) 终端推荐使用
- ✅ 256-color 终端兼容模式自动降级
"""

print(__doc__)
