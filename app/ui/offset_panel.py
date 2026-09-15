"""
offset_panel.py
---------------
Right-pane "Sync & Offset" tab.

Shows after a video has been downloaded:
  - Detected offset value and confidence level
  - Visual offset indicator bar
  - Manual adjustment slider (±10 seconds, 10ms steps)
  - Live numeric readout of the current offset value
  - "Apply & Save" button → writes video_start_time to song.ini
  - "Re-run Sync" button → re-runs cross-correlation
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import customtkinter as ctk

from app.setup.first_run import PALETTE
from app.core.song_scanner import SongEntry
from app.core.audio_sync import SyncResult, compute_offset
from app.setup.dependency_check import get_ffmpeg_path


class OffsetPanel(ctk.CTkFrame):
    """Right-pane Sync & Offset tab."""

    SLIDER_MIN_MS = -15000    # -15 seconds
    SLIDER_MAX_MS =  15000    # +15 seconds

    def __init__(self, parent, state, status_cb: Callable[[str, float], None], **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app_state = state
        self.status_cb = status_cb
        self._song: Optional[SongEntry] = None
        self._sync_result: Optional[SyncResult] = None

        self.on_apply: Optional[Callable[[SongEntry, int], None]] = None

        self._build_ui()
        self._show_idle()

    def _safe_after(self, fn):
        """Post fn() to the main thread only if this widget still exists."""
        try:
            if self.winfo_exists():
                self.after(0, fn)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        P = PALETTE

        # Content container (centered)
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=20, pady=20)

        # ── Title ─────────────────────────────────────────────────────
        ctk.CTkLabel(
            self.content,
            text="Video Sync & Offset",
            font=ctk.CTkFont(family="Segoe UI Black", size=18, weight="bold"),
            text_color=P["accent_blue"],
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            self.content,
            text="Fine-tune the alignment between the video and the song audio.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # ── Status card ───────────────────────────────────────────────
        self.status_card = ctk.CTkFrame(
            self.content,
            fg_color=P["bg_card"],
            corner_radius=10,
            border_color=P["border"],
            border_width=1,
        )
        self.status_card.pack(fill="x", pady=(0, 16))

        inner = ctk.CTkFrame(self.status_card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        # Song name
        self.song_name_lbl = ctk.CTkLabel(
            inner,
            text="No song selected",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        )
        self.song_name_lbl.pack(fill="x")

        # Offset detected row
        row1 = ctk.CTkFrame(inner, fg_color="transparent")
        row1.pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(
            row1,
            text="Detected offset:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            width=130,
            anchor="w",
        ).pack(side="left")

        self.detected_lbl = ctk.CTkLabel(
            row1,
            text="—",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color=P["accent_cyan"],
            anchor="w",
        )
        self.detected_lbl.pack(side="left")

        # Confidence row
        row2 = ctk.CTkFrame(inner, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            row2,
            text="Confidence:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            width=130,
            anchor="w",
        ).pack(side="left")

        self.confidence_lbl = ctk.CTkLabel(
            row2,
            text="—",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_dim"],
            anchor="w",
        )
        self.confidence_lbl.pack(side="left")

        # Confidence progress bar
        self.conf_bar = ctk.CTkProgressBar(
            inner,
            height=6,
            fg_color=P["bg_panel"],
            progress_color=P["accent_blue"],
        )
        self.conf_bar.set(0)
        self.conf_bar.pack(fill="x", pady=(8, 0))

        # ── Manual adjustment ─────────────────────────────────────────
        adj_card = ctk.CTkFrame(
            self.content,
            fg_color=P["bg_card"],
            corner_radius=10,
            border_color=P["border"],
            border_width=1,
        )
        adj_card.pack(fill="x", pady=(0, 16))

        adj_inner = ctk.CTkFrame(adj_card, fg_color="transparent")
        adj_inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(
            adj_inner,
            text="Manual Adjustment",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            adj_inner,
            text="Positive = skip into video (video leads)  •  Negative = delay video (audio leads)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"],
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        # Offset display + fine-tune buttons
        fine_row = ctk.CTkFrame(adj_inner, fg_color="transparent")
        fine_row.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            fine_row,
            text="− 100ms",
            width=80,
            height=30,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=P["bg_panel"],
            hover_color=P["bg_card_hover"],
            border_color=P["border"],
            border_width=1,
            text_color=P["text_secondary"],
            command=lambda: self._nudge(-100),
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            fine_row,
            text="− 10ms",
            width=70,
            height=30,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=P["bg_panel"],
            hover_color=P["bg_card_hover"],
            border_color=P["border"],
            border_width=1,
            text_color=P["text_secondary"],
            command=lambda: self._nudge(-10),
        ).pack(side="left", padx=(0, 8))

        self.offset_display = ctk.CTkLabel(
            fine_row,
            text="0 ms",
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
            text_color=P["accent_blue"],
            width=120,
            anchor="center",
        )
        self.offset_display.pack(side="left", expand=True)

        ctk.CTkButton(
            fine_row,
            text="+ 10ms",
            width=70,
            height=30,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=P["bg_panel"],
            hover_color=P["bg_card_hover"],
            border_color=P["border"],
            border_width=1,
            text_color=P["text_secondary"],
            command=lambda: self._nudge(10),
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            fine_row,
            text="+ 100ms",
            width=80,
            height=30,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=P["bg_panel"],
            hover_color=P["bg_card_hover"],
            border_color=P["border"],
            border_width=1,
            text_color=P["text_secondary"],
            command=lambda: self._nudge(100),
        ).pack(side="right", padx=(4, 0))

        # Slider
        self.slider_var = ctk.DoubleVar(value=0)
        self.slider = ctk.CTkSlider(
            adj_inner,
            from_=self.SLIDER_MIN_MS,
            to=self.SLIDER_MAX_MS,
            variable=self.slider_var,
            number_of_steps=int((self.SLIDER_MAX_MS - self.SLIDER_MIN_MS) / 10),
            button_color=P["accent_blue"],
            button_hover_color=P["accent_cyan"],
            progress_color=P["accent_blue"],
            fg_color=P["bg_panel"],
            command=self._on_slider_change,
        )
        self.slider.pack(fill="x", pady=(0, 4))

        # Slider endpoint labels
        lbl_row = ctk.CTkFrame(adj_inner, fg_color="transparent")
        lbl_row.pack(fill="x")
        ctk.CTkLabel(
            lbl_row,
            text=f"{self.SLIDER_MIN_MS // 1000}s",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=P["text_dim"],
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            lbl_row,
            text="0",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=P["text_dim"],
            anchor="center",
        ).pack(side="left", expand=True)
        ctk.CTkLabel(
            lbl_row,
            text=f"+{self.SLIDER_MAX_MS // 1000}s",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=P["text_dim"],
            anchor="e",
        ).pack(side="right")

        # ── Action buttons ────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self.content, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        self.apply_btn = ctk.CTkButton(
            btn_row,
            text="Apply & Save to song.ini",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=PALETTE["success"],
            hover_color="#00b85a",
            text_color="#000000",
            state="disabled",
            command=self._do_apply,
        )
        self.apply_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.resync_btn = ctk.CTkButton(
            btn_row,
            text="Re-run Sync",
            width=120,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=PALETTE["accent_purple"],
            hover_color=PALETTE["accent_blue"],
            state="disabled",
            command=self._do_resync,
        )
        self.resync_btn.pack(side="left")

        # ── Sync log ──────────────────────────────────────────────────
        self.log_box = ctk.CTkTextbox(
            self.content,
            height=80,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=PALETTE["bg_panel"],
            text_color=PALETTE["text_secondary"],
            border_color=PALETTE["border"],
            border_width=1,
            state="disabled",
        )
        self.log_box.pack(fill="x")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self):
        """Reset to idle state (new song selected but not yet downloaded)."""
        self._song = None
        self._sync_result = None
        self._show_idle()

    def show_no_sync(self, reason: str = ""):
        """Show state when sync cannot run (missing ffmpeg or stems)."""
        self._log(f"Audio sync unavailable: {reason}")
        self.apply_btn.configure(state="normal")
        self.resync_btn.configure(state="disabled")
        self.song_name_lbl.configure(text=self._song.display_name if self._song else "")
        self.detected_lbl.configure(text="N/A")
        self.confidence_lbl.configure(text=reason, text_color=PALETTE["warning"])

    def show_result(self, song: SongEntry, result: SyncResult):
        """Populate panel after successful download + sync."""
        self._song = song
        self._sync_result = result
        self.app_state.sync_result = result

        # Populate detected info
        self.song_name_lbl.configure(text=song.display_name)

        if result.success:
            self.detected_lbl.configure(
                text=result.offset_display,
                text_color=PALETTE["accent_cyan"],
            )
            conf_color = (
                PALETTE["success"] if result.confidence >= 0.85
                else PALETTE["warning"] if result.confidence >= 0.55
                else PALETTE["danger"]
            )
            self.confidence_lbl.configure(
                text=f"{result.confidence_label}  ({result.confidence:.0%})",
                text_color=conf_color,
            )
            self.conf_bar.set(result.confidence)
            self.conf_bar.configure(progress_color=conf_color)

            # Set slider to detected value
            clamped = max(self.SLIDER_MIN_MS, min(self.SLIDER_MAX_MS, result.offset_ms))
            self.slider_var.set(clamped)
            self._update_offset_display(clamped)
            self._log(f"Sync complete: {result.offset_display}  [{result.confidence_label} confidence]")
        else:
            self.detected_lbl.configure(text="Failed", text_color=PALETTE["danger"])
            self.confidence_lbl.configure(text=result.error, text_color=PALETTE["danger"])
            self.conf_bar.set(0)
            self._log(f"Sync failed: {result.error}")

        self.apply_btn.configure(state="normal")
        self.resync_btn.configure(state="normal")
        self.slider.configure(state="normal")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _show_idle(self):
        self.song_name_lbl.configure(text="Download a video to enable sync")
        self.detected_lbl.configure(text="—", text_color=PALETTE["accent_cyan"])
        self.confidence_lbl.configure(text="—", text_color=PALETTE["text_dim"])
        self.conf_bar.set(0)
        self.slider_var.set(0)
        self._update_offset_display(0)
        self.apply_btn.configure(state="disabled")
        self.resync_btn.configure(state="disabled")
        self.slider.configure(state="disabled")

    def _update_offset_display(self, ms: int):
        sign = "+" if ms >= 0 else ""
        self.offset_display.configure(text=f"{sign}{ms} ms")

    def _on_slider_change(self, value: float):
        ms = int(round(value / 10) * 10)   # snap to 10ms
        self.slider_var.set(ms)
        self._update_offset_display(ms)

    def _nudge(self, delta_ms: int):
        current = int(self.slider_var.get())
        new_val = max(self.SLIDER_MIN_MS, min(self.SLIDER_MAX_MS, current + delta_ms))
        self.slider_var.set(new_val)
        self._update_offset_display(new_val)

    def _log(self, msg: str):
        """Append to log textbox — thread-safe via _safe_after."""
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self._safe_after(_do)

    def _do_apply(self):
        if not self._song:
            return
        ms = int(self.slider_var.get())
        if self.on_apply:
            self.on_apply(self._song, ms)
        self._log(f"Saved video_start_time = {ms:+d} ms")

    def _do_resync(self):
        if not self._song or not self._song.video_path:
            return

        stem = self._song.best_audio_stem()
        ffmpeg = get_ffmpeg_path()

        if not stem:
            self._log("No audio stem found for re-sync.")
            return
        if not ffmpeg:
            self._log("ffmpeg not available for re-sync.")
            return

        self.apply_btn.configure(state="disabled")
        self.resync_btn.configure(state="disabled", text="Syncing...")
        self._log("Re-running audio sync...")

        def _worker():
            result = compute_offset(
                video_path=self._song.video_path,
                stem_path=stem,
                ffmpeg_path=ffmpeg,
                progress_cb=self._log,
            )
            self._safe_after(lambda: self.show_result(self._song, result))

        threading.Thread(target=_worker, daemon=True).start()
