#!/bin/bash
# ============================================================
# start_sovits.sh — 从 qq_config.json 读取配置启动 SoVITS 实例
# 开机自启 / systemd 调用入口
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/data/qq_config.json"

# 用 Python 从 JSON 读配置（比 jq 更通用，避免没装 jq）
read_config() {
    python3 -c "
import json, sys
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)['tts']
print(cfg['$1'])
"
}

echo "[SoVITS] 读取配置..."

SOVITS_HOME=$(read_config sovits_home)
SOVITS_PORT=$(read_config sovits_port)
GPT_WEIGHTS=$(read_config gpt_weights_path)
SOVITS_WEIGHTS=$(read_config sovits_weights_path)
REF_AUDIO=$(read_config ref_audio)
REF_TEXT=$(read_config ref_text)
GPT_CONFIG=$(read_config gpt_config_path)

echo "[SoVITS] 工作目录: $SOVITS_HOME"
echo "[SoVITS] 端口:     $SOVITS_PORT"
echo "[SoVITS] GPT权重:  $GPT_WEIGHTS"
echo "[SoVITS] SoVITS权重: $SOVITS_WEIGHTS"
echo "[SoVITS] 参考音频: $REF_AUDIO"

# 第一步：杀掉旧进程，释放端口
PID_FILE="/tmp/sovits_${SOVITS_PORT}.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[SoVITS] 杀掉旧进程 PID=$OLD_PID..."
        kill "$OLD_PID" 2>/dev/null
        sleep 1
    fi
    rm -f "$PID_FILE"
fi
# 再加一层保险：用 fuser 杀端口占用
if fuser "${SOVITS_PORT}/tcp" >/dev/null 2>&1; then
    echo "[SoVITS] 强制释放端口 ${SOVITS_PORT}..."
    fuser -k "${SOVITS_PORT}/tcp" 2>/dev/null
    sleep 1
fi

# 第二步：启动 api_v2.py
# PYTHONNOUSERSITE=1 防止 ~/.local 的包覆盖 conda 环境的包
echo "[SoVITS] 启动 API 服务..."
cd "$SOVITS_HOME"
PYTHONNOUSERSITE=1 /home/qwq/anaconda3/envs/GPTSoVits/bin/python3 api_v2.py \
    -a 127.0.0.1 \
    -p "$SOVITS_PORT" \
    -c "$GPT_CONFIG" &
API_PID=$!

# 等待服务就绪
echo "[SoVITS] 等待服务就绪..."
for i in $(seq 1 30); do
    if curl -s "http://127.0.0.1:$SOVITS_PORT" > /dev/null 2>&1; then
        echo "[SoVITS] 服务已就绪（第 ${i}s）"
        break
    fi
    sleep 1
done

# 第三步：加载权重和参考音频
echo "[SoVITS] 加载 GPT 权重..."
curl -s "http://127.0.0.1:$SOVITS_PORT/set_gpt_weights?weights_path=$GPT_WEIGHTS"

echo "[SoVITS] 加载 SoVITS 权重..."
curl -s "http://127.0.0.1:$SOVITS_PORT/set_sovits_weights?weights_path=$SOVITS_WEIGHTS"

echo "[SoVITS] 设置参考音频..."
ENCODED_TEXT=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$REF_TEXT'''))")
ENCODED_AUDIO=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$REF_AUDIO'''))")
curl -s "http://127.0.0.1:$SOVITS_PORT/set_refer_audio?refer_audio_path=$ENCODED_AUDIO&prompt_text=$ENCODED_TEXT"
echo ""

echo "[SoVITS] ✅ 启动完成！PID=$API_PID"
echo "$API_PID" > "$PID_FILE"
