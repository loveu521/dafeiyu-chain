#!/usr/bin/env bash
# 服务器链路验收：跑一遍完整巡游，检查产物与服务状态。
# 用法：/opt/dafeiyu/deploy/verify.sh
set -euo pipefail

ROOT=/opt/dafeiyu
APP=$ROOT/app
OUT=$APP/output
PY=$ROOT/venv/bin/python

echo "==================== 1. 完整链路实跑 ===================="
cd "$APP"
$PY run_local.py

echo
echo "==================== 2. 产物验收 ===================="
$PY - <<'PY'
import json, sys
from pathlib import Path
out = Path("/opt/dafeiyu/app/output")
r = json.loads((out / "run_report.json").read_text(encoding="utf-8"))
cap = {c["name"]: c for c in r["capabilities"]}
print("能力自检：", {k: ("OK" if v["ok"] else "FAIL") for k, v in cap.items()})
print("收件箱：", r["inbox_total"], "条", r["inbox_by_kind"])
checks = {
    "语音 mp3": out / "voice.mp3",
    "语音 wav": out / "voice.wav",
    "截图 png": out / "card.png",
    "卡片 html": out / "card.html",
    "评论草稿": out / "comment_draft.json",
    "收件箱": out / "inbox.jsonl",
}
bad = []
for name, p in checks.items():
    ok = p.exists() and p.stat().st_size > 0
    print(f"  {name:12s} {'OK' if ok else 'MISSING':8s} {p.stat().st_size if p.exists() else 0} B")
    if not ok:
        bad.append(name)
h = (out / "voice.mp3").read_bytes()[:4]
# MP3 可能带 ID3 标签，也可能直接是 MPEG 帧同步头（0xFF Ex）
mp3 = h.startswith(b"ID3") or (len(h) >= 2 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0)
wav = (out / "voice.wav").read_bytes()[:4] == b"RIFF"
png = (out / "card.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
print("文件头：", {"mp3": mp3, "wav": wav, "png": png})
if bad or not (mp3 and wav and png) or not all(c["ok"] for c in r["capabilities"]):
    print("验收失败：", bad)
    sys.exit(1)
print("产物全部有效")
PY

echo
echo "==================== 3. 服务状态 ===================="
for s in astrbot dafeiyu-cruise.timer; do
  printf "%-24s " "$s"
  systemctl is-active "$s" 2>/dev/null || echo "(未启用)"
done
echo "--- 监听端口 ---"
ss -tlnp | grep -E "6185|22|80" || true
echo
echo "==================== 4. 最近日志 ===================="
tail -n 12 "$ROOT/logs/astrbot.log" 2>/dev/null || echo "(暂无 astrbot 日志)"
echo
echo "验收完成：$(date '+%F %T %Z')"
