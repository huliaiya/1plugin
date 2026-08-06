#!/bin/bash
# 狐狸插件一键同步脚本
# 用途：在 AstrBot 部署服务器上执行，将插件代码完整对齐到远程最新版本。
# 适用场景：main.py 与 fox_toolbox/ 文件版本混用导致的
#           ImportError: cannot import name '_to_int'
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

# 用 src/. 语法合并覆盖，确保已存在的旧目录内文件也被更新
mkdir -p "$PLUGIN_DIR/fox_toolbox"
cp -r /tmp/1plugin_tmp/fox_toolbox/. "$PLUGIN_DIR/fox_toolbox/"
cp /tmp/1plugin_tmp/main.py "$PLUGIN_DIR/"
cp /tmp/1plugin_tmp/metadata.yaml "$PLUGIN_DIR/"
cp /tmp/1plugin_tmp/_conf_schema.json "$PLUGIN_DIR/"
mkdir -p "$PLUGIN_DIR/pages"
cp -r /tmp/1plugin_tmp/pages/. "$PLUGIN_DIR/pages/"

# 校验同步结果
echo "== 同步后校验 =="
grep -c "def _to_int" "$PLUGIN_DIR/fox_toolbox/snapshot_renderer.py"
grep -n "^version" "$PLUGIN_DIR/metadata.yaml"

# 校验通过则提示完全重启
if grep -q "def _to_int" "$PLUGIN_DIR/fox_toolbox/snapshot_renderer.py"; then
    echo ""
    echo "文件已同步。必须完全重启 AstrBot 进程（不是插件热重载），"
    echo "否则 fox_toolbox 旧模块仍缓存在 sys.modules 中，导入会继续失败。"
else
    echo "同步失败，请检查网络后重试。"
    exit 1
fi
