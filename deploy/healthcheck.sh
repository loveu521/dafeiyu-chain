#!/usr/bin/env bash
# 看门狗：WebUI 不响应则重启 AstrBot（systemd 之外再加一层兜底）。
set -euo pipefail
LOG=/opt/dafeiyu/logs/watchdog.log
PORT=${ASTRBOT_PORT:-6185}

if curl -fsS -m 8 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 \
   || curl -fsS -m 8 -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
  echo "$(date '+%F %T') OK  WebUI :${PORT} 响应正常" >> "$LOG"
else
  echo "$(date '+%F %T') FAIL WebUI :${PORT} 无响应，重启 astrbot.service" >> "$LOG"
  systemctl restart astrbot.service
fi
