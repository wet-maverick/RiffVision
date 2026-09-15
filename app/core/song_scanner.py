"""
song_scanner.py
---------------
Scans a Clone Hero songs folder recursively.
Reads song.ini from each song directory and returns structured SongEntry objects.

Clone Hero song layout (per official wiki):
  Songs/
    Artist - Title/
      song.ini        ← metadata
      notes.chart     ← required
      song.ogg        ← audio stem
      video.mp4       ← optional background video  ← we detect this
      album.png       ← optional
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SongEntry:
    """Represents a single Clone Hero song found on disk."""

    # Filesystem
    folder: Path
    ini_path: Optional[Path] = None
    has_video: bool = False
    video_path: Optional[Path] = None

    # Metadata from song.ini (may be empty strings if not present)
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    year: str = ""
    charter: str = ""
    preview_start_ms: int = 0
    video_start_ms: int = 0    # video_start_time in song.ini

    # Audio stems present (for sync)
    audio_stems: list[Path] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Friendly 'Artist – Title' or folder name fallback."""
        if self.artist and self.title:
            return f"{self.artist} — {self.title}"
        if self.title:
            return self.title
        return self.folder.name

    @property
    def search_query(self) -> str:
        """Default YouTube search query based on metadata."""
        if self.artist and self.title:
            return f"{self.artist} {self.title} official music video"
        return self.folder.name

    def best_audio_stem(self) -> Optional[Path]:
        """Return the best audio stem for sync (prefer song, then guitar, etc.)."""
        priority = ["song", "guitar", "rhythm", "bass", "drums", "vocals", "keys"]
        stem_map = {s.stem.lower(): s for s in self.audio_stems}
        for name in priority:
            if name in stem_map:
                return stem_map[name]
        return self.audio_stems[0] if self.audio_stems else None


# ---------------------------------------------------------------------------
# INI parsing
# ---------------------------------------------------------------------------

_AUDIO_EXTENSIONS = {".ogg", ".mp3", ".opus", ".wav"}
_AUDIO_STEM_NAMES = {
    "song", "guitar", "bass", "rhythm", "drums", "drums_1", "drums_2",
    "drums_3", "drums_4", "vocals", "keys", "crowd",
}


def _parse_ini(ini_path: Path) -> dict:
    """
    Parse a song.ini file.
    Clone Hero song.ini files often lack a proper [section] header,
    so we inject a fake [song] header if needed.
    """
    raw = ini_path.read_text(encoding="utf-8", errors="replace")

    # If no section header, prepend one
    if not any(line.strip().startswith("[") for line in raw.splitlines()):
        raw = "[song]\n" + raw

    parser = configparser.RawConfigParser()
    parser.optionxform = str   # preserve case
    try:
        parser.read_string(raw)
    except configparser.Error:
        return {}

    # Flatten all sections into one dict (Clone Hero only has [song])
    data: dict[str, str] = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            data[key.lower()] = value.strip().strip('"')
    return data


# Video filenames Clone Hero recognises (checked case-insensitively)
_VIDEO_NAMES = {"video.mp4", "video.webm", "video.avi", "video.mkv",
                "video.ogv", "video.mov"}


