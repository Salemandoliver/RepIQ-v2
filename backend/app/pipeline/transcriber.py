"""Transcription behind a swappable interface.

Default implementation: Deepgram (nova-3, en-GB, diarization).
To migrate to self-hosted Whisper later, add a WhisperTranscriber implementing
the same `transcribe(audio_path, keyterms) -> list[turn]` signature and switch
in get_transcriber().
"""
import logging
from abc import ABC, abstractmethod

import httpx

from ..config import settings

log = logging.getLogger("calliq.transcriber")


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, keyterms: list[str] | None = None) -> list[dict]:
        """Returns diarized turns: [{speaker_idx:int, start_sec, end_sec, text}]"""


class DeepgramTranscriber(Transcriber):
    URL = "https://api.deepgram.com/v1/listen"

    def transcribe(self, audio_path: str, keyterms: list[str] | None = None) -> list[dict]:
        params = {
            "model": settings.deepgram_model,
            "language": settings.deepgram_language,
            "diarize": "true",
            "smart_format": "true",
            "punctuate": "true",
            "utterances": "true",
        }
        # Custom vocabulary (BT product names etc.) improves recognition
        url = self.URL
        if keyterms:
            url += "?" + "&".join(f"keyterm={httpx.QueryParams({'k': t})['k']}"
                                  for t in keyterms[:50])
        with open(audio_path, "rb") as f:
            audio = f.read()
        ext = audio_path.rsplit(".", 1)[-1].lower()
        content_type = {"mp3": "audio/mpeg", "mp4": "video/mp4", "m4a": "audio/mp4",
                        "wav": "audio/wav", "webm": "video/webm"}.get(ext, "audio/mpeg")
        resp = httpx.post(
            url, params=params, content=audio,
            headers={"Authorization": f"Token {settings.deepgram_api_key}",
                     "Content-Type": content_type},
            timeout=600,
        )
        resp.raise_for_status()
        data = resp.json()
        utterances = data.get("results", {}).get("utterances", [])
        return [{
            "speaker_idx": u.get("speaker", 0),
            "start_sec": u["start"],
            "end_sec": u["end"],
            "text": u["transcript"],
        } for u in utterances]


def assign_roles(turns: list[dict]) -> list[dict]:
    """Map diarized speaker indices to rep/customer.
    Heuristic: the speaker who talks first on an outbound call is usually the customer
    answering... in practice the rep speaks more and asks more questions. We assign
    'rep' to the speaker with the most total talk time weighted by question marks."""
    if not turns:
        return []
    stats: dict[int, float] = {}
    for t in turns:
        score = (t["end_sec"] - t["start_sec"]) + 5.0 * t["text"].count("?")
        stats[t["speaker_idx"]] = stats.get(t["speaker_idx"], 0) + score
    rep_idx = max(stats, key=stats.get)
    out = []
    for t in turns:
        out.append({
            "speaker": "rep" if t["speaker_idx"] == rep_idx else "customer",
            "start_sec": t["start_sec"],
            "end_sec": t["end_sec"],
            "text": t["text"],
        })
    return out


def get_transcriber() -> Transcriber:
    return DeepgramTranscriber()
