"""
library_panel.py
----------------
Left-side song library panel.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from app.setup.first_run import PALETTE
from app.core.song_scanner import SongEntry


class LibraryPanel(ctk.CTkFrame):
    """Left panel: song library list with filter controls."""

    PANEL_WIDTH = 330

    def __init__(self, parent, state, **kwargs):
        super().__init__(
            parent,
            width=self.PANEL_WIDTH,
            fg_color=PALETTE["bg_panel"],
            corner_radius=12,
            border_color=PALETTE["border"],
            border_width=1,
            **kwargs,
        )
        self.pack_propagate(False)
        self.state = state
        self.on_song_selected: Optional[Callable[[SongEntry], None]] = None

        self._all_songs: list[SongEntry] = []
        self._filtered_songs: list[SongEntry] = []
        self._selected_index: Optional[int] = None
        self._row_frames: list[ctk.CTkFrame] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        P = PALETTE

        # ── Panel header ──────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=P["bg_card"], corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Top accent line
        ctk.CTkFrame(hdr, fg_color=P["accent_purple"], height=2, corner_radius=0).pack(
            fill="x", side="top"
        )

        hdr_inner = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_inner.pack(fill="both", expand=True, padx=14)

        ctk.CTkLabel(
            hdr_inner,
            text="LIBRARY",
            font=ctk.CTkFont(family="Segoe UI Black", size=11, weight="bold"),
            text_color=P["text_secondary"],
            anchor="w",
        ).pack(side="left", fill="y")

        # Count badge
        self.count_badge = ctk.CTkFrame(
            hdr_inner,
            fg_color=P["accent_blue"],
            corner_radius=10,
            height=22,
            width=38,
        )
        self.count_badge.pack(side="right", pady=14)
        self.count_badge.pack_propagate(False)

        self.count_lbl = ctk.CTkLabel(
            self.count_badge,
            text="0",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#000000",
        )
        self.count_lbl.pack(fill="both", expand=True)

        # ── Search bar ────────────────────────────────────────────────
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=(10, 4))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())

        search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            placeholder_text="  Search songs...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=P["bg_card"],
            border_color=P["border"],
            text_color=P["text_primary"],
            placeholder_text_color=P["text_dim"],
            height=36,
            corner_radius=18,
        )
        search_entry.pack(fill="x")

        # ── Filter toggle ─────────────────────────────────────────────
        toggle_row = ctk.CTkFrame(self, fg_color="transparent")
        toggle_row.pack(fill="x", padx=12, pady=(2, 8))

        self.missing_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            toggle_row,
            text="Missing video only",
            variable=self.missing_only_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            fg_color=P["accent_blue"],
            hover_color=P["accent_cyan"],
            checkmark_color=P["bg_dark"],
            border_color=P["border"],
            command=self._apply_filter,
        ).pack(side="left")

        # ── Scrollable list ───────────────────────────────────────────
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=P["bg_card_hover"],
            scrollbar_button_hover_color=P["accent_blue"],
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=6, pady=(0, 8))

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self, songs: list[SongEntry]):
        self._all_songs = songs
        self._selected_index = None
        self._apply_filter()

    def _apply_filter(self):
        query = self.search_var.get().lower().strip()
        missing_only = self.missing_only_var.get()

        filtered = self._all_songs
        if missing_only:
            filtered = [s for s in filtered if not s.has_video]
        if query:
            filtered = [
                s for s in filtered
                if query in s.title.lower() or query in s.artist.lower()
            ]

        self._filtered_songs = filtered
        self._render_list()

    def _render_list(self):
        for child in self.scroll_frame.winfo_children():
            child.destroy()
        self._row_frames.clear()
        self._selected_index = None

        P = PALETTE
        total = len(self._filtered_songs)

        # Update count badge
        self.count_lbl.configure(text=str(total))
        badge_color = P["accent_blue"] if total > 0 else P["text_dim"]
        self.count_badge.configure(fg_color=badge_color)

        for idx, song in enumerate(self._filtered_songs):
            row = self._make_row(idx, song)
            row.pack(fill="x", padx=4, pady=2)
            self._row_frames.append(row)

        if not self._filtered_songs:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No songs found",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=P["text_dim"],
            ).pack(pady=30)

    def _make_row(self, idx: int, song: SongEntry) -> ctk.CTkFrame:
        P = PALETTE

        row = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=P["bg_card"],
            corner_radius=8,
            height=58,
            cursor="hand2",
        )
        row.pack_propagate(False)

        # Left accent bar (colored by video status)
        bar_color = P["success"] if song.has_video else P["danger"]
        ctk.CTkFrame(
            row,
            fg_color=bar_color,
            width=4,
            corner_radius=2,
        ).place(x=0, y=6, relheight=1, height=-12)

        # Text block
        text_frame = ctk.CTkFrame(row, fg_color="transparent")
        text_frame.place(x=14, y=0, relwidth=0.95, relheight=1.0)

        artist_lbl = ctk.CTkLabel(
            text_frame,
            text=song.artist or "Unknown Artist",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_secondary"],
            anchor="w",
        )
        artist_lbl.place(x=0, y=10, relwidth=1.0)

        title_lbl = ctk.CTkLabel(
            text_frame,
            text=song.title or song.folder.name,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        )
        title_lbl.place(x=0, y=28, relwidth=1.0)

        # Video badge on right
        if song.has_video:
            badge = ctk.CTkFrame(row, fg_color="#0a2a1a", corner_radius=4, width=20, height=14)
            badge.place(relx=1.0, rely=0.5, x=-10, anchor="e")
            ctk.CTkLabel(
                badge,
                text="▶",
                font=ctk.CTkFont(family="Segoe UI", size=8),
                text_color=P["success"],
            ).place(relx=0.5, rely=0.5, anchor="center")

        # Bind events on all child widgets
        for widget in [row, text_frame, artist_lbl, title_lbl]:
            widget.bind("<Button-1>", lambda e, i=idx: self._select_row(i))
            widget.bind("<Enter>", lambda e, r=row, i=idx: self._on_hover(r, True, i))
            widget.bind("<Leave>", lambda e, r=row, i=idx: self._on_hover(r, False, i))

        return row

    def _select_row(self, idx: int):
        if idx < 0 or idx >= len(self._filtered_songs):
            return

        # Deselect previous
        if self._selected_index is not None and self._selected_index < len(self._row_frames):
            self._row_frames[self._selected_index].configure(fg_color=PALETTE["bg_card"])

        self._selected_index = idx
        self._row_frames[idx].configure(fg_color="#0d2245")  # deep blue selected

        song = self._filtered_songs[idx]
        if self.on_song_selected:
            self.on_song_selected(song)

    def _on_hover(self, row: ctk.CTkFrame, entering: bool, idx: Optional[int] = None):
        is_selected = (idx is not None and idx == self._selected_index)
        if is_selected:
            return
        row.configure(fg_color=PALETTE["bg_card_hover"] if entering else PALETTE["bg_card"])
