#!/bin/bash
# 狐狸插件一键同步脚本
# 用途：在 AstrBot 部署服务器上执行，将插件代码完整对齐到远程最新版本，
#       避免因 main.py 与 fox_toolbox/ 等文件版本混用导致 ImportError。
# 用法：bash scripts/fix_deploy.sh
set -e

PLUGIN_DIR=/root/AstrBot/data/plugins/astrbot_plugin_fox_toolbox

# 下载最新插件代码（已存在则增量更新，避免重复克隆）
if [ -d /tmp/1plugin_tmp/.git ]; then
    cd /tmp/1plugin_tmp
    git fetch origin
    git reset --hard origin/main
else
    git clone --depth 1 https://github.com/huliaiya/1plugin.git /tmp/1plugin_tmp
fi

# 同步插件全部文件到部署目录
cp -r /tmp/1plugin_tmp/fox_toolbox "$PLUGIN_DIR/"
cp /tmp/1plugin_tmp/main.py "$PLUGIN_DIR/"
cp /tmp/1plugin_tmp/metadata.yaml "$PLUGIN_DIR/"
cp /tmp/1plugin_tmp/_conf_schema.json "$PLUGIN_DIR/"
cp -r /tmp/1plugin_tmp/pages "$PLUGIN_DIR/"

# 校验 _to_int 是否同步成功
if grep -q "def _to_int" "$PLUGIN_DIR/fox_toolbox/snapshot_renderer.py"; then
    echo "同步成功。请重启 AstrBot 或在插件管理里重载插件。"
else
    echo "同步失败，请检查网络后重试。"
    exit 1
fi
