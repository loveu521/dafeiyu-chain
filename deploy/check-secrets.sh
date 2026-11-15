#!/usr/bin/env bash
# 敏感信息扫描：提交 / 推送前必跑。
#
#   bash deploy/check-secrets.sh     → 退出码 0 = 干净，1 = 发现疑似凭据
#
# 只匹配「带值的凭据」，不匹配字段名单出现（如 README 里讲 "API Key" 是安全的）。
# 命中时只打印脱敏前缀，绝不回显完整值。扫描范围 = git 已跟踪 + 未跟踪且未被忽略的文件。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 - <<'PY'
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(".").resolve()
SELF = "deploy/check-secrets.sh"          # 排除自身（里面是正则字面量，不是真值）

def sh(*args):
    return subprocess.check_output(args).decode().split("\0")

has_git = (ROOT / ".git").is_dir() and shutil.which("git") is not None
if has_git:
    # 提交场景：只看「将入库」的文件 = 已跟踪 + 未跟踪且未被 ignore
    tracked = sh("git", "ls-files", "-z")
    untracked = sh("git", "ls-files", "--others", "--exclude-standard", "-z")
    candidates = set(tracked + untracked)
else:
    # 服务器 tar 部署场景（无 .git）：扫描源码目录，跳过产物/缓存/私有数据
    skip_dirs = {"output", ".git", "__pycache__", "astrbot_data", "secrets",
                 ".venv", "venv", "logs"}
    skip_suffix = {".png", ".jpg", ".jpeg", ".gif", ".mp3", ".wav",
                   ".pyc", ".log", ".env", ".pem", ".key"}
    candidates = set()
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if any(part in skip_dirs for part in rel.parts) or p.suffix in skip_suffix:
            continue
        candidates.add(rel.as_posix())

files = sorted({f for f in candidates
                if f and f != SELF and (ROOT / f).is_file()})

# (类别, 正则) —— 全部只匹配「值」，不匹配字段名
PATTERNS = [
    ("GitHub token",
     r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
    ("OpenAI/Anthropic key",
     r"sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}"),
    ("AWS access key",
     r"AKIA[0-9A-Z]{16}"),
    ("私钥",
     r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |)?PRIVATE KEY-----"),
    ("B站登录凭证",
     r"(?:SESSDATA|bili_jct|buvid3|dedeuserid)\s*[:=]\s*['\"]?[A-Za-z0-9%\-_,]{16,}"),
    ("密钥赋值",
     r"(?:password|passwd|api[_-]?key|app[_-]?secret|access[_-]?token|auth[_-]?token|secret)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
    ("硬编码公网 IP",
     r"(?<![\d.])(?:[1-9]\d{0,2}\.){3}[1-9]\d{0,2}(?![\d.])"),
]

def is_internal_ip(ip: str) -> bool:
    """环回 / 私有 / 保留地址不算泄露（文档与 service 里会正常出现）。"""
    try:
        a, b, c, d = (int(x) for x in ip.split("."))
    except Exception:
        return True
    if a in (0, 10, 127, 255) or a >= 224:
        return True
    if a == 192 and b == 168:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 169 and b == 254:
        return True
    return False

def mask(value: str) -> str:
    v = value.strip()
    return (v[:4] + "***(已脱敏)") if len(v) > 6 else "***(已脱敏)"

findings = []
for f in files:
    try:
        text = (ROOT / f).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue                                   # 二进制文件跳过
    for category, pattern in PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            value = m.group(0)
            if category == "硬编码公网 IP" and is_internal_ip(value):
                continue
            line = text.count("\n", 0, m.start()) + 1
            findings.append((f, line, category, mask(value)))

print(f"[check-secrets] 扫描 {len(files)} 个将入库文件")
if findings:
    print(f"[check-secrets] ❌ 发现 {len(findings)} 处疑似凭据，禁止提交/推送：\n")
    for f, line, category, masked in findings:
        print(f"  {f}:{line}  [{category}]  {masked}")
    print("\n  处理：把真实值改成本地环境变量或 config.local.yaml（已被 gitignore），")
    print("        仓库内文件只保留占位符 / 空对象 {}。改完重跑本脚本。")
    sys.exit(1)

print("[check-secrets] ✅ 未发现 token / 密码 / API Key / 凭证 / 公网 IP")
print("[check-secrets] 凭据注入规则见 AGENTS.md §7：一律走环境变量或 AstrBot WebUI。")
PY
