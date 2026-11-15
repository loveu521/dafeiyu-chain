"""能力：刷 B 站（真·现刷）。

支持四种「每次都不一样」的现刷方式，全部只读接口、不写任何账号操作：

- 热门榜翻页（pn 1..N，每批不同内容）
- 全站 / 分区排行榜
- 关键词搜索（用户说「刷刷 up 主雨落发的视频」→ 真的去搜「雨落」）
- 最近发过的视频去重（用户说「再刷刷其他的」→ 真的换一批）

每次抓取都会落盘 bilibili.json，带批次号 / 抓取时间 / 数据来源 / 页码 / 关键词，
让「现刷」在文本、截图、语音里都看得见，而不是永远那三条。

开源依赖：bilibili-api-python（评论懒加载接口，GPLv3）+ aiohttp。
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import aiohttp

from .base import Skill, SkillResult

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

# 轮换计划：连续问「刷b站」时，每次自动前进一格，绝不老是同一批。
# 只列实测稳定的热门榜分页（ranking/v2 对部分服务器 IP 会返回 -352 风控，
# 因此只在用户明确说「排行榜」时才单独请求，失败自动降级到热门页）。
SOURCE_PLAN = [
    ("popular", 1), ("popular", 2), ("popular", 3),
    ("popular", 4), ("popular", 5),
]

# 关键词里出现这些分区词时，走分区排行榜（无结果会自动降级到热门榜）
RID_BY_WORD = {
    "动画": 1, "番剧": 1, "音乐": 3, "舞蹈": 129, "游戏": 4,
    "知识": 36, "科技": 188, "数码": 188, "生活": 160, "美食": 211,
    "鬼畜": 119, "时尚": 155, "娱乐": 5, "影视": 181, "纪录片": 177,
}


class BilibiliSkill(Skill):
    name = "bilibili"

    # ------------------------------------------------------------------
    # 状态：轮换游标 + 最近发过的 aid（保证「再刷刷其他的」真的换一批）
    # ------------------------------------------------------------------
    def _state_path(self) -> Path:
        return Path(self.outdir) / "feed_state.json"

    def _load_state(self) -> dict:
        p = self._state_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        return {"cursor": 0, "search_page": 1, "seen": [], "batch": 0}

    def _save_state(self, st: dict) -> None:
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # 取数
    # ------------------------------------------------------------------
    async def _get_json(self, url: str, params: dict | None = None) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url, params=params, headers=UA,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return await r.json()

    @staticmethod
    def _norm(v: dict) -> dict:
        """统一 popular / ranking / search 三种返回结构。"""
        stat = v.get("stat") or {}
        owner = v.get("owner") if isinstance(v.get("owner"), dict) else {}
        title = re.sub(r"<[^>]+>", "", html.unescape(v.get("title") or "")).strip()
        pic = v.get("pic") or ""
        if pic.startswith("//"):
            pic = "https:" + pic

        def num(*keys: str) -> int:
            for k in keys:
                val = v.get(k)
                if val is None:
                    val = stat.get(k)
                if val is not None:
                    try:
                        return int(val)
                    except (TypeError, ValueError):
                        pass
            return 0

        try:
            aid = int(v.get("aid") or v.get("id") or 0)
        except (TypeError, ValueError):
            aid = 0
        return {
            "aid": aid,
            "bvid": v.get("bvid") or "",
            "title": title,
            "owner": v.get("author") or owner.get("name") or "-",
            "tname": v.get("tname") or v.get("typename") or "",
            "pic": pic,
            "view": num("play", "view"),
            "reply": num("review", "reply"),
            "like": num("like"),
        }

    async def _fetch_popular(self, pn: int) -> list[dict]:
        j = await self._get_json(
            "https://api.bilibili.com/x/web-interface/popular",
            {"ps": 20, "pn": pn},
        )
        if j.get("code") != 0:
            raise RuntimeError(f"热门接口 code={j.get('code')}: {j.get('message')}")
        return [self._norm(v) for v in (j["data"]["list"] or [])]

    async def _fetch_ranking(self, rid: int) -> list[dict]:
        j = await self._get_json(
            "https://api.bilibili.com/x/web-interface/ranking/v2",
            {"rid": rid, "type": "all"},
        )
        if j.get("code") != 0:
            raise RuntimeError(f"排行榜接口 code={j.get('code')}: {j.get('message')}")
        return [self._norm(v) for v in ((j.get("data") or {}).get("list") or [])]

    async def _fetch_search(self, keyword: str, page: int) -> list[dict]:
        j = await self._get_json(
            "https://api.bilibili.com/x/web-interface/search/type",
            {"search_type": "video", "keyword": keyword, "page": page},
        )
        if j.get("code") != 0:
            raise RuntimeError(f"搜索接口 code={j.get('code')}: {j.get('message')}")
        return [self._norm(v) for v in ((j.get("data") or {}).get("result") or [])]

    async def _fetch_comments(self, aid: int, n: int) -> list[dict]:
        """热门评论（按点赞降序），委托给 digest 能力，避免两处各写一套取数。"""
        from .digest import DigestSkill

        return await DigestSkill({}, self.outdir).fetch_hot_comments(aid, n)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    async def run(self, ctx: dict) -> SkillResult:
        cfg = self.cfg
        limit = int(cfg.get("limit", 3))
        dedup = bool(cfg.get("dedup", True))
        fixed_source = cfg.get("source", "auto")
        keyword = (ctx.get("keyword") or "").strip()
        refresh = bool(ctx.get("refresh"))
        rid = ctx.get("rid")

        st = self._load_state()
        batch = int(st.get("batch", 0)) + 1
        st["batch"] = batch
        now = datetime.now()
        batch_id = f"{now:%m%d%H%M%S}-{batch}"

        # --- 决定本批来源 -------------------------------------------------
        if keyword:
            page = int(st.get("search_page", 1))
            if refresh:
                page = page % 5 + 1
            st["search_page"] = page % 5 + 1
            source, arg = "search", keyword
            label = f"关键词搜索「{keyword}」· 第 {page} 页"
        else:
            cursor = int(st.get("cursor", 0))
            if ctx.get("ranking") or fixed_source == "ranking":
                # 用户明确要看排行榜时才请求（该接口偶发 -352，失败会降级）
                src, arg = "ranking", int(rid or 0)
            elif fixed_source == "popular":
                src, arg = "popular", (cursor % 5) + 1
            else:  # auto：热门榜分页轮换
                src, arg = SOURCE_PLAN[cursor % len(SOURCE_PLAN)]
            cursor += 1
            if refresh:
                cursor += 1  # 「换一批」额外跳过一格
            st["cursor"] = cursor
            source = src
            label = (
                f"B站热门榜 · 第 {arg} 页" if src == "popular"
                else ("B站全站排行榜" if arg == 0 else f"B站排行榜 · 分区 {arg}")
            )

        # --- 真实取数（偶发风控自动重试 → 换入口 → 空手兜底）--------------
        label_extra: list[str] = []

        async def _pull() -> list[dict]:
            if source == "search":
                return await self._fetch_search(arg, int(st.get("search_page", 1)))
            if source == "ranking":
                data = await self._fetch_ranking(int(arg))
                if not data and int(arg) != 0:
                    data = await self._fetch_ranking(0)
                    label_extra.append("该分区没数据，换全站榜")
                return data
            return await self._fetch_popular(int(arg))

        try:
            pool = await _pull()
        except Exception:  # noqa: BLE001
            await asyncio.sleep(0.8)
            try:
                pool = await _pull()
                label_extra.append("刚卡了一下，重试成功")
            except Exception:  # noqa: BLE001
                fallback = (int(st.get("cursor", 0)) % 5) + 1
                try:
                    pool = await self._fetch_popular(fallback)
                    label = f"B站热门榜 · 第 {fallback} 页"
                    label_extra.append("排行榜没响应，改刷热门")
                except Exception:  # noqa: BLE001
                    pool = []
                    label_extra.append("B站暂时没响应，本鱼空手回来")
        if label_extra:
            label = f"{label}（{'、'.join(label_extra)}）"

        # --- 去重：排除最近发过的 ------------------------------------------
        seen = [int(x) for x in st.get("seen", [])]
        seen_set = set(seen)
        fresh = [v for v in pool if v["aid"] and (not dedup or v["aid"] not in seen_set)]
        if not fresh and pool:
            # 这一批全发过了：自动再翻一页拿新的
            try:
                nxt = (int(arg) + 1) if source == "popular" else 1
                pool2 = (
                    await self._fetch_popular(nxt) if source == "popular"
                    else await self._fetch_search(arg, (int(st.get("search_page", 1)) % 5) + 1)
                    if source == "search" else await self._fetch_ranking(0)
                )
                fresh = [v for v in pool2 if v["aid"] and v["aid"] not in seen_set]
                if fresh:
                    label += "（本页已发过，自动翻页）"
            except Exception:  # noqa: BLE001
                pass
        chosen = (fresh or pool)[:limit]
        dedup_hit = len(pool) - len(fresh) if fresh else len(pool)

        st["seen"] = ([v["aid"] for v in chosen] + seen)[:80]
        self._save_state(st)

        comments_aid = chosen[0]["aid"] if chosen else 0
        comments = await self._fetch_comments(comments_aid, 3) if comments_aid else []
        meta = {
            "batch": batch,
            "batch_id": batch_id,
            "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "source_label": label,
            "keyword": keyword,
            "page": arg,
            "pool_size": len(pool),
            "dedup_hit": dedup_hit,
            "deduplicated": bool(fresh),
        }

        out = Path(self.outdir) / "bilibili.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"meta": meta, "videos": chosen, "top_comments": comments},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 留一份带批次号的归档，方便逐批回放
        shutil.copyfile(out, Path(self.outdir) / f"bilibili_{batch_id}.json")

        return SkillResult(
            artifacts=[str(out)],
            data={"videos": chosen, "comments": comments,
                  "comments_aid": comments_aid, "meta": meta},
            note=f"{label} · 第{batch}批 · 现刷 {len(chosen)} 条 + 热评 {len(comments)} 条",
        )
