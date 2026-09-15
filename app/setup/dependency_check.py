"""
dependency_check.py
-------------------
Checks for and optionally installs all non-Python prerequisites:
  - Deno (JS runtime required by yt-dlp EJS challenge solver)
  - bgutil-ytdlp-pot-provider (PO Token plugin for YouTube bot-detection bypass)
  - ffmpeg (audio extraction for sync)

Returns structured status objects so the UI can display friendly messages.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

APP_DATA_DIR = Path.home() / ".riffvision"
DENO_DIR = APP_DATA_DIR / "deno"
FFMPEG_DIR = APP_DATA_DIR / "ffmpeg"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DepStatus:
    name: str
    found: bool
    version: str = ""
    path: str = ""
    error: str = ""


@dataclass
class CheckResult:
    deno: DepStatus = field(default_factory=lambda: DepStatus("Deno"))
    pot_plugin: DepStatus = field(default_factory=lambda: DepStatus("PO Token Plugin"))
    ffmpeg: DepStatus = field(default_factory=lambda: DepStatus("ffmpeg"))

    @property
    def all_ok(self) -> bool:
        return self.deno.found and self.ffmpeg.found
        # pot_plugin is nice-to-have; we degrade gracefully without it

    @property
    def critical_missing(self) -> list[str]:
        missing = []
        if not self.deno.found:
            missing.append("Deno")
        if not self.ffmpeg.found:
            missing.append("ffmpeg")
        return missing


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Run a command, return (success, stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def _find_deno() -> DepStatus:
    """Locate Deno — check bundled path first, then system PATH."""
    # 1. Bundled by RiffVision
    bundled = DENO_DIR / ("deno.exe" if platform.system() == "Windows" else "deno")
    if bundled.exists():
        ok, out = _run([str(bundled), "--version"])
        if ok:
            version = out.splitlines()[0] if out else "unknown"
            return DepStatus("Deno", True, version, str(bundled))

    # 2. System PATH
    system_deno = shutil.which("deno")
    if system_deno:
        ok, out = _run([system_deno, "--version"])
        if ok:
            version = out.splitlines()[0] if out else "unknown"
            return DepStatus("Deno", True, version, system_deno)

    return DepStatus("Deno", False, error="Not found")


def _find_ffmpeg() -> DepStatus:
    """Locate ffmpeg — check bundled path first, then system PATH."""
    bundled = FFMPEG_DIR / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    if bundled.exists():
        ok, out = _run([str(bundled), "-version"])
        if ok:
            version = out.splitlines()[0] if out else "unknown"
            return DepStatus("ffmpeg", True, version, str(bundled))

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        ok, out = _run([system_ffmpeg, "-version"])
        if ok:
            version = out.splitlines()[0] if out else "unknown"
            return DepStatus("ffmpeg", True, version, system_ffmpeg)

    return DepStatus("ffmpeg", False, error="Not found")


def _find_pot_plugin() -> DepStatus:
    """Check if bgutil-ytdlp-pot-provider is importable."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("bgutil_ytdlp_pot_provider")
        if spec is not None:
            return DepStatus("PO Token Plugin", True, "installed", spec.origin or "")
    except Exception:
        pass
    return DepStatus("PO Token Plugin", False, error="Not installed")


def check_all() -> CheckResult:
    """Run all dependency checks and return a CheckResult."""
    result = CheckResult()
    result.deno = _find_deno()
    result.ffmpeg = _find_ffmpeg()
    result.pot_plugin = _find_pot_plugin()
    return result


# ---------------------------------------------------------------------------
# Installation helpers
# ---------------------------------------------------------------------------

def get_deno_path() -> Optional[str]:
    """Return the path to the Deno binary if available."""
    status = _find_deno()
    return status.path if status.found else None


def get_ffmpeg_path() -> Optional[str]:
    """Return the path to the ffmpeg binary if available."""
    status = _find_ffmpeg()
    return status.path if status.found else None


