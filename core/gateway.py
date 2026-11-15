"""网关抽象：本地 Mock 与 AstrBot QQ 官方机器人共用同一套 Segment。

QQ 官方机器人消息类型对照（bot.q.qq.com）：
  msg_type=0 文本；msg_type=7 富媒体（先上传拿 file_info 再发）。
  图片支持 png/jpg/gif/webp/bmp；语音支持 silk/mp3/wav/ogg（file_type=3）。
因此 edge-tts 产出的 mp3 可直接作为语音上传，无需转 silk。
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .models import Segment


class Gateway:
    name = "base"

    async def send(self, seg: Segment, channel: str = "c2c") -> dict:
        raise NotImplementedError


class MockGateway(Gateway):
    """等价「QQ 官机收件箱」：把要发出的消息按官机字段落盘，供本地验收。"""

    name = "mock(QQ官机收件箱)"

    def __init__(self, outdir: str | Path):
        self.outdir = Path(outdir)
        self.media = self.outdir / "media"
        self.media.mkdir(parents=True, exist_ok=True)
        self.inbox = self.outdir / "inbox.jsonl"
        self.inbox.write_text("", encoding="utf-8")
        self.seq = 0

    async def send(self, seg: Segment, channel: str = "c2c") -> dict:
        self.seq += 1
        rec: dict = {
            "seq": self.seq,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": channel,
            "msg_type": 0 if seg.kind == "text" else 7,
            "segment": seg.kind,
        }
        if seg.kind == "text":
            rec["content"] = seg.content
        else:
            src = Path(seg.file)
            dst = self.media / f"{self.seq:02d}_{src.name}"
            if src.exists():
                shutil.copy2(src, dst)
            rec["file_type"] = 1 if seg.kind == "image" else 3
            rec["file_info"] = f"<uploaded:{dst.name}>"
            rec["local_file"] = str(dst)
            rec["bytes"] = dst.stat().st_size if dst.exists() else 0
        rec.update(seg.meta)
        with self.inbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


class AstrBotGateway(Gateway):
    """服务器阶段：把 Segment 交给 AstrBot 的 qq_official 适配器。

    实际投递由 AstrBot 的 send_message / event 完成，这里只做转换，
    保证本地与服务器跑的是同一条链路、同一批产物。
    """

    name = "astrbot(QQ官方机器人)"

    def __init__(self, context=None):
        self.context = context

    async def send(self, seg: Segment, channel: str = "c2c") -> dict:
        comp = seg.to_astrbot_comp()
        return {"component": type(comp).__name__, "channel": channel}
