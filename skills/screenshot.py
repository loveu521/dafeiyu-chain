"""能力：发图片 —— 按用户要求，图片来自「截图」而非生图。

开源依赖：Playwright + Chromium。
思路参考 HarukaBot（B站动态渲染截图）与 openclaw-onebot 的 rendering pipeline：
把结构化数据渲染成 HTML，再用无头浏览器截图成 PNG → Segment(image)。

卡片上明确印出「抓取时间 / 数据来源 / 页码 / 批次号」，让每次现刷肉眼可辨；
产物带批次号，避免 QQ 官机按内容 hash 命中旧缓存导致「永远是那一张」。
安全：screenshot_url 模式带域名白名单，禁止访问内网 / 云元数据地址。
"""
from __future__ import annotations

import asyncio
import html
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .base import Skill, SkillResult
from core.models import Segment

CARD_TPL = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#08263f,#12436b);
 font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;color:#eaf6ff}
.wrap{padding:34px 38px}.head{display:flex;align-items:center;gap:18px}
.fish{font-size:70px;line-height:1}h1{font-size:30px;margin:0 0 6px}
.sub{color:#8fc4e8;font-size:15px}
.meta{color:#ffd98a;font-size:14px;margin-top:4px}
.tag{display:inline-block;background:#1e6f9f;padding:4px 13px;border-radius:14px;
 font-size:13px;margin-right:8px}
.list{margin-top:26px}.item{background:rgba(255,255,255,.07);border-left:4px solid #4bb3e6;
 border-radius:8px;padding:14px 18px;margin-bottom:12px}
.title{font-size:19px;font-weight:600}.stat{color:#9fd0ee;font-size:14px;margin-top:5px}
.foot{margin-top:22px;color:#7fb4d8;font-size:14px}
.cmt{margin-top:8px;color:#cfe9fa;font-size:14px;font-style:italic}
</style></head><body><div class="wrap">
<div class="head"><div class="fish">🐟</div><div>
<h1>蓝色大肥鱼 · 巡游报告</h1><div class="sub">B 站现刷速览 / 白饭已就位</div>
<div class="meta">{meta_line}</div>
</div></div>
<div style="margin-top:18px"><span class="tag">QQ 官方机器人</span>
<span class="tag">截图发送</span><span class="tag">Playwright</span></div>
<div class="list">{items}</div>
<div class="foot">咕噜……本鱼只负责看，评论先给主人过目。 —— 大肥鱼 · {batch_tag}</div>
</div></body></html>"""

ITEM_TPL = """<div class="item"><div class="title">{i}. {title}</div>
<div class="stat">UP {owner} · 播放 {view} · 评论 {reply} · {tname}</div>
{cmt}</div>"""

# 读片报告卡片：标题 / 简介 / 热门评论 / 总结，全部来自真实接口数据
DIGEST_CARD_TPL = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#08263f,#12436b);
 font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;color:#eaf6ff}
.wrap{padding:34px 38px}.head{display:flex;align-items:center;gap:18px}
.fish{font-size:70px;line-height:1}h1{font-size:30px;margin:0 0 6px}
.sub{color:#8fc4e8;font-size:15px}
.meta{color:#ffd98a;font-size:14px;margin-top:4px}
.tag{display:inline-block;background:#1e6f9f;padding:4px 13px;border-radius:14px;
 font-size:13px;margin-right:8px}
.vtitle{font-size:24px;font-weight:700;margin:22px 0 6px;line-height:1.4}
.vstat{color:#9fd0ee;font-size:14px;margin-bottom:18px}
.sec{margin-top:18px}.lbl{color:#ffd98a;font-size:15px;font-weight:600;margin-bottom:8px}
.desc{background:rgba(255,255,255,.07);border-left:4px solid #4bb3e6;border-radius:8px;
 padding:14px 18px;font-size:16px;line-height:1.7;white-space:pre-wrap;word-break:break-all}
.cmt{background:rgba(255,255,255,.07);border-radius:8px;padding:11px 16px;
 margin-bottom:9px;font-size:15px;line-height:1.55}
.cmt .like{color:#ffb35c;font-size:13px;margin-left:8px}
.cmt .who{color:#8fc4e8;font-size:13px;margin-right:8px}
.sum{background:linear-gradient(135deg,#1e6f9f,#2b8fc4);border-radius:10px;
 padding:18px 20px;font-size:17px;line-height:1.7;margin-top:8px}
.foot{margin-top:22px;color:#7fb4d8;font-size:14px}
</style></head><body><div class="wrap">
<div class="head"><div class="fish">🐟</div><div>
<h1>蓝色大肥鱼 · 读片报告</h1><div class="sub">标题 / 简介 / 热门评论 / 一句话总结</div>
<div class="meta">{meta_line}</div>
</div></div>
<div style="margin-top:18px"><span class="tag">bilibili-api</span>
<span class="tag">热评按赞排序</span><span class="tag">Playwright 截图</span></div>
<div class="vtitle">{title}</div>
<div class="vstat">UP {owner} · {tname} · 播放 {view} · 点赞 {like} · 评论 {reply}{dur}{pub}</div>
<div class="sec"><div class="lbl">简介</div><div class="desc">{desc}</div></div>
<div class="sec"><div class="lbl">热门评论（按点赞数）</div>{cmts}</div>
<div class="sec"><div class="lbl">本鱼的总结 · {mode}</div><div class="sum">{summary}</div></div>
<div class="foot">咕噜……材料都是现读的，评论只给主人过目，本鱼不乱发。 — {batch_tag}</div>
</div></body></html>"""

CMT_TPL = """<div class="cmt"><span class="who">{who}</span>{text}<span class="like">{like} 赞</span></div>"""


class ScreenshotSkill(Skill):
    name = "screenshot"

    def _render_html(self, ctx: dict, batch_tag: str) -> str:
        videos = ctx.get("videos") or []
        if not videos:
            videos = [{"title": "（还没去刷，本鱼先打个卡）", "owner": "-", "view": 0,
                       "reply": 0, "tname": "待巡游"}]
        meta = ctx.get("meta") or {}
        bits = []
        if meta.get("fetched_at"):
            bits.append(f"现刷于 {meta['fetched_at']}")
        if meta.get("source_label"):
            bits.append(str(meta["source_label"]))
        if meta.get("batch"):
            bits.append(f"第 {meta['batch']} 批")
        if meta.get("deduplicated"):
            bits.append("已跳过发过的")
        meta_line = " · ".join(bits) or f"本地生成 {datetime.now():%Y-%m-%d %H:%M:%S}"

        items = []
        for i, v in enumerate(videos[:5], 1):
            cmt = ""
            if i == 1 and ctx.get("draft"):
                cmt = f'<div class="cmt">拟评论：{html.escape(ctx["draft"])}</div>'
            items.append(ITEM_TPL.format(
                i=i, title=html.escape(str(v.get("title", ""))[:40]),
                owner=html.escape(str(v.get("owner", "-"))),
                view=v.get("view", 0), reply=v.get("reply", 0),
                tname=html.escape(str(v.get("tname", ""))), cmt=cmt,
            ))
        # CSS 里有大量花括号，不能用 str.format（会被当成占位符）
        return (CARD_TPL.replace("{items}", "".join(items))
                        .replace("{meta_line}", html.escape(meta_line))
                        .replace("{batch_tag}", html.escape(batch_tag)))

    def _render_digest_html(self, ctx: dict, batch_tag: str) -> str:
        """读片报告：把简介 / 热评 / 总结渲染成一张卡片。"""
        d = ctx.get("digest") or {}
        esc = lambda x: html.escape(str(x if x is not None else ""))  # noqa: E731
        meta = ctx.get("meta") or {}
        bits = []
        if d.get("fetched_at"):
            bits.append(f"现读于 {d['fetched_at']}")
        if d.get("bvid"):
            bits.append(str(d["bvid"]))
        if meta.get("source_label"):
            bits.append(str(meta["source_label"]))
        bits.append(f"第 {d.get('index', 1)} 条")
        meta_line = " · ".join(bits) or f"本地生成 {datetime.now():%Y-%m-%d %H:%M:%S}"

        cmts = "".join(
            CMT_TPL.replace("{who}", esc(c.get("user") or "匿名"))
                   .replace("{text}", esc(c.get("text")))
                   .replace("{like}", str(c.get("like", 0)))
            for c in (d.get("hot_comments") or [])
        ) or '<div class="cmt">（评论区这会儿没刷出来）</div>'

        mode = "LLM 归纳" if d.get("summary_mode") == "llm" else "本地摘要"
        dur = f" · 时长 {esc(d['duration'])}" if d.get("duration") else ""
        pub = f" · {esc(d['pubdate'])}" if d.get("pubdate") else ""

        replacements = {
            "{meta_line}": esc(meta_line), "{title}": esc(d.get("title") or "（没读到标题）"),
            "{owner}": esc(d.get("owner") or "-"), "{tname}": esc(d.get("tname") or "视频"),
            "{view}": str(d.get("view", 0)), "{like}": str(d.get("like", 0)),
            "{reply}": str(d.get("reply", 0)), "{dur}": dur, "{pub}": pub,
            "{desc}": esc(d.get("desc") or "（UP 主没写简介）"),
            "{cmts}": cmts, "{mode}": mode,
            "{summary}": esc(d.get("summary") or "（本鱼没总结出话来）"),
            "{batch_tag}": esc(batch_tag),
        }
        out = DIGEST_CARD_TPL
        for k, v in replacements.items():
            out = out.replace(k, v)
        return out

    def _chromium_path(self) -> str | None:
        """浏览器路径：配置/环境变量优先 → 系统 chromium → Playwright 自带。"""
        import os

        configured = self.cfg.get("chromium_path") or os.environ.get("DFY_CHROMIUM")
        if configured:
            return configured
        if Path("/usr/bin/chromium").exists():
            return "/usr/bin/chromium"
        return None

    def _shot_sync(self, page_source: str, out: Path, is_html: bool) -> None:
        from playwright.sync_api import sync_playwright

        launch: dict = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        exe = self._chromium_path()
        if exe:
            launch["executable_path"] = exe
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch)
            page = browser.new_page(
                viewport={"width": 900, "height": 620}, device_scale_factor=2,
            )
            if is_html:
                page.set_content(page_source, wait_until="networkidle")
            else:
                page.goto(page_source, wait_until="networkidle", timeout=20000)
            page.screenshot(path=str(out), full_page=True)
            browser.close()

    async def run(self, ctx: dict) -> SkillResult:
        mode = self.cfg.get("mode", "html_card")
        tag = ctx.get("batch_id") or (ctx.get("meta") or {}).get("batch_id") \
            or datetime.now().strftime("%m%d%H%M%S")
        outdir = Path(self.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        is_digest = bool(ctx.get("digest"))
        stem = "read" if is_digest else "card"
        out = outdir / f"{stem}_{tag}.png"

        if mode == "url":
            url = self.cfg.get("url", "")
            allowed = set(self.cfg.get("url_allowlist", []))
            host = urlparse(url).hostname or ""
            if not url or host not in allowed:
                raise ValueError(f"URL 不在白名单内，拒绝截图: {url!r}")
            await asyncio.to_thread(self._shot_sync, url, out, False)
            note = f"网页截图 {host}"
            artifacts = [str(out)]
        else:
            html_src = (
                self._render_digest_html(ctx, tag) if is_digest
                else self._render_html(ctx, tag)
            )
            html_out = outdir / f"{stem}_{tag}.html"
            html_out.write_text(html_src, encoding="utf-8")
            shutil.copyfile(html_out, outdir / f"{stem}.html")
            await asyncio.to_thread(self._shot_sync, html_src, out, True)
            note = (
                f"读片报告（简介/热评/总结）Playwright 截图（批次 {tag}）"
                if is_digest else
                f"HTML 渲染后 Playwright 截图（批次 {tag}，非生图）"
            )
            artifacts = [str(out), str(html_out)]

        # 固定别名（最新一次），兼容 run_local 验收与人工查看
        shutil.copyfile(out, outdir / f"{stem}.png")

        seg = Segment(
            "image", file=str(out),
            meta={"format": "png", "mode": mode, "card": stem,
                  "bytes": out.stat().st_size, "batch_id": tag},
        )
        return SkillResult(
            segments=[seg], artifacts=artifacts, note=note,
            data={"batch_id": tag},
        )
