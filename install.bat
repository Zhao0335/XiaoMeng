@echo off
chcp 65001 >nul
title XiaoMengCore 安装向导

cls
echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║                                                           ║
echo  ║              🐱 XiaoMengCore 安装向导                     ║
echo  ║                                                           ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.
echo  此脚本将帮你完成以下操作:
echo.
echo    1. 安装 Python 依赖包
echo    2. 创建必要的文件夹
echo    3. 检查配置文件
echo.
echo  按任意键开始安装...
pause >nul

echo.
echo  [1/3] 安装 Python 依赖...
echo  ─────────────────────────────────────────────────────────
echo.

pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo  ❌ 安装失败！请检查:
    echo     - 是否已安装 Python
    echo     - 是否有网络连接
    echo.
    pause
    exit /b 1
)

echo.
echo  ✅ 依赖安装完成!
echo.

echo  [2/3] 创建必要的文件夹...
echo  ─────────────────────────────────────────────────────────
echo.

if not exist "data" mkdir data
if not exist "data\persona" mkdir data\persona
if not exist "data\skills" mkdir data\skills
if not exist "data\memory" mkdir data\memory
if not exist "data\.learnings" mkdir data\.learnings
if not exist "plugins" mkdir plugins

echo  ✅ 文件夹创建完成!
echo.

echo  [3/3] 检查配置文件...
echo  ─────────────────────────────────────────────────────────
echo.

if exist "data\config.json" (
    echo  ✅ 配置文件已存在
) else (
    if exist "data\config.example.json" (
        copy "data\config.example.json" "data\config.json" >nul
        echo  ✅ 已从示例创建配置文件
    ) else (
        echo  ⚠️ 配置文件不存在，请手动创建
    )
)

echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║                                                           ║
echo  ║                   🎉 安装完成!                            ║
echo  ║                                                           ║
echo  ╠═══════════════════════════════════════════════════════════╣
echo  ║                                                           ║
echo  ║  接下来:                                                  ║
echo  ║                                                           ║
echo  ║  1. 确保已安装 Ollama 并下载了模型                         ║
echo  ║     下载地址: https://ollama.ai                           ║
echo  ║     运行命令: ollama pull qwen2.5:7b                      ║
echo  ║                                                           ║
echo  ║  2. 双击 start.bat 启动小萌                               ║
echo  ║                                                           ║
echo  ║  3. 在浏览器打开 http://127.0.0.1:8000                    ║
echo  ║                                                           ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.
pause
