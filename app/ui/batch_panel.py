"""
batch_panel.py
--------------
Batch download tab — queue up all songs missing videos and let
RiffVision work through them automatically.

Each song gets auto-searched on YouTube, the top result is downloaded,
and audio sync runs afterwards. The user can pause, skip, or cancel
individual items. A live queue table shows status for every song.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from app.setup.first_run import PALETTE
from app.core.song_scanner import SongEntry
from app.core.downloader import search_youtube, download_video, DownloadProgress
from app.core.audio_sync import compute_offset
from app.core.ini_writer import write_video_start_time
from app.setup.dependency_check import get_deno_path, get_ffmpeg_path


class JobStatus(Enum):
    WAITING   = auto()
    SEARCHING = auto()
    DOWNLOADING = auto()
    SYNCING   = auto()
    DONE      = auto()
    SKIPPED   = auto()
    ERROR     = auto()


_STATUS_COLOR = {
    JobStatus.WAITING:     PALETTE["text_dim"],
    JobStatus.SEARCHING:   PALETTE["accent_cyan"],
    JobStatus.DOWNLOADING: PALETTE["accent_blue"],
    JobStatus.SYNCING:     PALETTE["accent_purple"],
    JobStatus.DONE:        PALETTE["success"],
    JobStatus.SKIPPED:     PALETTE["warning"],
    JobStatus.ERROR:       PALETTE["danger"],
}

_STATUS_LABEL = {
    JobStatus.WAITING:     "Waiting",
    JobStatus.SEARCHING:   "Searching...",
    JobStatus.DOWNLOADING: "Downloading...",
    JobStatus.SYNCING:     "Syncing...",
    JobStatus.DONE:        "Done",
    JobStatus.SKIPPED:     "Skipped",
    JobStatus.ERROR:       "Error",
}


@dataclass
class BatchJob:
    song: SongEntry
    status: JobStatus = JobStatus.WAITING
    progress: float = 0.0       # 0–100 during download
    note: str = ""              # short status note shown in table


class BatchPanel(ctk.CTkFrame):
    """Batch download tab — queue and auto-process multiple songs."""

    def __init__(self, parent, app_state, status_cb: Callable[[str, float], None], **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app_state = app_state
        self.status_cb = status_cb

        self._jobs: list[BatchJob] = []
        self._running = False
        self._paused  = False
        self._stop_flag = False
        self._current_thread: Optional[threading.Thread] = None

        self._build_ui()

    def _safe_after(self, fn):
        try:
            if self.winfo_exists():
                self.after(0, fn)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        P = PALETTE

        # ── Top controls ──────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            ctrl,
            text="Batch Download",
            font=ctk.CTkFont(family="Segoe UI Black", size=16, weight="bold"),
            text_color=P["accent_blue"],
            anchor="w",
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_frame.pack(side="right")

        self._load_btn = ctk.CTkButton(
            btn_frame,
            text="Load Missing Songs",
            width=160, height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=P["accent_purple"],
            hover_color=P["accent_blue"],
            corner_radius=16,
            command=self._load_missing,
        )
        self._load_btn.pack(side="left", padx=(0, 8))

        self._start_btn = ctk.CTkButton(
            btn_frame,
            text="▶  Start Queue",
            width=130, height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=P["success"],
            hover_color="#00b85a",
            text_color="#000000",
            corner_radius=16,
            state="disabled",
            command=self._start_queue,
        )
        self._start_btn.pack(side="left", padx=(0, 8))

        self._pause_btn = ctk.CTkButton(
            btn_frame,
            text="⏸  Pause",
            width=100, height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=P["warning"],
            hover_color="#cc8800",
            text_color="#000000",
            corner_radius=16,
            state="disabled",
            command=self._toggle_pause,
        )
        self._pause_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            btn_frame,
            text="■  Stop",
            width=90, height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=P["danger"],
            hover_color="#cc2222",
            corner_radius=16,
            state="disabled",
            command=self._stop_queue,
        )
        self._stop_btn.pack(side="left")

        # ── Summary bar ───────────────────────────────────────────────
        self._summary_lbl = ctk.CTkLabel(
            self,
            text="Load songs missing a video to begin.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            anchor="w",
        )
        self._summary_lbl.pack(fill="x", padx=16, pady=(0, 6))

        # ── Queue table ───────────────────────────────────────────────
        table_frame = ctk.CTkFrame(self, fg_color=P["bg_card"],
                                   corner_radius=10, border_color=P["border"],
                                   border_width=1)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Style the Treeview to match the dark theme
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Batch.Treeview",
                        background=PALETTE["bg_card"],
                        foreground=PALETTE["text_primary"],
                        fieldbackground=PALETTE["bg_card"],
                        rowheight=26,
                        font=("Segoe UI", 10),
                        borderwidth=0,
                        relief="flat")
        style.configure("Batch.Treeview.Heading",
                        background=PALETTE["bg_panel"],
                        foreground=PALETTE["text_secondary"],
                        font=("Segoe UI", 10, "bold"),
                        relief="flat",
                        borderwidth=0)
        style.map("Batch.Treeview",
                  background=[("selected", PALETTE["accent_blue"])],
                  foreground=[("selected", "#000000")])
        style.layout("Batch.Treeview", [
            ("Batch.Treeview.treearea", {"sticky": "nswe"})
        ])

        cols = ("artist", "title", "status", "progress")
        self._tree = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            style="Batch.Treeview",
            selectmode="browse",
        )
        self._tree.heading("artist",   text="Artist")
        self._tree.heading("title",    text="Title")
        self._tree.heading("status",   text="Status")
        self._tree.heading("progress", text="Note")

        self._tree.column("artist",   width=200, minwidth=100)
        self._tree.column("title",    width=250, minwidth=120)
        self._tree.column("status",   width=110, minwidth=80,  anchor="center")
        self._tree.column("progress", width=200, minwidth=100)

        vsb = ttk.Scrollbar(table_frame, orient="vertical",   command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self._tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)

        # Right-click to skip individual items
        self._tree.bind("<Button-3>", self._on_right_click)

        # Tag colors for status
        self._tree.tag_configure("done",      foreground=PALETTE["success"])
        self._tree.tag_configure("error",     foreground=PALETTE["danger"])
        self._tree.tag_configure("skipped",   foreground=PALETTE["warning"])
        self._tree.tag_configure("active",    foreground=PALETTE["accent_cyan"])
        self._tree.tag_configure("waiting",   foreground=PALETTE["text_dim"])

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def refresh_songs(self, all_songs: list[SongEntry]):
        """Called by main window when song list is refreshed."""
        self._all_songs = all_songs

    def _load_missing(self):
        """Populate queue with songs that don't have a video."""
        songs = getattr(self, "_all_songs", [])
        missing = [s for s in songs if not s.has_video]

        if not missing:
            self._summary_lbl.configure(
                text="All songs already have videos!",
                text_color=PALETTE["success"],
            )
            return

        self._jobs = [BatchJob(song=s) for s in missing]
        self._rebuild_table()
        self._start_btn.configure(state="normal")
        self._summary_lbl.configure(
            text=f"{len(missing)} songs queued for download.",
            text_color=PALETTE["text_secondary"],
        )

    def _rebuild_table(self):
        """Clear and repopulate the Treeview from self._jobs."""
        for item in self._tree.get_children():
            self._tree.delete(item)
        for i, job in enumerate(self._jobs):
            tag = self._job_tag(job)
            self._tree.insert(
                "", "end", iid=str(i),
                values=(
                    job.song.artist or "Unknown",
                    job.song.title  or job.song.folder.name,
                    _STATUS_LABEL[job.status],
                    job.note,
                ),
                tags=(tag,),
            )

    def _update_row(self, idx: int):
        """Refresh a single row in the Treeview — called from main thread."""
        if idx < 0 or idx >= len(self._jobs):
            return
        job = self._jobs[idx]
        tag = self._job_tag(job)
        note = job.note
        if job.status == JobStatus.DOWNLOADING and job.progress > 0:
            note = f"{job.progress:.0f}%  {job.note}"
        self._tree.item(str(idx), values=(
            job.song.artist or "Unknown",
            job.song.title  or job.song.folder.name,
            _STATUS_LABEL[job.status],
            note,
        ), tags=(tag,))
        # Scroll to keep active row visible
        if job.status in (JobStatus.SEARCHING, JobStatus.DOWNLOADING, JobStatus.SYNCING):
            self._tree.see(str(idx))

    def _job_tag(self, job: BatchJob) -> str:
        if job.status == JobStatus.DONE:      return "done"
        if job.status == JobStatus.ERROR:     return "error"
        if job.status == JobStatus.SKIPPED:   return "skipped"
        if job.status in (JobStatus.SEARCHING, JobStatus.DOWNLOADING,
                          JobStatus.SYNCING):  return "active"
        return "waiting"

    def _update_summary(self):
        done    = sum(1 for j in self._jobs if j.status == JobStatus.DONE)
        errors  = sum(1 for j in self._jobs if j.status == JobStatus.ERROR)
        skipped = sum(1 for j in self._jobs if j.status == JobStatus.SKIPPED)
        total   = len(self._jobs)
        self._summary_lbl.configure(
            text=f"{done}/{total} done  •  {errors} errors  •  {skipped} skipped",
            text_color=PALETTE["text_secondary"],
        )

    # ------------------------------------------------------------------
    # Queue execution
    # ------------------------------------------------------------------

    def _start_queue(self):
        if self._running:
            return
        self._running   = True
        self._paused    = False
        self._stop_flag = False
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal")
        self._stop_btn.configure(state="normal")
        self._load_btn.configure(state="disabled")

        self._current_thread = threading.Thread(
            target=self._run_queue, daemon=True
        )
        self._current_thread.start()

    def _toggle_pause(self):
        if not self._running:
            return
        self._paused = not self._paused
        self._pause_btn.configure(
            text="▶  Resume" if self._paused else "⏸  Pause"
        )

    def _stop_queue(self):
        self._stop_flag = True
        self._paused    = False   # unblock pause so thread can exit

    def _run_queue(self):
        """Worker thread — processes jobs one by one."""
        deno_path  = get_deno_path()
        ffmpeg_path = get_ffmpeg_path()

        for idx, job in enumerate(self._jobs):
            if self._stop_flag:
                break

            # Skip already-finished jobs (e.g. from a previous run)
            if job.status in (JobStatus.DONE, JobStatus.SKIPPED):
                continue

            # Wait while paused
            while self._paused and not self._stop_flag:
                time.sleep(0.2)
            if self._stop_flag:
                break

            self._set_job(idx, JobStatus.SEARCHING, "Looking up on YouTube...")

            # Search YouTube — take top result
            try:
                results = search_youtube(
                    job.song.search_query,
                    max_results=1,
                    deno_path=deno_path,
                )
            except Exception as exc:
                self._set_job(idx, JobStatus.ERROR, f"Search failed: {exc}"[:80])
                continue

            if not results:
                self._set_job(idx, JobStatus.SKIPPED, "No results found")
                continue

            video = results[0]
            self._set_job(idx, JobStatus.DOWNLOADING,
                          f"{video.title[:50]}")

            # Download
            def _prog(dp: DownloadProgress, i=idx, j=job):
                j.progress = dp.percent
                j.note = dp.speed or ""
                self._safe_after(lambda ii=i: self._update_row(ii))

            try:
                path = download_video(
                    video_result=video,
                    dest_folder=job.song.folder,
                    deno_path=deno_path,
                    progress_cb=_prog,
                )
            except Exception as exc:
                self._set_job(idx, JobStatus.ERROR, f"Download failed: {exc}"[:80])
                continue

            # Update song entry on main thread
            def _mark_done(s=job.song, p=path):
                s.has_video  = True
                s.video_path = p
            self._safe_after(_mark_done)

            # Audio sync (optional — skip if no stem or ffmpeg)
            stem = job.song.best_audio_stem()
            if stem and ffmpeg_path:
                self._set_job(idx, JobStatus.SYNCING, "Detecting offset...")
                try:
                    sync = compute_offset(
                        video_path=path,
                        stem_path=stem,
                        ffmpeg_path=ffmpeg_path,
                    )
                    if sync.success:
                        write_video_start_time(job.song.folder / "song.ini",
                                               sync.offset_ms)
                        self._set_job(idx, JobStatus.DONE,
                                      f"Offset {sync.offset_ms:+d} ms "
                                      f"[{sync.confidence_label}]")
                    else:
                        self._set_job(idx, JobStatus.DONE,
                                      f"Done (sync failed: {sync.error[:40]})")
                except Exception as exc:
                    self._set_job(idx, JobStatus.DONE,
                                  f"Done (sync error: {str(exc)[:40]})")
            else:
                self._set_job(idx, JobStatus.DONE, "Done (no sync — stems missing)")

            self._safe_after(self._update_summary)

        # Queue finished
        def _finish():
            self._running = False
            self._start_btn.configure(state="normal")
            self._pause_btn.configure(state="disabled", text="⏸  Pause")
            self._stop_btn.configure(state="disabled")
            self._load_btn.configure(state="normal")
            self._update_summary()
            self.status_cb("Batch download complete.", 0)

        self._safe_after(_finish)

    def _set_job(self, idx: int, status: JobStatus, note: str = ""):
        """Set a job's status and schedule a UI update on the main thread."""
        if 0 <= idx < len(self._jobs):
            self._jobs[idx].status = status
            self._jobs[idx].note   = note
            self._safe_after(lambda i=idx: self._update_row(i))

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------

    def _on_right_click(self, event):
        item = self._tree.identify_row(event.y)
        if not item:
            return
        idx = int(item)
        job = self._jobs[idx]

        menu = tk.Menu(self, tearoff=0,
                       bg=PALETTE["bg_card"],
                       fg=PALETTE["text_primary"],
                       activebackground=PALETTE["accent_blue"],
                       activeforeground="#000000",
                       font=("Segoe UI", 10))

        if job.status == JobStatus.WAITING:
            menu.add_command(label="Skip this song",
                             command=lambda: self._skip_job(idx))
        if job.status in (JobStatus.ERROR, JobStatus.SKIPPED):
            menu.add_command(label="Retry",
                             command=lambda: self._retry_job(idx))
        menu.add_separator()
        menu.add_command(label="Remove from queue",
                         command=lambda: self._remove_job(idx))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _skip_job(self, idx: int):
        self._set_job(idx, JobStatus.SKIPPED, "Manually skipped")

    def _retry_job(self, idx: int):
        if 0 <= idx < len(self._jobs):
            self._jobs[idx].status   = JobStatus.WAITING
            self._jobs[idx].note     = ""
            self._jobs[idx].progress = 0.0
            self._safe_after(lambda: self._update_row(idx))

    def _remove_job(self, idx: int):
        if 0 <= idx < len(self._jobs):
            iid = str(idx)
            if self._tree.exists(iid):
                self._tree.delete(iid)
            self._jobs[idx].status = JobStatus.SKIPPED
