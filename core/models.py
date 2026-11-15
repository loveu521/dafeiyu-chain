"""链路中间表示：与 AstrBot 消息链组件一一对应。

本地跑通阶段不依赖 astrbot 包；to_astrbot_comp() 采用延迟导入，
只有真正落到 AstrBot 插件里执行时才会 import。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Segment:
    """一条消息段。kind 与 QQ 官方机器人 msg_type 的映射见 gateway.py。"""

    kind: str  # "text" | "image" | "record"
    content: str = ""  # text 专用
    file: str = ""  # image / record 专用：本地路径或公网 URL
    meta: dict[str, Any] = field(default_factory=dict)

    def to_astrbot_comp(self):
        """把中间表示转成 AstrBot 的 Comp.Plain / Comp.Image / Comp.Record。

        本地文件必须用 fromFileSystem；语音必须用 wav（AstrBot 的 Record
        只接受 wav），因此优先取 meta.wav_for_astrbot。
        """
        import astrbot.api.message_components as Comp

        if self.kind == "text":
            return Comp.Plain(text=self.content)
        if self.kind == "image":
            return Comp.Image.fromFileSystem(self.file)
        if self.kind == "record":
            wav = self.meta.get("wav_for_astrbot") or self.file
            return Comp.Record(file=wav)
        raise ValueError(f"未知消息段类型: {self.kind}")

    def brief(self) -> str:
        if self.kind == "text":
            return self.content[:60].replace("\n", " ")
        return f"[{self.kind}] {self.file}"