def install_deno(progress_cb: Optional[Callable[[str], None]] = None) -> DepStatus:
    """
    Download and install Deno into APP_DATA_DIR/deno/.
    progress_cb receives status strings for display.
    """
    def emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    system = platform.system()
    machine = platform.machine().lower()

    # Build download URL for Deno v2 latest
    base = "https://github.com/denoland/deno/releases/latest/download"
    if system == "Windows":
        url = f"{base}/deno-x86_64-pc-windows-msvc.zip"
        archive_name = "deno.zip"
        bin_name = "deno.exe"
    elif system == "Darwin":
        if "arm" in machine or "aarch" in machine:
            url = f"{base}/deno-aarch64-apple-darwin.zip"
        else:
            url = f"{base}/deno-x86_64-apple-darwin.zip"
        archive_name = "deno.zip"
        bin_name = "deno"
    else:
        url = f"{base}/deno-x86_64-unknown-linux-gnu.zip"
        archive_name = "deno.zip"
        bin_name = "deno"

    DENO_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = DENO_DIR / archive_name
    dest_path = DENO_DIR / bin_name

    try:
        emit(f"Downloading Deno from {url} ...")
        urllib.request.urlretrieve(url, archive_path)

        emit("Extracting Deno ...")
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extract(bin_name, DENO_DIR)

        archive_path.unlink(missing_ok=True)

        # Make executable on Unix
        if system != "Windows":
            dest_path.chmod(0o755)

        emit("Deno installed successfully.")
        return _find_deno()

    except Exception as exc:
        emit(f"Deno install failed: {exc}")
        return DepStatus("Deno", False, error=str(exc))


def install_ffmpeg(progress_cb: Optional[Callable[[str], None]] = None) -> DepStatus:
    """
    Download a static ffmpeg build into APP_DATA_DIR/ffmpeg/.
    Uses gyan.dev builds for Windows, evermeet.cx for macOS, johnvansickle for Linux.
    """
    def emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    system = platform.system()
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if system == "Windows":
            url = "https://github.com/GyanD/codexffmpeg/releases/latest/download/ffmpeg-release-essentials.zip"
            emit(f"Downloading ffmpeg (Windows) ...")
            archive_path = FFMPEG_DIR / "ffmpeg.zip"
            urllib.request.urlretrieve(url, archive_path)
            emit("Extracting ffmpeg ...")
            with zipfile.ZipFile(archive_path, "r") as zf:
                # The zip contains a versioned folder; find ffmpeg.exe inside bin/
                names = zf.namelist()
                ffmpeg_entry = next((n for n in names if n.endswith("bin/ffmpeg.exe")), None)
                if ffmpeg_entry:
                    data = zf.read(ffmpeg_entry)
                    dest = FFMPEG_DIR / "ffmpeg.exe"
                    dest.write_bytes(data)
            archive_path.unlink(missing_ok=True)

        elif system == "Darwin":
            url = "https://evermeet.cx/ffmpeg/getrelease/zip"
            emit("Downloading ffmpeg (macOS) ...")
            archive_path = FFMPEG_DIR / "ffmpeg.zip"
            urllib.request.urlretrieve(url, archive_path)
            emit("Extracting ffmpeg ...")
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(FFMPEG_DIR)
            archive_path.unlink(missing_ok=True)
            ffmpeg_bin = FFMPEG_DIR / "ffmpeg"
            if ffmpeg_bin.exists():
                ffmpeg_bin.chmod(0o755)

        else:
            url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
            emit("Downloading ffmpeg (Linux) ...")
            archive_path = FFMPEG_DIR / "ffmpeg.tar.xz"
            urllib.request.urlretrieve(url, archive_path)
            emit("Extracting ffmpeg ...")
            with tarfile.open(archive_path, "r:xz") as tf:
                members = tf.getmembers()
                ffmpeg_member = next(
                    (m for m in members if m.name.endswith("/ffmpeg") and m.isfile()),
                    None,
                )
                if ffmpeg_member:
                    ffmpeg_member.name = "ffmpeg"
                    tf.extract(ffmpeg_member, FFMPEG_DIR)
            archive_path.unlink(missing_ok=True)
            ffmpeg_bin = FFMPEG_DIR / "ffmpeg"
            if ffmpeg_bin.exists():
                ffmpeg_bin.chmod(0o755)

        emit("ffmpeg installed successfully.")
        return _find_ffmpeg()

    except Exception as exc:
        emit(f"ffmpeg install failed: {exc}")
        return DepStatus("ffmpeg", False, error=str(exc))


def install_pot_plugin(progress_cb: Optional[Callable[[str], None]] = None) -> DepStatus:
    """pip install bgutil-ytdlp-pot-provider."""
    def emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    emit("Installing PO Token plugin ...")
    ok, out = _run(
        [sys.executable, "-m", "pip", "install", "-q", "bgutil-ytdlp-pot-provider"],
        timeout=120,
    )
    if ok:
        emit("PO Token plugin installed.")
        return _find_pot_plugin()
    else:
        emit(f"PO Token plugin install failed: {out}")
        return DepStatus("PO Token Plugin", False, error=out)
