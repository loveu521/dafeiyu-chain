"""可插拔能力集合。新增能力只需继承 Skill 并在 build_skills 注册。"""
from skills.chat import ChatSkill
from skills.voice import VoiceSkill
from skills.screenshot import ScreenshotSkill
from skills.bilibili import BilibiliSkill
from skills.comment import CommentSkill
from skills.digest import DigestSkill

REGISTRY = {
    "chat": ChatSkill,
    "voice": VoiceSkill,
    "screenshot": ScreenshotSkill,
    "bilibili": BilibiliSkill,
    "digest": DigestSkill,
    "comment": CommentSkill,
}


def build_skills(config: dict, outdir: str) -> dict:
    cfg = config.get("skills", {})
    return {
        name: cls(cfg.get(name, {}), outdir)
        for name, cls in REGISTRY.items()
    }
