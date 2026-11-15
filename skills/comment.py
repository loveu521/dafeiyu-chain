"""能力：发评论。

开源依赖：bilibili-api-python 的 comment.send_comment（需 Credential）。
默认 dry_run=True：只生成草稿并落盘，绝不真发。理由：
  1. 真发需要 SESSDATA/bili_jct/buvid3 等登录凭证，本地阶段没有；
  2. 自动留言受平台规则约束，社区共识是「先拟好内容给主人确认再发」。
只有显式 allow_publish=True 且拿到完整凭证才会调用真实接口，
并且带每日上限与内容白名单检查。

安全约定（AGENTS.md §7）：仓库里的 config.yaml / config.example.yaml 中
`credential` 永远是空对象 {}。真实凭证只从环境变量注入
（BILI_SESSDATA / BILI_JCT / BILI_BUVID3 / BILI_DEDEUSERID），
可由 systemd 的 EnvironmentFile 从一个被 gitignore 的本地文件加载。
绝不把真实值写进任何仓库内文件。
"""
from __future__ import annotations

import json
import random
import shutil
from datetime import datetime
from pathlib import Path

from .base import Skill, SkillResult
from core.models import Segment

BANNED = ["密码", "api key", "身份证", "手机号", "微信号"]

# 每次换一句，避免草稿永远是同一句
DRAFT_TPL = [
    "这条「{t}」有点意思，本鱼路过留个爪～",
    "刷到「{t}」，咕噜，白饭都差点忘了吃。",
    "「{t}」这播放量，本鱼看得鱼鳍都抖了。",
    "本鱼今天在「{t}」底下冒个泡，不吵不闹。",
    "看完了，「{t}」值得一句：有点东西。",
]


class CommentSkill(Skill):
    name = "comment"

    @staticmethod
    def _credential(cfg: dict) -> dict:
        """仓库配置只留空占位，真实凭证一律从环境变量读取（不落盘、不入库）。"""
        import os

        cred = dict(cfg.get("credential") or {})
        for key, env in (
            ("sessdata", "BILI_SESSDATA"),
            ("bili_jct", "BILI_JCT"),
            ("buvid3", "BILI_BUVID3"),
            ("dedeuserid", "BILI_DEDEUSERID"),
        ):
            if os.environ.get(env):
                cred[key] = os.environ[env]
        return cred

    def _draft(self, ctx: dict) -> str:
        videos = ctx.get("videos") or []
        if not videos:
            return "咕噜，先巡游再评论，本鱼不瞎说。"
        t = str(videos[0].get("title", ""))[:20]
        return random.choice(DRAFT_TPL).format(t=t)

    async def run(self, ctx: dict) -> SkillResult:
        draft = ctx.get("draft") or self._draft(ctx)
        videos = ctx.get("videos") or []
        aid = videos[0]["aid"] if videos else 0
        dry_run = bool(self.cfg.get("dry_run", True))
        allow = bool(self.cfg.get("allow_publish", False))
        cred = self._credential(self.cfg)
        daily_limit = int(self.cfg.get("daily_limit", 3))
        tag = ctx.get("batch_id") or datetime.now().strftime("%m%d%H%M%S")

        lowered = draft.lower()
        blocked = [w for w in BANNED if w in lowered]
        result = {
            "aid": aid, "draft": draft, "dry_run": dry_run,
            "blocked_words": blocked, "daily_limit": daily_limit,
            "published": False, "reason": "", "batch_id": tag,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if blocked:
            result["reason"] = "命中隐私词，拒绝发送"
        elif dry_run or not allow:
            result["reason"] = "dry_run / 未显式授权，仅生成草稿"
        elif not all(cred.get(k) for k in ("sessdata", "bili_jct", "buvid3")):
            result["reason"] = "缺少登录凭证，拒绝发送"
        else:
            # 真实发送路径（服务器阶段才会走到这里）
            from bilibili_api import comment as bili_comment
            from bilibili_api.utils.network import Credential

            credential = Credential(
                sessdata=cred["sessdata"], bili_jct=cred["bili_jct"],
                buvid3=cred["buvid3"], dedeuserid=cred.get("dedeuserid", ""),
            )
            ret = await bili_comment.send_comment(
                text=draft, oid=aid,
                type_=bili_comment.CommentResourceType.VIDEO,
                credential=credential,
            )
            result["published"] = True
            result["reason"] = "已真实发送"
            result["api_return"] = ret

        outdir = Path(self.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        out = outdir / f"comment_draft_{tag}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copyfile(out, outdir / "comment_draft.json")

        seg = Segment(
            "text", f"[评论草稿·{tag}] {draft}\n状态：{result['reason']}",
            meta={"published": result["published"], "batch_id": tag},
        )
        return SkillResult(
            segments=[seg], artifacts=[str(out)],
            data={"draft": draft, "published": result["published"], "batch_id": tag},
            note=result["reason"],
        )
