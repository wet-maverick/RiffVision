"""
downloader.py
-------------
yt-dlp wrapper for RiffVision.

Provides:
  - search_youtube()    : search for videos, return list of VideoResult
  - fetch_thumbnail()   : download a thumbnail image as a PIL Image
  - download_video()    : download a YouTube video as video.mp4 to a given folder

All heavy operations are designed to be called from background threads.
Progress is reported via callbacks to keep the UI responsive.
"""

from __future__ import annotations

import io
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests
from PIL import Image

# ---------------------------------------------------------------------------
# yt-dlp import
# ---------------------------------------------------------------------------

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError, ExtractorError
except ImportError as e:
    raise ImportError(
        "yt-dlp is not installed. Run: pip install 'yt-dlp[default]'"
    ) from e

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class VideoResult:
    """A single YouTube search result."""
    video_id: str
    title: str
    channel: str
    duration_sec: int
    thumbnail_url: str
    watch_url: str
    view_count: int = 0
    description: str = ""

    @property
    def duration_fmt(self) -> str:
        """Human-readable duration string (mm:ss or h:mm:ss)."""
        s = self.duration_sec
        if s <= 0:
            return "?"
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"

    @property
    def view_count_fmt(self) -> str:
        v = self.view_count
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M views"
        if v >= 1_000:
            return f"{v // 1_000}K views"
        return f"{v} views"


@dataclass
class DownloadProgress:
    """Progress information passed to the progress callback."""
    status: str = "idle"          # idle | downloading | processing | done | error
    percent: float = 0.0          # 0–100
    speed: str = ""               # e.g. "3.2 MiB/s"
    eta: str = ""                 # e.g. "0:23"
    filename: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_ydl_opts(
    deno_path: Optional[str] = None,
    extra: Optional[dict] = None,
    cookie_browser: str = "chrome",
) -> dict:
    """
    Build yt-dlp options dict with EJS / Deno configuration.
    All output is suppressed — errors are handled via exceptions only.
    """
    opts: dict = {
        "quiet":       True,
        "no_warnings": True,
        "noprogress":  True,
        # Route yt-dlp's own logger to /dev/null so cookie-not-found
        # messages never appear in the terminal.
        "logger":      _SilentLogger(),
    }

    if deno_path:
        os.environ["DENO_PATH"] = deno_path

    opts["js_runtimes"] = {"deno": {}}

    if cookie_browser and cookie_browser != "none":
        opts["cookiesfrombrowser"] = (cookie_browser,)

    if extra:
        opts.update(extra)

    return opts


class _SilentLogger:
    """Drop all yt-dlp log messages — we handle errors via exceptions."""
    def debug(self, msg):   pass
    def info(self, msg):    pass
    def warning(self, msg): pass
    def error(self, msg):   pass


def _thumbnail_url(video_id: str) -> str:
    """Return the best available thumbnail URL for a YouTube video ID."""
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _is_cookie_error(msg: str) -> bool:
    """Return True if the error is about missing/unreadable browser cookies."""
    m = msg.lower()
    return ("cookie" in m and ("could not find" in m or "no such file" in m
                               or "unable to open" in m or "database" in m))


def _is_age_gate(msg: str) -> bool:
    """Return True if the error is a YouTube age-verification rejection."""
    m = msg.lower()
    return "sign in to confirm your age" in m or "age-restricted" in m


def search_youtube(
    query: str,
    max_results: int = 8,
    deno_path: Optional[str] = None,
    cookie_browser: str = "chrome",
) -> list[VideoResult]:
    """
    Search YouTube using yt-dlp's ytsearch: prefix.
    Returns up to max_results VideoResult objects.
    Raises RuntimeError on failure.

    If cookie extraction fails (browser not installed / profile missing),
    retries automatically without cookies — most videos don't need them.
    Age-gated videos will fail on the retry and surface a clear error.
    """
    def _do_search(browser: str) -> list[VideoResult]:
        opts = _build_ydl_opts(deno_path, {
            "extract_flat": True,
            "skip_download": True,
        }, cookie_browser=browser)

        results: list[VideoResult] = []
        # Catch Exception broadly — cookie errors fire during YoutubeDL.__init__
        try:
            with YoutubeDL(opts) as ydl:
                search_url = f"ytsearch{max_results}:{query}"
                info = ydl.extract_info(search_url, download=False)
        except Exception as exc:
            raise RuntimeError(f"YouTube search failed: {exc}") from exc

        if not info or "entries" not in info:
            return []

            for entry in info.get("entries", []):
                if not entry:
                    continue
                vid_id = entry.get("id", "")
                if not vid_id:
                    continue
                thumb = (
                    entry.get("thumbnail")
                    or (entry.get("thumbnails", [{}])[-1].get("url", "")
                        if entry.get("thumbnails") else "")
                    or _thumbnail_url(vid_id)
                )
                results.append(VideoResult(
                    video_id=vid_id,
                    title=entry.get("title", "Unknown Title"),
                    channel=entry.get("uploader") or entry.get("channel") or "Unknown",
                    duration_sec=int(entry.get("duration") or 0),
                    thumbnail_url=thumb,
                    watch_url=f"https://www.youtube.com/watch?v={vid_id}",
                    view_count=int(entry.get("view_count") or 0),
                    description=entry.get("description") or "",
                ))
        return results

    try:
        return _do_search(cookie_browser)
    except RuntimeError as exc:
        # If the failure is a cookie/browser error, retry without cookies.
        # This keeps search working even when Chrome isn't installed or the
        # profile path doesn't exist. Age-gated videos will still fail on
        # the retry — that error will surface normally to the user.
        if _is_cookie_error(str(exc)):
            return _do_search("none")
        raise


