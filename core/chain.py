"""可插拔链路编排。

设计目标（对应「可复制可选链路」）：
- 每个能力是独立 Skill，config 里一个开关，关掉不影响其他环节；
- capabilities 顺序 = 能力自检顺序（逐个证明可用）；
- pipeline = 一次完整「巡游」组合，用同一批 Skill 串成真实会话流；
- 任一环节失败只标记该环节，不拖垮整条链路；
- ctx 可带 keyword / refresh / rid，让「刷刷雨落」「再刷刷其他的」真的换内容。
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from .gateway import Gateway
from .models import Segment
from .persona import closing, reply


@dataclass
class StepTrace:
    name: str
    ok: bool
    ms: int
    segments: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    note: str = ""


class Chain:
    def __init__(self, config: dict, skills: dict, gateway: Gateway):
        self.config = config
        self.skills = skills  # name -> Skill 实例
        self.gateway = gateway
        self.order: list[str] = config.get("capabilities", [])
        self.traces: list[StepTrace] = []

    async def _emit(self, seg: Segment, channel: str = "c2c") -> dict:
        return await self.gateway.send(seg, channel)

    async def run_capability(self, name: str, ctx: dict) -> StepTrace:
        """单独验证一个能力：产出该能力的消息段并发到收件箱。"""
        t0 = time.time()
        sk = self.skills.get(name)
        if sk is None or not sk.enabled:
            return StepTrace(name, False, 0, note="未启用 / 未注册（可选链路跳过）")
        try:
            res = await sk.run(ctx)
            sent = []
            for seg in res.segments:
                sent.append(seg.brief())
                await self._emit(seg)
            # chat 自身已产出人设文本，其余能力附一条人设旁白，模拟「会说话」
            if name != "chat":
                await self._emit(Segment("text", reply(name, **(res.data or {}))))
            return StepTrace(
                name, True, int((time.time() - t0) * 1000),
                segments=sent, artifacts=res.artifacts, note=res.note,
            )
        except Exception as e:  # noqa: BLE001 - 单环节失败不阻断链路
            return StepTrace(
                name, False, int((time.time() - t0) * 1000),
                note=f"{type(e).__name__}: {e}",
            )

    async def run_all(self, ctx: dict | None = None):
        ctx = ctx or {}
        for name in self.order:
            tr = await self.run_capability(name, ctx)
            self.traces.append(tr)
            ctx[f"_last_{name}"] = tr
        return self.traces

    async def run_pipeline(self, ctx: dict | None = None):
        """一次完整巡游：现刷B站 → 截图 → 语音 → 评论草稿 → 收尾文本。

        ctx 支持 keyword / refresh / rid，决定这一批刷什么、要不要换一批。
        所有下游能力共用同一个 batch_id，保证图片/语音/草稿都是这一批的。
        """
        ctx = ctx or {}
        flow: list[dict[str, Any]] = []
        t0 = time.time()
        meta: dict = {}

        # 1. 刷 B 站（真实取数，带轮换/搜索/去重）
        if self.skills["bilibili"].enabled:
            r = await self.skills["bilibili"].run(ctx)
            ctx["videos"] = r.data.get("videos", [])
            ctx["comments"] = r.data.get("comments", [])
            ctx["comments_aid"] = r.data.get("comments_aid", 0)
            meta = r.data.get("meta", {})
            ctx["meta"] = meta
            ctx["batch_id"] = meta.get("batch_id", "")
            await self._emit(Segment(
                "text", reply("bilibili", titles=[v["title"] for v in ctx["videos"]], meta=meta)
            ))
            flow.append({"step": "刷B站", "count": len(ctx["videos"]),
                         "source": meta.get("source_label"), "batch": meta.get("batch"),
                         "artifacts": r.artifacts})

        # 1.5 读片：读第一条视频的简介 / 热门评论，并总结输出
        digest_data = None
        digest_sk = self.skills.get("digest")
        if digest_sk and digest_sk.enabled and ctx.get("videos"):
            try:
                r = await digest_sk.run(ctx)
                digest_data = r.data.get("digest")
                ctx["digest"] = digest_data
                for seg in r.segments:
                    await self._emit(seg)
                flow.append({"step": "读片总结", "note": r.note, "artifacts": r.artifacts})
            except Exception as e:  # noqa: BLE001 - 读片失败不拖垮巡游
                flow.append({"step": "读片总结", "note": f"失败降级: {type(e).__name__}"})

        # 用本批真实数据算好评论草稿，让截图卡片一起渲染出来
        if self.skills["comment"].enabled:
            ctx["draft"] = self.skills["comment"]._draft(ctx)

        # 2. 截图发图片（有读片数据 → 读片报告卡片；否则巡游清单卡片）
        if self.skills["screenshot"].enabled:
            r = await self.skills["screenshot"].run(ctx)
            for seg in r.segments:
                await self._emit(seg)
            flow.append({"step": "截图发图片", "artifacts": r.artifacts})

        # 3. 发语音（优先念读片总结，没有则念本批清单结论）
        if self.skills["voice"].enabled:
            if digest_data and digest_data.get("summary"):
                ctx["speak_text"] = str(digest_data["summary"])[:110]
            else:
                v0 = (ctx.get("videos") or [{}])[0]
                ctx["speak_text"] = (
                    f"咕噜，本鱼{meta.get('fetched_at', '刚刚')}从"
                    f"{meta.get('source_label', 'B站')}现刷了{len(ctx.get('videos', []))}条，"
                    f"第一条是「{str(v0.get('title', '白饭'))[:14]}」，"
                    f"播放{v0.get('view', 0)}。这是第{meta.get('batch', 0)}批。"
                )
            r = await self.skills["voice"].run(ctx)
            for seg in r.segments:
                await self._emit(seg)
            flow.append({"step": "发语音", "artifacts": r.artifacts})

        # 4. 发评论（默认只出草稿，不真发）
        if self.skills["comment"].enabled:
            r = await self.skills["comment"].run(ctx)
            for seg in r.segments:
                await self._emit(seg)
            flow.append({"step": "发评论", "note": r.note, "artifacts": r.artifacts})

        # 5. 收尾文本（带批次号，证明是这一批的）
        await self._emit(Segment("text", closing(meta)))
        return {"flow": flow, "ms": int((time.time() - t0) * 1000), "meta": meta}
