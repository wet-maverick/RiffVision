"""
ini_writer.py
-------------
Reads and writes Clone Hero song.ini files, specifically updating
video_start_time while preserving all other keys and comments.

Clone Hero's song.ini is a loose INI format that may or may not have
a [song] section header, and may use inconsistent spacing around '='.
We preserve the file's original formatting as much as possible.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


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
    Preserves all other content exactly as-is.
    Creates the file if it doesn't exist (unlikely but handled).
    """
    value_str = str(int(offset_ms))

    # ---- File exists — update in-place ----
    if ini_path.exists():
        try:
            text = ini_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise OSError(f"Cannot read {ini_path}: {e}") from e

        lines = text.splitlines(keepends=True)
        found = False
        new_lines = []

        for line in lines:
            # Match the key case-insensitively with flexible spacing
            if re.match(r"^\s*video_start_time\s*=", line, re.IGNORECASE):
                # Preserve original indentation and spacing style
                match = re.match(r"^(\s*video_start_time\s*=\s*)", line, re.IGNORECASE)
                if match:
                    prefix = match.group(1)
                    # Preserve original case of the key
                    new_lines.append(f"{prefix}{value_str}\n")
                else:
                    new_lines.append(f"video_start_time = {value_str}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            # Key doesn't exist — append it
            # Find the [song] section or just append at end
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

    # Look for [song] section
    for i, line in enumerate(result):
        if re.match(r"^\s*\[song\]", line, re.IGNORECASE):
            result.insert(i + 1, f"{key} = {value}\n")
            return result

    # No section found — append at end, ensuring a trailing newline
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
        if stripped.startswith("[") or not stripped or stripped.startswith(";"):
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            data[key.strip().lower()] = val.strip().strip('"')
    return data
