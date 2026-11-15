"""能力 0：养大肥鱼（基座）。

即「给 AI 一个人设 + 一个会说话的壳」。本地用 persona.py 的模板；
服务器阶段由 AstrBot 的 PersonaManager / LLM Provider 接管，
本 Skill 只负责产出一条符合人设的文本消息，保证链路第一步可验证。
"""
from __future__ import annotations

from core.models import Segment
from core.persona import PERSONA, reply

from .base import Skill, SkillResult


class ChatSkill(Skill):
    name = "chat"

    async def run(self, ctx: dict) -> SkillResult:  # noqa: ARG002
        return SkillResult(
            segments=[Segment("text", reply("chat"), meta={"persona": "大肥鱼"})],
            data={"persona_chars": len(PERSONA)},
            note="人设已加载，可对话（本地模板 / 服务器接 LLM）",
        )
