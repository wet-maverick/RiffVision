"""
ini_writer.py
-------------
Reads and writes Clone Hero song.ini files, specifically updating
video_start_time while preserving all other keys and comments.

Clone Hero's song.ini is a loose INI format that may or may not have
a [song] section header, and may use inconsistent spacing around '='.
Some files have [song] and the first key on the same line with no newline.
We normalise the file on every write to ensure Clone Hero can parse it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalise_lines(lines: list[str]) -> list[str]:
    """
    Fix common malformations in song.ini files:
      1. [song] header jammed onto the same line as the first key
         e.g.  "[song]video_start_time = 1356"
         →     "[song]\nvideo_start_time = 1356\n"
      2. Remove duplicate video_start_time keys (keep last occurrence)
    """
    result: list[str] = []
    for line in lines:
        # Case 1: [song] immediately followed by a key=value on same line
        m = re.match(r'^(\[song\])(.*)', line, re.IGNORECASE)
        if m and m.group(2).strip():
            # Split into two lines
            result.append(m.group(1) + "\n")
            rest = m.group(2).strip()
            if rest:
                result.append(rest + "\n")
        else:
            result.append(line)

    # Remove duplicate video_start_time — keep the LAST occurrence
    # (the one we just wrote), remove earlier ones
    vst_indices = [
        i for i, ln in enumerate(result)
        if re.match(r'^\s*video_start_time\s*=', ln, re.IGNORECASE)
    ]
    if len(vst_indices) > 1:
        # Remove all but the last
        for idx in reversed(vst_indices[:-1]):
            result.pop(idx)

    return result


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_video_start_time(ini_path: Path) -> int:
    """
    Read video_start_time from song.ini.
    Returns 0 if the key is absent or unreadable.
    """
    if not ini_path.exists():
        return 0

    try:
        text = ini_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    for line in text.splitlines():
        stripped = line.strip()
        # Handle [song]key=value on same line
        m = re.match(r'^\[song\](video_start_time\s*=.*)', stripped, re.IGNORECASE)
        if m:
            stripped = m.group(1)
        if stripped.lower().startswith("video_start_time"):
            parts = stripped.split("=", 1)
            if len(parts) == 2:
                try:
                    return int(float(parts[1].strip()))
                except ValueError:
                    return 0
    return 0


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_video_start_time(ini_path: Path, offset_ms: int) -> None:
    """
    Write (or update) the video_start_time key in song.ini.
    Normalises the file to ensure Clone Hero can parse it correctly:
      - Splits [song]key=value onto separate lines
      - Removes duplicate video_start_time entries
    """
    value_str = str(int(offset_ms))

    # ---- File exists — update in-place ----
    if ini_path.exists():
        try:
            text = ini_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise OSError(f"Cannot read {ini_path}: {e}") from e

        # Normalise first (fixes [song]key=value on same line)
        lines = _normalise_lines(text.splitlines(keepends=True))

        found = False
        new_lines = []

        for line in lines:
            if re.match(r"^\s*video_start_time\s*=", line, re.IGNORECASE):
                match = re.match(r"^(\s*video_start_time\s*=\s*)", line, re.IGNORECASE)
                if match:
                    new_lines.append(f"{match.group(1)}{value_str}\n")
                else:
                    new_lines.append(f"video_start_time = {value_str}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines = _append_key(new_lines, "video_start_time", value_str)

        try:
            ini_path.write_text("".join(new_lines), encoding="utf-8")
        except OSError as e:
            raise OSError(f"Cannot write {ini_path}: {e}") from e

    # ---- File doesn't exist — create minimal one ----
    else:
        content = f"[song]\nvideo_start_time = {value_str}\n"
        try:
            ini_path.write_text(content, encoding="utf-8")
        except OSError as e:
            raise OSError(f"Cannot create {ini_path}: {e}") from e


def _append_key(lines: list[str], key: str, value: str) -> list[str]:
    """
    Insert key = value after the [song] section header if found,
    otherwise append at the end of the file.
    """
    result = list(lines)
    for i, line in enumerate(result):
        if re.match(r"^\s*\[song\]\s*$", line, re.IGNORECASE):
            result.insert(i + 1, f"{key} = {value}\n")
            return result

    # No clean [song] line — append at end
    if result and not result[-1].endswith("\n"):
        result[-1] += "\n"
    result.append(f"{key} = {value}\n")
    return result


# ---------------------------------------------------------------------------
# Convenience: read all metadata
# ---------------------------------------------------------------------------

def read_metadata(ini_path: Path) -> dict[str, str]:
    """Return a flat dict of all key=value pairs in song.ini."""
    if not ini_path.exists():
        return {}
    try:
        text = ini_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    data: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        # Handle [song]key=value on same line
        m = re.match(r'^\[song\](.*=.*)', stripped, re.IGNORECASE)
        if m:
            stripped = m.group(1).strip()
        if stripped.startswith("[") or not stripped or stripped.startswith(";"):
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            data[key.strip().lower()] = val.strip().strip('"')
    return data

