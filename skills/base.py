"""Skill 基类：所有能力都实现同样的 run(ctx) -> SkillResult 接口。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models import Segment


@dataclass
class SkillResult:
    segments: list[Segment] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    note: str = ""


class Skill:
    name = "base"
    enabled = True

    def __init__(self, cfg: dict | None = None, outdir: str = "output"):
        self.cfg = cfg or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.outdir = outdir

    async def run(self, ctx: dict) -> SkillResult:  # noqa: ARG002
        raise NotImplementedError