# ---------------------------------------------------------------------------
# Thumbnail fetching
# ---------------------------------------------------------------------------

_thumb_cache: dict[str, Image.Image] = {}
_thumb_lock = threading.Lock()


def fetch_thumbnail(
    video_id: str,
    width: int = 320,
    height: int = 180,
) -> Optional[Image.Image]:
    """
    Download and return a PIL Image thumbnail for the given video ID.
    Results are cached in memory.
    Falls back to lower-resolution versions if maxres is unavailable.
    Returns None if all attempts fail.
    """
    cache_key = f"{video_id}_{width}x{height}"
    with _thumb_lock:
        if cache_key in _thumb_cache:
            return _thumb_cache[cache_key]

    urls = [
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/default.jpg",
    ]

    for url in urls:
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                img = img.resize((width, height), Image.LANCZOS)
                with _thumb_lock:
                    _thumb_cache[cache_key] = img
                return img
        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_video(
    video_result: VideoResult,
    dest_folder: Path,
    deno_path: Optional[str] = None,
    progress_cb: Optional[Callable[[DownloadProgress], None]] = None,
    cookie_browser: str = "chrome",
) -> Path:
    """
    Download a YouTube video to dest_folder/video.mp4.

    Uses yt-dlp with:
      - Best video+audio quality up to 1080p
      - Re-muxed to mp4 via ffmpeg (no re-encode, preserves quality)
      - EJS / Deno JS challenge solving
      - bgutil PO Token plugin (auto-registered if installed)

    Returns the path to the downloaded file.
    Raises RuntimeError on failure.
    """
    dest_folder = Path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)
    output_path = dest_folder / "video.mp4"

    # Remove any existing partial download
    temp_path = dest_folder / "video.%(ext)s"

    prog = DownloadProgress(status="downloading")

    def _progress_hook(d: dict):
        nonlocal prog
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                prog.percent = (downloaded / total) * 100
            else:
                prog.percent = 0
            prog.speed = d.get("_speed_str", "").strip() or ""
            prog.eta = d.get("_eta_str", "").strip() or ""
            prog.filename = d.get("filename", "")
            prog.status = "downloading"

        elif d["status"] == "finished":
            prog.percent = 100
            prog.status = "processing"
            prog.speed = ""
            prog.eta = ""

        elif d["status"] == "error":
            prog.status = "error"
            prog.error = str(d.get("error", "Unknown error"))

        if progress_cb:
            progress_cb(DownloadProgress(
                status=prog.status,
                percent=prog.percent,
                speed=prog.speed,
                eta=prog.eta,
                filename=prog.filename,
                error=prog.error,
            ))

    # Find ffmpeg — yt-dlp needs it for merging streams
    from app.setup.dependency_check import get_ffmpeg_path
    ffmpeg_loc = get_ffmpeg_path()
    ffmpeg_dir = str(Path(ffmpeg_loc).parent) if ffmpeg_loc else None

    def _do_download(browser: str):
        _opts = _build_ydl_opts(deno_path, {
            "format": (
                "bestvideo[vcodec^=avc][height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[vcodec^=avc][height<=1080]+bestaudio"
                "/best[vcodec^=avc][height<=1080][ext=mp4]"
                "/best[vcodec^=avc][height<=1080]"
            ),
            "outtmpl": str(dest_folder / "video.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [_progress_hook],
            "noprogress": False,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
        }, cookie_browser=browser)
        if ffmpeg_dir:
            _opts["ffmpeg_location"] = ffmpeg_dir
        # Catch Exception broadly — cookie errors fire during YoutubeDL.__init__
        # before download() is even called, so they won't be DownloadError.
        try:
            with YoutubeDL(_opts) as ydl:
                ydl.download([video_result.watch_url])
        except Exception as e:
            raise RuntimeError(str(e)) from e

    try:
        _do_download(cookie_browser)
    except RuntimeError as exc:
        err_str = str(exc)
        if _is_cookie_error(err_str):
            # Browser profile not found — retry without cookies.
            # If the video is age-gated, the retry will fail with a clear message.
            try:
                _do_download("none")
            except RuntimeError as exc2:
                err2 = str(exc2)
                if _is_age_gate(err2):
                    raise RuntimeError(
                        "This video is age-restricted.\n\n"
                        "To download it:\n"
                        "1. Go to Settings → Browser for cookies\n"
                        "2. Select the browser you use for YouTube\n"
                        "3. Make sure you're logged into YouTube in that browser\n"
                        "4. Try downloading again."
                    ) from exc2
                raise RuntimeError(f"Download failed: {exc2}") from exc2
        elif _is_age_gate(err_str):
            raise RuntimeError(
                "This video is age-restricted.\n\n"
                "To download it:\n"
                "1. Go to Settings → Browser for cookies\n"
                "2. Select the browser you use for YouTube\n"
                "3. Make sure you're logged into YouTube in that browser\n"
                "4. Try downloading again."
            ) from exc
        else:
            raise RuntimeError(f"Download failed: {exc}") from exc

    # Ensure the output file is named exactly video.mp4
    # yt-dlp may produce video.webm or video.mkv if conversion failed
    possible = list(dest_folder.glob("video.*"))
    for p in possible:
        if p.suffix.lower() != ".mp4" and p.stem == "video":
            p.rename(output_path)
            break

    if not output_path.exists():
        # Last resort: any video.* file
        for p in possible:
            if p.exists():
                p.rename(output_path)
                break

    if not output_path.exists():
        raise RuntimeError("Download completed but video.mp4 was not found in the song folder.")

    if progress_cb:
        progress_cb(DownloadProgress(status="done", percent=100))

    return output_path
