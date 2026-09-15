"""
main_window.py
--------------
Root CustomTkinter window for RiffVision.

Layout:
  ┌──────────────────────────────────────────────────────┐
  │  Header bar  (logo + title + settings button)        │
  ├────────────────┬─────────────────────────────────────┤
  │                │                                     │
  │  LibraryPanel  │  Right pane (tabbed):               │
  │  (song list)   │   - SearchPanel (YouTube results)   │
  │                │   - OffsetPanel (sync + slider)     │
  │                │                                     │
  ├────────────────┴─────────────────────────────────────┤
  │  Status bar  (progress bar + message)                │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Callable

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.setup.first_run import PALETTE, load_config, save_config
from app.setup.dependency_check import check_all, get_deno_path, get_ffmpeg_path
from app.core.song_scanner import SongEntry, scan_songs
from app.core.downloader import VideoResult, DownloadProgress, download_video
from app.core.audio_sync import compute_offset, SyncResult
from app.core.ini_writer import write_video_start_time

from app.ui.library_panel import LibraryPanel
from app.ui.search_panel import SearchPanel
from app.ui.offset_panel import OffsetPanel


# ---------------------------------------------------------------------------
# App State
# ---------------------------------------------------------------------------

class AppState:
    """Central state shared across panels."""

    def __init__(self, config: dict):
        self.config = config
        self.songs: list[SongEntry] = []
        self.selected_song: Optional[SongEntry] = None
        self.selected_video: Optional[VideoResult] = None
        self.sync_result: Optional[SyncResult] = None
        self.deno_path: Optional[str] = get_deno_path()
        self.ffmpeg_path: Optional[str] = get_ffmpeg_path()

    @property
    def songs_folder(self) -> str:
        return self.config.get("songs_folder", "D:/CloneHeroSongs")


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(ctk.CTk):

    def __init__(self, config: dict):
        super().__init__()

        self.state = AppState(config)

        # ── Window chrome ──────────────────────────────────────────────────
        self.title("RiffVision")
        self.minsize(1000, 640)
        self.configure(fg_color=PALETTE["bg_dark"])

        # Center window on screen, respecting Windows DPI and taskbar
        self.update_idletasks()
        w, h = 1280, 780
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - w) // 2)
        y = max(30, (screen_h - h) // 2)   # never go above y=30 (hides title bar)
        self.geometry(f"{w}x{h}+{x}+{y}")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # ── Build UI ───────────────────────────────────────────────────────
        self._build_header()
        self._build_body()
        self._build_statusbar()

        # ── Wire up cross-panel callbacks ──────────────────────────────────
        self.library_panel.on_song_selected = self._on_song_selected
        self.search_panel.on_video_selected = self._on_video_selected
        self.offset_panel.on_apply = self._on_apply_offset

        # ── Initial scan ───────────────────────────────────────────────────
        self.after(100, self._refresh_library)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_header(self):
        P = PALETTE

        # Outer header frame
        hdr = ctk.CTkFrame(self, fg_color=P["bg_panel"], corner_radius=0, height=72)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        # Electric blue accent line across the very top
        ctk.CTkFrame(hdr, fg_color=P["accent_blue"], height=3, corner_radius=0).pack(
            fill="x", side="top"
        )

        # Inner row — all content
        row = ctk.CTkFrame(hdr, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=20)

        # ── Logo ──────────────────────────────────────────────────────
        logo_frame = ctk.CTkFrame(row, fg_color="transparent")
        logo_frame.pack(side="left", fill="y")

        ctk.CTkLabel(
            logo_frame,
            text="RIFF",
            font=ctk.CTkFont(family="Segoe UI Black", size=28, weight="bold"),
            text_color=P["accent_blue"],
        ).pack(side="left", pady=14)

        ctk.CTkLabel(
            logo_frame,
            text="VISION",
            font=ctk.CTkFont(family="Segoe UI Black", size=28, weight="bold"),
            text_color=P["accent_cyan"],
        ).pack(side="left")

        # Divider pip
        ctk.CTkFrame(
            logo_frame, fg_color=P["border"], width=1, corner_radius=0
        ).pack(side="left", fill="y", padx=16, pady=16)

        ctk.CTkLabel(
            logo_frame,
            text="Clone Hero Video Manager",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_dim"],
        ).pack(side="left")

        # ── Right controls ────────────────────────────────────────────
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right", fill="y", pady=14)

        self.folder_btn = ctk.CTkButton(
            right,
            text="⊙  Change Folder",
            width=140,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=P["bg_card"],
            hover_color=P["bg_card_hover"],
            border_color=P["border"],
            border_width=1,
            text_color=P["text_secondary"],
            corner_radius=18,
            command=self._change_folder,
        )
        self.folder_btn.pack(side="left", padx=(0, 8))

        self.rescan_btn = ctk.CTkButton(
            right,
            text="↺  Rescan Songs",
            width=140,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=P["accent_purple"],
            hover_color=P["accent_blue"],
            corner_radius=18,
            command=self._refresh_library,
        )
        self.rescan_btn.pack(side="left")

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # Left: library (fixed width)
        self.library_panel = LibraryPanel(body, self.state)
        self.library_panel.pack(side="left", fill="y", padx=(12, 6), pady=12)

        # Right: tabbed view
        right_frame = ctk.CTkFrame(body, fg_color="transparent")
        right_frame.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=12)

        self.tab_view = ctk.CTkTabview(
            right_frame,
            fg_color=PALETTE["bg_panel"],
            segmented_button_fg_color=PALETTE["bg_card"],
            segmented_button_selected_color=PALETTE["accent_blue"],
            segmented_button_selected_hover_color=PALETTE["accent_cyan"],
            segmented_button_unselected_color=PALETTE["bg_card"],
            segmented_button_unselected_hover_color=PALETTE["bg_card_hover"],
            text_color=PALETTE["text_primary"],
            text_color_disabled=PALETTE["text_dim"],
            border_color=PALETTE["border"],
            border_width=1,
        )
        self.tab_view.pack(fill="both", expand=True)

        self.tab_view.add("Search YouTube")
        self.tab_view.add("Sync & Offset")

        self.search_panel = SearchPanel(
            self.tab_view.tab("Search YouTube"),
            self.state,
            status_cb=self._set_status,
        )
        self.search_panel.pack(fill="both", expand=True)

        self.offset_panel = OffsetPanel(
            self.tab_view.tab("Sync & Offset"),
            self.state,
            status_cb=self._set_status,
        )
        self.offset_panel.pack(fill="both", expand=True)

    def _build_statusbar(self):
        P = PALETTE

        # Outer bar
        bar = ctk.CTkFrame(self, fg_color=P["bg_panel"], corner_radius=0, height=48)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        # Separator line at top of bar
        ctk.CTkFrame(bar, fg_color=P["border"], height=1, corner_radius=0).pack(
            fill="x", side="top"
        )

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16)

        # Accent dot
        ctk.CTkFrame(
            inner,
            fg_color=P["accent_blue"],
            width=8,
            height=8,
            corner_radius=4,
        ).pack(side="left", padx=(0, 10), pady=20)

        self.status_label = ctk.CTkLabel(
            inner,
            text="Ready  —  select a song from the library to begin",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        # Song count badge
        self.song_count_label = ctk.CTkLabel(
            inner,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"],
            anchor="e",
        )
        self.song_count_label.pack(side="right", padx=(0, 14))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            inner,
            width=200,
            height=6,
            fg_color=P["bg_card"],
            progress_color=P["accent_blue"],
            corner_radius=3,
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(side="right", padx=(0, 14), pady=21)

    # ------------------------------------------------------------------
    # Status helpers (thread-safe)
    # ------------------------------------------------------------------

    def _set_status(self, message: str, progress: float = -1):
        """Update status bar. progress=-1 keeps current bar value."""
        def _do():
            self.status_label.configure(text=message)
            if 0 <= progress <= 1:
                self.progress_bar.set(progress)
                self.progress_bar.configure(progress_color=PALETTE["accent_blue"])
            elif progress == 1.0:
                self.progress_bar.set(1.0)
                self.progress_bar.configure(progress_color=PALETTE["success"])
        self.after(0, _do)

    def _set_progress(self, dp: DownloadProgress):
        """Handle DownloadProgress from the downloader thread."""
        def _do():
            pct = dp.percent / 100.0
            self.progress_bar.set(pct)

            if dp.status == "downloading":
                speed = f"  {dp.speed}" if dp.speed else ""
                eta = f"  ETA {dp.eta}" if dp.eta else ""
                self.status_label.configure(
                    text=f"Downloading...  {dp.percent:.0f}%{speed}{eta}"
                )
                self.progress_bar.configure(progress_color=PALETTE["accent_blue"])

            elif dp.status == "processing":
                self.status_label.configure(text="Processing video (muxing)...")
                self.progress_bar.configure(progress_color=PALETTE["accent_cyan"])

            elif dp.status == "done":
                self.status_label.configure(text="Download complete!")
                self.progress_bar.configure(progress_color=PALETTE["success"])

            elif dp.status == "error":
                self.status_label.configure(text=f"Download error: {dp.error}")
                self.progress_bar.configure(progress_color=PALETTE["danger"])

        self.after(0, _do)

    # ------------------------------------------------------------------
    # Library refresh
    # ------------------------------------------------------------------

    def _refresh_library(self):
        self._set_status("Scanning songs folder...", 0.0)
        self.rescan_btn.configure(state="disabled", text="Scanning...")

        def _scan():
            songs = scan_songs(self.state.songs_folder)
            self.state.songs = songs

            def _done():
                self.library_panel.refresh(songs)
                total = len(songs)
                missing = sum(1 for s in songs if not s.has_video)
                self.song_count_label.configure(
                    text=f"{total} songs  •  {missing} missing video"
                )
                self._set_status(
                    f"Loaded {total} songs  ({missing} missing video)",
                    progress=0,
                )
                self.rescan_btn.configure(state="normal", text="Rescan Songs")

            self.after(0, _done)

        threading.Thread(target=_scan, daemon=True).start()

    # ------------------------------------------------------------------
    # Panel callbacks
    # ------------------------------------------------------------------

    def _on_song_selected(self, song: SongEntry):
        """Called when user clicks a song in the library."""
        self.state.selected_song = song
        self.state.selected_video = None
        self.state.sync_result = None

        self.search_panel.set_song(song)
        self.offset_panel.clear()
        self.tab_view.set("Search YouTube")

        self._set_status(
            f"Selected: {song.display_name}  •  "
            + ("Video present" if song.has_video else "No video — search below"),
            progress=0,
        )

    def _on_video_selected(self, video: VideoResult):
        """Called when user picks a video result in the search panel."""
        song = self.state.selected_song
        if not song:
            return

        self.state.selected_video = video
        self._set_status(f"Downloading: {video.title}", 0.02)

        def _download():
            try:
                path = download_video(
                    video_result=video,
                    dest_folder=song.folder,
                    deno_path=self.state.deno_path,
                    progress_cb=self._set_progress,
                )
            except RuntimeError as exc:
                def _err():
                    messagebox.showerror("Download Failed", str(exc))
                    self._set_status(f"Download failed: {exc}", 0)
                self.after(0, _err)
                return

            # Update song entry
            song.has_video = True
            song.video_path = path

            self._set_status("Download complete!  Running audio sync...", 1.0)
            self._run_sync(song, path)

        threading.Thread(target=_download, daemon=True).start()

    def _run_sync(self, song: SongEntry, video_path: Path):
        """Run audio sync in background after download completes."""
        stem = song.best_audio_stem()
        ffmpeg = self.state.ffmpeg_path

        if not stem or not ffmpeg:
            def _no_sync():
                self.offset_panel.show_no_sync(
                    reason="No audio stem found" if not stem else "ffmpeg not available"
                )
                self.tab_view.set("Sync & Offset")
                self.library_panel.refresh(self.state.songs)
            self.after(0, _no_sync)
            return

        def _sync():
            result = compute_offset(
                video_path=video_path,
                stem_path=stem,
                ffmpeg_path=ffmpeg,
                progress_cb=lambda msg: self._set_status(msg),
            )
            self.state.sync_result = result

            def _show():
                self.offset_panel.show_result(song, result)
                self.tab_view.set("Sync & Offset")
                self.library_panel.refresh(self.state.songs)

            self.after(0, _show)

        threading.Thread(target=_sync, daemon=True).start()

    def _on_apply_offset(self, song: SongEntry, offset_ms: int):
        """Called when user clicks Apply in the offset panel."""
        try:
            ini_path = song.folder / "song.ini"
            write_video_start_time(ini_path, offset_ms)
            song.video_start_ms = offset_ms
            self._set_status(
                f"Saved  video_start_time = {offset_ms:+d} ms  to {song.display_name}",
                progress=0,
            )
        except OSError as exc:
            messagebox.showerror("Write Error", str(exc))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _change_folder(self):
        current = self.state.songs_folder
        chosen = filedialog.askdirectory(
            title="Select Clone Hero Songs Folder",
            initialdir=current if Path(current).exists() else "/",
        )
        if chosen:
            self.state.config["songs_folder"] = chosen
            save_config(self.state.config)
            self._refresh_library()