def _find_video(folder: Path) -> Optional[Path]:
    """
    Find a background video for a song folder.

    Search order:
      1. Exact match for known names in the song folder itself
      2. One level UP from the song folder (video.mp4 next to the
         difficulty folder, e.g. Artist-Song/video.mp4 when chart is
         in Artist-Song/Hard/song.ini)
      3. One level DOWN into subfolders of the song folder
      4. Any .mp4/.webm in the song folder with a non-audio stem name
         (catches non-standard names like bg.mp4, background.mp4, etc.)

    Returns the Path to the first match, or None.
    """
    _VIDEO_EXTS = {".mp4", ".webm", ".avi", ".mkv", ".ogv", ".mov"}

    def _check_dir(d: Path) -> Optional[Path]:
        """Return first video file found directly in directory d."""
        try:
            for p in d.iterdir():
                if p.is_file() and p.name.lower() in _VIDEO_NAMES:
                    return p
        except PermissionError:
            pass
        return None

    # 1. Song folder itself — exact name match
    hit = _check_dir(folder)
    if hit:
        return hit

    # 2. Parent folder — video may sit one level up from a difficulty subfolder
    parent = folder.parent
    if parent != folder:
        hit = _check_dir(parent)
        if hit:
            return hit

    # 3. One level down — video in a subfolder of the song dir
    try:
        for child in folder.iterdir():
            if child.is_dir():
                hit = _check_dir(child)
                if hit:
                    return hit
    except PermissionError:
        pass

    # 4. Any video-extension file in the song folder (non-standard name)
    try:
        for p in folder.iterdir():
            if (p.is_file()
                    and p.suffix.lower() in _VIDEO_EXTS
                    and p.stem.lower() not in _AUDIO_STEM_NAMES):
                return p
    except PermissionError:
        pass

    return None


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default
    """
    Build a SongEntry from a directory.
    Returns None if the directory doesn't look like a valid song folder
    (no notes.chart/notes.mid and no song.ini).
    """
    ini_path = folder / "song.ini"
    has_chart = (folder / "notes.chart").exists() or (folder / "notes.mid").exists()

    if not ini_path.exists() and not has_chart:
        return None   # Not a song folder

    entry = SongEntry(folder=folder, ini_path=ini_path if ini_path.exists() else None)

    # Check for video — search folder and one level of subfolders
    video_path = _find_video(folder)
    entry.has_video = video_path is not None
    entry.video_path = video_path

    # Collect audio stems
    entry.audio_stems = [
        p for p in folder.iterdir()
        if p.suffix.lower() in _AUDIO_EXTENSIONS
        and p.stem.lower() in _AUDIO_STEM_NAMES
    ]

    # Parse metadata
    if ini_path.exists():
        data = _parse_ini(ini_path)
        entry.title = data.get("name", "")
        entry.artist = data.get("artist", "")
        entry.album = data.get("album", "")
        entry.genre = data.get("genre", "")
        entry.year = data.get("year", "")
        entry.charter = data.get("charter", "")
        entry.preview_start_ms = _safe_int(data.get("preview_start_time", "0"))
        entry.video_start_ms = _safe_int(data.get("video_start_time", "0"))

    # Fallback title from folder name
    if not entry.title:
        entry.title = folder.name

    return entry


# ---------------------------------------------------------------------------
# Public scanner
# ---------------------------------------------------------------------------

def scan_songs(songs_root: str | Path, depth_limit: int = 6) -> list[SongEntry]:
    """
    Recursively scan songs_root for Clone Hero song folders.

    Returns a list of SongEntry objects sorted by artist then title.
    Skips folders that don't contain either a song.ini or a notes.chart/mid.

    depth_limit prevents runaway recursion on misconfigured paths.
    """
    root = Path(songs_root)
    if not root.exists():
        return []

    songs: list[SongEntry] = []
    _scan_recursive(root, songs, current_depth=0, depth_limit=depth_limit)

    songs.sort(key=lambda s: (s.artist.lower(), s.title.lower()))
    return songs


def _scan_recursive(
    directory: Path,
    results: list[SongEntry],
    current_depth: int,
    depth_limit: int,
) -> None:
    if current_depth > depth_limit:
        return

    try:
        entries = list(directory.iterdir())
    except PermissionError:
        return

    # Try to build a song entry from this directory
    entry = _build_entry(directory)
    if entry is not None:
        results.append(entry)
        return   # Don't descend into a song folder

    # Not a song folder — recurse into subdirectories
    for child in entries:
        if child.is_dir() and not child.name.startswith("."):
            _scan_recursive(child, results, current_depth + 1, depth_limit)


def count_missing_video(songs: list[SongEntry]) -> int:
    return sum(1 for s in songs if not s.has_video)
