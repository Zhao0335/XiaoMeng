@echo off
chcp 65001 >nul
title XiaoMengCore 启动器

:menu
cls
echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║                                                           ║
echo  ║              🐱 XiaoMengCore 启动器                       ║
echo  ║                                                           ║
echo  ╠═══════════════════════════════════════════════════════════╣
echo  ║                                                           ║
echo  ║   [1] 启动管理面板 (推荐)                                  ║
echo  ║       - 可视化管理界面                                     ║
echo  ║       - 管理技能、插件、模型                                ║
echo  ║       - 包含论文阅读器                                     ║
echo  ║                                                           ║
echo  ║   [2] 启动统一网关 (v1)                                    ║
echo  ║       - 统一消息入口                                       ║
echo  ║       - 用户分组会话隔离                                   ║
echo  ║                                                           ║
echo  ║   [3] 启动 v2 网关 (推荐)                                  ║
echo  ║       - 跨平台身份统一                                     ║
echo  ║       - 同一用户QQ/微信共享会话                            ║
echo  ║       - 消息队列 + 钩子系统                                ║
echo  ║                                                           ║
echo  ║   [4] 启动命令行对话                                       ║
echo  ║       - 在命令行中与小萌对话                                ║
echo  ║                                                           ║
echo  ║   [5] 安装/更新依赖                                        ║
echo  ║       - 首次使用请先运行此项                                ║
echo  ║                                                           ║
echo  ║   [6] 检查系统状态                                         ║
echo  ║       - 检查配置和模型是否正常                              ║
echo  ║                                                           ║
echo  ║   [7] 打开配置文件夹                                       ║
echo  ║       - 查看和编辑配置文件                                  ║
echo  ║                                                           ║
echo  ║   [0] 退出                                                 ║
echo  ║                                                           ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.
set /p choice="请输入选项 [0-7]: "

if "%choice%"=="1" goto panel
if "%choice%"=="2" goto gateway
if "%choice%"=="3" goto gateway_v2
if "%choice%"=="4" goto cli
if "%choice%"=="5" goto install
if "%choice%"=="6" goto check
if "%choice%"=="7" goto openfolder
if "%choice%"=="0" goto end
goto menu

:panel
cls
echo.
echo  正在启动管理面板...
echo  启动后请在浏览器打开: http://127.0.0.1:8000
echo  按 Ctrl+C 可停止服务
echo.
python run_panel.py
pause
goto menu

:gateway
cls
echo.
echo  正在启动统一网关 (v1)...
echo  启动后可通过以下方式访问:
echo  - HTTP API: http://127.0.0.1:8080/api/message
echo  - WebSocket: ws://127.0.0.1:8080/ws/{user_id}
echo  按 Ctrl+C 可停止服务
echo.
python run_gateway.py
pause
goto menu

:gateway_v2
cls
echo.
echo  正在启动 v2 网关...
echo.
echo  ═════════════════════════════════════════════════════════
echo   XiaoMengCore v2 核心特性:
echo  ═════════════════════════════════════════════════════════
echo   ✓ 跨平台身份统一
echo     - 将 QQ、微信、Telegram 等账号关联到同一身份
echo     - 同一用户在不同平台共享会话历史
echo.
echo   ✓ 消息队列系统
echo     - STEER: 打断当前任务
echo     - FOLLOWUP: 追加到队列
echo     - COLLECT: 收集多条消息
echo.
echo   ✓ 钩子系统
echo     - 在 Agent 生命周期注入自定义逻辑
echo.
echo   ✓ 双层持久化
echo     - sessions.json: 会话元数据
echo     - .jsonl: 完整对话记录
echo  ═════════════════════════════════════════════════════════
echo.
echo  启动后访问:
echo  - Dashboard: http://127.0.0.1:8080/dashboard
echo  - API: http://127.0.0.1:8080/api/message
echo.
echo  按 Ctrl+C 可停止服务
echo.
python run_gateway_v2.py
pause
goto menu

:cli
cls
echo.
echo  正在启动命令行对话...
echo  输入消息后按回车发送
echo  输入 'exit' 或 'quit' 退出
echo.
python cli_chat.py
pause
goto menu

:install
cls
echo.
echo  正在安装/更新依赖...
echo.
pip install -r requirements.txt
echo.
echo  安装完成!
pause
goto menu

:check
cls
echo.
echo  正在检查系统状态...
echo.
python -c "
print('=' * 50)
print('XiaoMengCore 系统检查')
print('=' * 50)

import os
import sys

errors = []
warnings = []

print('\n[Python 版本]')
print(f'  Python {sys.version}')

print('\n[依赖检查]')
try:
    import openai
    print('  ✅ openai')
except:
    print('  ❌ openai - 请运行 [3] 安装依赖')
    errors.append('缺少 openai')

try:
    import fastapi
    print('  ✅ fastapi')
except:
    print('  ❌ fastapi - 请运行 [3] 安装依赖')
    errors.append('缺少 fastapi')

try:
    import yaml
    print('  ✅ pyyaml')
except:
    print('  ❌ pyyaml - 请运行 [3] 安装依赖')
    errors.append('缺少 pyyaml')

print('\n[配置文件]')
if os.path.exists('data/config.json'):
    print('  ✅ data/config.json')
else:
    print('  ❌ data/config.json 不存在')
    errors.append('配置文件不存在')

if os.path.exists('data/config.example.json'):
    print('  ✅ data/config.example.json')
else:
    print('  ⚠️ data/config.example.json 不存在')

print('\n[人设文件]')
persona_dir = 'data/persona'
for f in ['SOUL.md', 'AGENTS.md', 'MEMORY.md']:
    path = os.path.join(persona_dir, f)
    if os.path.exists(path):
        print(f'  ✅ {f}')
    else:
        print(f'  ⚠️ {f} 不存在')
        warnings.append(f'{f} 不存在')

print('\n[技能文件]')
skills_dir = 'data/skills'
if os.path.exists(skills_dir):
    count = len([d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d))])
    print(f'  ✅ 已加载 {count} 个技能')
else:
    print('  ⚠️ 技能目录不存在')

print('\n[模型配置]')
try:
    import json
    with open('data/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    llm = config.get('llm', {})
    print(f'  提供商: {llm.get(\"provider\", \"未设置\")}')
    print(f'  模型: {llm.get(\"model\", \"未设置\")}')
    print(f'  地址: {llm.get(\"base_url\", \"未设置\")}')
except Exception as e:
    print(f'  ❌ 读取配置失败: {e}')
    errors.append('配置读取失败')

print('\n' + '=' * 50)
if errors:
    print('❌ 发现问题:')
    for e in errors:
        print(f'   - {e}')
    print('\n请先解决上述问题后再启动')
elif warnings:
    print('⚠️ 有警告但不影响使用')
    for w in warnings:
        print(f'   - {w}')
else:
    print('✅ 系统状态正常!')
print('=' * 50)
"
pause
goto menu

:openfolder
cls
echo.
echo  正在打开配置文件夹...
start "" "data"
goto menu

:end
cls
echo.
echo  感谢使用 XiaoMengCore!
echo.
timeout /t 2 >nul
exit
