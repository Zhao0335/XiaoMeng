#!/usr/bin/env bash
# 小萌初始化脚本 — 新部署时运行一次
# 从模板生成配置文件，不覆盖已存在的文件

set -e
DATA="$(cd "$(dirname "$0")/data" && pwd)"

echo "=== 小萌初始化 (数据目录: $DATA) ==="

mkdir -p "$DATA/memory" "$DATA/persona" "$DATA/skills"

copy_if_missing() {
    local src="$1" dst="$2"
    if [ -f "$dst" ]; then
        echo "  跳过（已存在）: $(basename $dst)"
    else
        cp "$src" "$dst"
        echo "  已创建: $(basename $dst)"
    fi
}

copy_if_missing "$DATA/qq_config.example.json"      "$DATA/qq_config.json"
copy_if_missing "$DATA/identity_links.example.json" "$DATA/identity_links.json"
copy_if_missing "$DATA/persona/SOUL.template.md"    "$DATA/persona/SOUL.md"

for f in qq_admins.json qq_blacklist.json whitelist.json users.json; do
    [ -f "$DATA/$f" ] || echo '{}' > "$DATA/$f"
done
[ -f "$DATA/persona/MEMORY.md" ]   || touch "$DATA/persona/MEMORY.md"
[ -f "$DATA/routing_hints.md" ]    || touch "$DATA/routing_hints.md"

echo ""
echo "完成！请编辑以下文件填写配置："
echo "  $DATA/qq_config.json       ← API Key、QQ 号、代理地址"
echo "  $DATA/identity_links.json  ← 主人 QQ 号"
