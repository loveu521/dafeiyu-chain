"""能力：发语音。

开源依赖：edge-tts（微软 Edge 在线 TTS，无需 API Key）+ pydub/ffmpeg。

产出两份，对应两个投递通道：
- voice.mp3  → QQ 官机富媒体直传（file_type=3 支持 mp3/wav/ogg/silk，无需转 silk）
- voice.wav  → AstrBot 的 Comp.Record：官方文档明确「暂时只接受 wav 格式」，
               所以 16kHz 单声道 PCM wav 才是插件侧能直接吃的格式。

每次产物带批次号，避免 QQ 官机按内容 hash 命中旧缓存导致「永远是那一条」；
同时把最新一次复制到固定名，兼容验收脚本与手工查看。
"""
from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path

import edge_tts
from pydub import AudioSegment

from core.models import Segment

from .base import Skill, SkillResult


class VoiceSkill(Skill):
    name = "voice"

    def _to_wav(self, mp3: Path, wav: Path) -> None:
        AudioSegment.from_mp3(str(mp3)).set_channels(1).set_frame_rate(16000).export(
            str(wav), format="wav"
        )

    async def run(self, ctx: dict) -> SkillResult:
        text = ctx.get("speak_text") or "咕噜，本鱼今天也在好好摸鱼。白饭真好吃~"
        voice_id = self.cfg.get("voice_id", "zh-CN-XiaoyiNeural")
        rate = self.cfg.get("rate", "-8%")
        tag = ctx.get("batch_id") or datetime.now().strftime("%m%d%H%M%S")

        outdir = Path(self.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        mp3 = outdir / f"voice_{tag}.mp3"
        wav = outdir / f"voice_{tag}.wav"
        # 固定别名（最新一次），兼容 run_local 验收与人工查看
        mp3_alias, wav_alias = outdir / "voice.mp3", outdir / "voice.wav"

        comm = edge_tts.Communicate(text, voice_id, rate=rate)
        await comm.save(str(mp3))
        await asyncio.to_thread(self._to_wav, mp3, wav)
        shutil.copyfile(mp3, mp3_alias)
        shutil.copyfile(wav, wav_alias)

        seg = Segment(
            "record", file=str(mp3),
            meta={
                "codec": "mp3", "tts": "edge-tts", "voice": voice_id,
                "text": text, "bytes": mp3.stat().st_size,
                "wav_for_astrbot": str(wav), "wav_bytes": wav.stat().st_size,
                "batch_id": tag,
            },
        )
        return SkillResult(
            segments=[seg], artifacts=[str(mp3), str(wav)],
            data={"speak_text": text, "batch_id": tag},
            note=f"edge-tts 合成 mp3 {mp3.stat().st_size}B + wav {wav.stat().st_size}B（批次 {tag}）",
        )
