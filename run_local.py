#!/usr/bin/env python3.11
"""本地一键跑通完整链路（阶段一）。

不依赖 QQ 账号 / AppID / 域名 / 登录凭证：
用 MockGateway 等价「QQ 官方机器人收件箱」，所有能力真实执行、产物落盘。

    python3.11 run_local.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.chain import Chain  # noqa: E402
from core.gateway import AstrBotGateway, MockGateway  # noqa: E402
from skills import build_skills  # noqa: E402


def _table(traces) -> str:
    lines = ["| 环节 | 结果 | 耗时 | 产物 | 说明 |", "|---|---|---|---|---|"]
    for t in traces:
        arts = ", ".join(Path(a).name for a in t.artifacts) or "—"
        segs = " / ".join(s[:34] for s in t.segments) or "—"
        lines.append(
            f"| {t.name} | {'✅' if t.ok else '⏭️/❌'} | {t.ms}ms | {arts or segs} | {t.note} |"
        )
    return "\n".join(lines)


async def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    outdir = ROOT / cfg.get("outdir", "output")
    outdir.mkdir(parents=True, exist_ok=True)

    gateway = (
        AstrBotGateway() if cfg.get("gateway") == "astrbot" else MockGateway(outdir)
    )
    skills = build_skills(cfg, str(outdir))
    chain = Chain(cfg, skills, gateway)

    print(f"[链路] 网关={gateway.name}  能力顺序={' → '.join(chain.order)}")
    print("[链路] ① 逐能力自检（每个可独立开关）")
    traces = await chain.run_all()
    for t in traces:
        flag = "OK " if t.ok else "SKIP/FAIL"
        print(f"   [{flag}] {t.name:10s} {t.ms:>5}ms  {t.note}")

    print("[链路] ② 完整巡游组合（刷B站 → 截图 → 语音 → 评论）")
    pipeline = await chain.run_pipeline()
    for f in pipeline["flow"]:
        print(f"   · {f['step']}: {f.get('note') or f.get('count') or ''}")

    # ---------- 验收报告 ----------
    inbox = outdir / "inbox.jsonl"
    records = [json.loads(x) for x in inbox.read_text(encoding="utf-8").splitlines() if x.strip()]
    kinds = {}
    for r in records:
        kinds[r["segment"]] = kinds.get(r["segment"], 0) + 1

    report = {
        "stage": "阶段一 · 本地跑通",
        "gateway": gateway.name,
        "capabilities": [
            {"name": t.name, "ok": t.ok, "ms": t.ms,
             "artifacts": t.artifacts, "note": t.note}
            for t in traces
        ],
        "pipeline": pipeline,
        "inbox_total": len(records),
        "inbox_by_kind": kinds,
        "artifacts": sorted(str(p.relative_to(ROOT)) for p in outdir.rglob("*") if p.is_file()),
    }
    (outdir / "run_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = f"""# 大肥鱼链路 · 阶段一本地跑通报告

> 网关：`{gateway.name}` ｜ 无需 QQ 账号 / AppID / 域名 / B站登录凭证

## 能力自检（可插拔，逐个独立验证）

{_table(traces)}

## 完整巡游组合

刷 B 站（真实取数）→ 渲染截图发图片 → 合成语音发语音条 → 生成评论草稿 → 收尾文本。
共耗时 **{pipeline['ms']}ms**。

## QQ 官机收件箱（inbox.jsonl）

共 **{len(records)}** 条消息，按类型：{json.dumps(kinds, ensure_ascii=False)}。
其中 `msg_type=7` 为富媒体（图片 file_type=1 / 语音 file_type=3），
`msg_type=0` 为文本 —— 与 QQ 官方机器人接口定义一致。

## 产物清单

{chr(10).join('- `' + a + '`' for a in report['artifacts'])}
"""
    (outdir / "REPORT.md").write_text(md, encoding="utf-8")

    print(f"\n[完成] 收件箱 {len(records)} 条：{json.dumps(kinds, ensure_ascii=False)}")
    print(f"[完成] 报告：{outdir / 'REPORT.md'}")
    return 0 if all(t.ok for t in traces) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
