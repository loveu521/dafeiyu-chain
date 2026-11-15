#!/usr/bin/env bash
# 阶段二：Debian/Ubuntu 服务器一键部署「大肥鱼 + AstrBot(QQ 官方机器人 WebSocket)」
#
#   sudo bash deploy/install_server.sh
#
# 幂等：可重复执行；不会覆盖 AstrBot 已有配置（data/cmd_config.json）。
# 设计前提：AstrBot 4.x 要求 Python>=3.12，链路本体用系统 3.11，两套 venv 隔离。
set -euo pipefail

ROOT=/opt/dafeiyu
APP=$ROOT/app
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
V311=$ROOT/venv
V312=$ROOT/astrbot_venv
ABDATA=$ROOT/astrbot_data
PORT=${ASTRBOT_PORT:-6185}
IDX="--index-url https://mirrors.aliyun.com/pypi/simple/"

log() { printf "\n\033[36m>>> %s\033[0m\n" "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "请用 root 运行"; exit 1; }

log "0/9 同步工程到 $APP"
mkdir -p "$ROOT"/{app,data,logs} "$ABDATA"
if [ "$SRC" != "$APP" ]; then
  tar -C "$SRC" --exclude=output --exclude='__pycache__' --exclude='*.pyc' \
      --exclude=.git -cf - . | tar -C "$APP" -xf -
else
  echo "脚本已在 $APP/deploy 下，原地使用"
fi
ln -sfn "$APP/deploy" "$ROOT/deploy"

log "1/9 2G swap（1.9G 内存机器跑 Chromium 必备）"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi
swapon --show

log "2/9 系统包"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ffmpeg python3-venv python3-pip curl fonts-wqy-zenhei

log "3/9 链路 venv（系统 Python 3.11）"
[ -d "$V311" ] || python3 -m venv "$V311"
"$V311/bin/pip" install -q $IDX -r "$APP/requirements.txt"
"$V311/bin/playwright" install --with-deps chromium

log "4/9 uv + Python 3.12（AstrBot 4.x 硬要求）"
mkdir -p "$ROOT/bin"
if [ ! -x "$ROOT/bin/uv" ]; then
  (curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$ROOT/bin" sh) \
    || { python3 -m pip install --break-system-packages -q uv; ln -sf "$(command -v uv)" "$ROOT/bin/uv"; }
fi
"$ROOT/bin/uv" python install 3.12

log "5/9 AstrBot venv（Python 3.12）"
[ -d "$V312" ] || "$ROOT/bin/uv" venv --python 3.12 "$V312"
"$ROOT/bin/uv" pip install --python "$V312/bin/python" $IDX \
  astrbot edge-tts bilibili-api-python playwright pydub PyYAML aiohttp
# 关键：3.12 的 playwright 版本与 3.11 不同，浏览器 build 号不同，必须各装一份
"$V312/bin/playwright" install chromium

log "6/9 初始化 AstrBot + 投放插件"
cd "$ABDATA"
"$V312/bin/astrbot" init -y >/dev/null 2>&1 || true
ln -sfn "$APP/astrbot_plugin_dafeiyu" "$ABDATA/data/plugins/astrbot_plugin_dafeiyu"

log "7/9 注册 systemd 服务"
cp "$APP/deploy"/astrbot.service "$APP/deploy"/dafeiyu-cruise.service \
   "$APP/deploy"/dafeiyu-cruise.timer "$APP/deploy"/dafeiyu-watchdog.service \
   "$APP/deploy"/dafeiyu-watchdog.timer /etc/systemd/system/
chmod +x "$APP/deploy"/*.sh
systemctl daemon-reload
[ -x /usr/sbin/ufw ] && ufw allow "${PORT}/tcp" >/dev/null || true

log "8/9 启动"
systemctl enable --now astrbot.service >/dev/null
systemctl enable --now dafeiyu-cruise.timer >/dev/null
systemctl enable --now dafeiyu-watchdog.timer >/dev/null

log "9/9 验收"
for i in $(seq 1 30); do
  curl -fsS -m 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 && break
  sleep 2
done
"$APP/deploy/verify.sh" || echo "（验收有告警，看上面输出）"

echo
echo "=========================================================="
echo " WebUI      : http://$(curl -sS -m 5 ifconfig.me 2>/dev/null || echo '<服务器IP>'):${PORT}"
echo " 初始账号   : astrbot"
echo " 初始密码   : 见日志 grep 'Initial password' $ROOT/logs/astrbot.log"
echo "            （登录后请立即修改）"
echo
echo " 最后一步   : WebUI → 机器人 → +创建 → QQ官方机器人(WebSocket)"
echo "              → 扫码一键创建 → 手机QQ扫码（自动写入 AppID/Secret）"
echo " 日志       : tail -f $ROOT/logs/astrbot.log"
echo " 手动巡游   : systemctl start dafeiyu-cruise.service"
echo "=========================================================="
