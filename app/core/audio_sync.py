"""
audio_sync.py
-------------
Computes the video_start_time offset (in milliseconds) that tells Clone Hero
where the video's audio aligns with the song stems.

Algorithm:
  1. Extract a mono audio track from video.mp4 using ffmpeg
  2. Load the best available song stem (song.ogg, guitar.ogg, etc.)
  3. Resample both to a common low sample rate (11025 Hz) for efficiency
  4. Compute normalized cross-correlation via scipy/numpy
  5. The lag at peak correlation = offset in samples → convert to ms
  6. Positive offset: video starts before song audio (video audio leads)
     Negative offset: video starts after song audio (video audio lags)

Clone Hero convention for video_start_time:
  - Negative value (e.g. -2500): video starts 2.5 seconds BEFORE the song
  - Positive value: video starts that many ms INTO playback

Returns a SyncResult with the detected offset and a confidence score.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

import numpy as np

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    """Result of an audio sync operation."""
    offset_ms: int           # video_start_time value to write into song.ini
    confidence: float        # 0.0–1.0 peak correlation coefficient
    method: str = "xcorr"    # always "xcorr" for now
    error: str = ""          # non-empty if sync failed

    @property
    def success(self) -> bool:
        return not self.error

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.85:
            return "High"
        if self.confidence >= 0.55:
            return "Medium"
        return "Low"

    @property
    def offset_display(self) -> str:
        s = self.offset_ms / 1000
        sign = "+" if s >= 0 else ""
        return f"{sign}{s:.3f}s ({self.offset_ms:+d} ms)"


# ---------------------------------------------------------------------------
# ffmpeg extraction
# ---------------------------------------------------------------------------

_SYNC_SR = 11025        # sample rate for correlation (low = fast, still accurate)
_SYNC_DURATION = 120    # seconds of audio to analyze (first 2 minutes is enough)


def _extract_audio_pcm(
    source: Path,
    ffmpeg_path: str,
    sample_rate: int = _SYNC_SR,
    duration: int = _SYNC_DURATION,
) -> np.ndarray:
    """
    Use ffmpeg to decode audio from source to raw 32-bit float PCM mono.
    Returns a 1-D numpy float32 array, or raises RuntimeError.
    """
    cmd = [
        ffmpeg_path,
        "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-t", str(duration),
        "-ac", "1",                    # mono
        "-ar", str(sample_rate),       # downsample
        "-f", "f32le",                 # raw 32-bit float LE
        "-vn",                         # no video
        "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out extracting audio")
    except FileNotFoundError:
        raise RuntimeError(f"ffmpeg not found at: {ffmpeg_path}")

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg error: {stderr}")

    raw = result.stdout
    if len(raw) < 4:
        raise RuntimeError("ffmpeg returned no audio data")

    return np.frombuffer(raw, dtype=np.float32).copy()


# ---------------------------------------------------------------------------
# Cross-correlation
# ---------------------------------------------------------------------------

def _normalized_xcorr(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute normalized cross-correlation between arrays a and b.
    Returns (correlation_coefficients, lags_in_samples).

    Uses scipy if available (faster FFT-based), falls back to numpy.
    """
    # Normalize
    a = a - a.mean()
    b = b - b.mean()
    a_std = a.std()
    b_std = b.std()

    if a_std < 1e-9 or b_std < 1e-9:
        # Silent track — can't sync
        lags = np.arange(-(len(b) - 1), len(a))
        return np.zeros(len(a) + len(b) - 1), lags

    a = a / a_std
    b = b / b_std

    # Trim to max 60 seconds to keep FFT manageable
    max_samples = _SYNC_SR * 60
    a = a[:max_samples]
    b = b[:max_samples]

    try:
        from scipy.signal import correlate, correlation_lags
        corr = correlate(a, b, mode="full", method="fft")
        lags = correlation_lags(len(a), len(b), mode="full")
    except ImportError:
        # Pure numpy fallback (slower)
        corr = np.correlate(a, b, mode="full")
        lags = np.arange(-(len(b) - 1), len(a))

    # Normalize to [-1, 1]
    norm = len(a)
    corr = corr / norm

    return corr, lags


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def compute_offset(
    video_path: Path,
    stem_path: Path,
    ffmpeg_path: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> SyncResult:
    """
    Compute the video_start_time offset by cross-correlating video audio
    against the song stem audio.

    video_path   : path to video.mp4
    stem_path    : path to best audio stem (song.ogg, guitar.ogg, etc.)
    ffmpeg_path  : path to ffmpeg binary
    progress_cb  : optional callback for status string updates

    Returns SyncResult.
    """
    def emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    emit("Extracting audio from video...")
    try:
        video_audio = _extract_audio_pcm(video_path, ffmpeg_path)
    except RuntimeError as e:
        return SyncResult(offset_ms=0, confidence=0.0, error=str(e))

    emit("Extracting audio from song stem...")
    try:
        song_audio = _extract_audio_pcm(stem_path, ffmpeg_path)
    except RuntimeError as e:
        return SyncResult(offset_ms=0, confidence=0.0, error=str(e))

    emit("Computing cross-correlation...")
    try:
        corr, lags = _normalized_xcorr(video_audio, song_audio)
    except Exception as e:
        return SyncResult(offset_ms=0, confidence=0.0, error=f"Correlation failed: {e}")

    # Find peak
    peak_idx = int(np.argmax(np.abs(corr)))
    peak_lag_samples = int(lags[peak_idx])
    confidence = float(np.abs(corr[peak_idx]))

    # Convert lag to milliseconds
    # Positive lag means video audio comes AFTER song audio starts
    # → video needs to start BEFORE song → negative video_start_time
    # We negate to match Clone Hero's video_start_time convention:
    #   video_start_time = -(lag_ms)
    lag_ms = int((peak_lag_samples / _SYNC_SR) * 1000)
    offset_ms = -lag_ms

    emit(f"Sync complete. Offset: {offset_ms:+d} ms  (confidence: {confidence:.2f})")

    return SyncResult(
        offset_ms=offset_ms,
        confidence=min(confidence, 1.0),
        method="xcorr",
    )
