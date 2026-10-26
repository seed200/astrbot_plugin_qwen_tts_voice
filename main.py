"""Qwen 3 TTS 语音回复插件。

使用本机 Qwen TTS WebUI 的 OpenAI 兼容接口
`POST /v1/audio/speech`，通过参考音频克隆音色。每隔 N 条 LLM 回复，
把当次文字回复替换成语音（也可以同时保留文字）。
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from pathlib import Path

import httpx
import astrbot.api.star as star
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain, Record, Reply
from astrbot.core.config.astrbot_config import AstrBotConfig

MIME_BY_SUFFIX = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}


class QwenTTSVoicePlugin(star.Star):
    def __init__(self, context: star.Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self.data_dir = star.StarTools.get_data_dir("astrbot_plugin_qwen_tts_voice")
        self.audio_dir = self.data_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.reply_counts: dict[str, int] = {}
        self._cleanup_old_audio()

    def _cfg(self, key: str, default=None):
        return self.config.get(key, default)

    def _enabled(self) -> bool:
        return bool(self._cfg("enabled", True))

    def _every_n(self) -> int:
        try:
            return max(0, int(self._cfg("voice_every_n", 5)))
        except (TypeError, ValueError):
            return 5

    def _reference_path(self) -> Path | None:
        directory = str(self._cfg("reference_audio_dir", "") or "").strip()
        filename = str(self._cfg("reference_audio_file", "") or "").strip()
        if not filename:
            return None
        path = Path(filename)
        if not path.is_absolute():
            if not directory:
                return None
            path = Path(directory) / filename
        return path

    def _reference_data_uri(self, path: Path) -> str:
        mime = MIME_BY_SUFFIX.get(path.suffix.lower(), "audio/wav")
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{payload}"

    async def _synthesize(self, text: str) -> Path:
        ref_path = self._reference_path()
        if ref_path is None:
            raise RuntimeError("未设置参考语音文件")
        if not ref_path.is_file():
            raise RuntimeError(f"参考语音不存在: {ref_path}")

        api_base = str(self._cfg("api_base", "http://127.0.0.1:7860")).rstrip("/")
        model = str(
            self._cfg("model", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
        ).strip()
        response_format = str(self._cfg("response_format", "wav")).strip().lower()
        if response_format not in {"wav", "mp3"}:
            response_format = "wav"

        payload = {
            "model": model,
            "input": text,
            "response_format": response_format,
            "language": str(self._cfg("language", "auto") or "auto"),
            "ref_audio": self._reference_data_uri(ref_path),
            "segment": False,
            "stream_format": "audio",
        }
        ref_text = str(self._cfg("ref_text", "") or "").strip()
        if ref_text:
            payload["ref_text"] = ref_text
        try:
            speed = float(self._cfg("speed", 1.0))
        except (TypeError, ValueError):
            speed = 1.0
        if speed != 1.0:
            payload["speed"] = max(0.25, min(speed, 4.0))

        headers = {"Content-Type": "application/json"}
        api_key = str(self._cfg("api_key", "") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            timeout = float(self._cfg("timeout_seconds", 180))
        except (TypeError, ValueError):
            timeout = 180.0

        data = b""
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(2):
                resp = await client.post(
                    f"{api_base}/v1/audio/speech",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code < 500:
                    resp.raise_for_status()
                    data = resp.content
                    break
                if attempt == 0:
                    logger.warning(
                        "[QwenTTS] Qwen 返回 500，等待后重试一次"
                    )
                    await asyncio.sleep(2)
                    continue
                resp.raise_for_status()

        if not data:
            raise RuntimeError("Qwen TTS 返回了空音频")

        out = self.audio_dir / (
            f"qwen_tts_{int(time.time())}_{uuid.uuid4().hex[:8]}.{response_format}"
        )
        out.write_bytes(data)
        return out

    @staticmethod
    def _extract_text(result) -> str:
        parts = []
        for comp in getattr(result, "chain", []) or []:
            if isinstance(comp, Plain) and comp.text:
                parts.append(comp.text)
        return "".join(parts).strip()

    def _cleanup_old_audio(self) -> None:
        cutoff = time.time() - 2 * 24 * 3600
        for path in self.audio_dir.glob("*"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    @filter.on_decorating_result(priority=100000)
    async def decorate_with_voice(self, event: AstrMessageEvent) -> None:
        if not self._enabled():
            return

        result = event.get_result()
        if result is None or not result.is_llm_result():
            return

        text = self._extract_text(result)
        if not text:
            return

        every_n = self._every_n()
        if every_n <= 0:
            return

        umo = event.unified_msg_origin
        count = self.reply_counts.get(umo, 0) + 1
        self.reply_counts[umo] = count
        if count % every_n != 0:
            return

        try:
            max_chars = max(1, int(self._cfg("max_text_chars", 200)))
        except (TypeError, ValueError):
            max_chars = 200
        if len(text) > max_chars:
            logger.info(
                f"[QwenTTS] 第 {count} 条回复过长（{len(text)} 字），本次保留文字"
            )
            return

        try:
            audio_path = await self._synthesize(text)
        except Exception as exc:
            logger.warning(f"[QwenTTS] 语音合成失败，保留文字回复: {exc}")
            return

        record = Record.fromFileSystem(str(audio_path))
        prefix = [
            comp
            for comp in result.chain
            if isinstance(comp, (Reply, At))
        ]
        new_chain = prefix + [record]
        if bool(self._cfg("send_text_too", False)):
            new_chain.append(Plain(text))
        result.chain = new_chain
        result.use_t2i_ = False
        event.set_extra("qwen_tts_audio_path", str(audio_path))
        logger.info(
            f"[QwenTTS] 第 {count} 条回复已转为语音: {audio_path.name}"
        )

    @filter.after_message_sent()
    async def cleanup_audio(self, event: AstrMessageEvent) -> None:
        path = event.get_extra("qwen_tts_audio_path")
        event.set_extra("qwen_tts_audio_path", None)
        if not path:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
