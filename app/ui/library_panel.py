"""
library_panel.py
----------------
Left-side song library panel.

Features:
  - Scrollable list of all songs found in the songs folder
  - Live filter: type to narrow by artist or title
  - Toggle: show only songs missing a background video
  - Each row: color-coded video indicator dot + artist/title
  - Click a row to select it (fires on_song_selected callback)
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from app.setup.first_run import PALETTE
from app.core.song_scanner import SongEntry


class LibraryPanel(ctk.CTkFrame):
    """Left panel: song library list with filter controls."""

    PANEL_WIDTH = 320

    def __init__(self, parent, state, **kwargs):
        super().__init__(
            parent,
            width=self.PANEL_WIDTH,
            fg_color=PALETTE["bg_panel"],
            corner_radius=10,
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

        # Header
        hdr = ctk.CTkFrame(self, fg_color=P["bg_card"], corner_radius=8, height=44)
        hdr.pack(fill="x", padx=10, pady=(10, 6))
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr,
            text="Song Library",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(side="left", padx=12, pady=10)

        self.count_lbl = ctk.CTkLabel(
            hdr,
            text="0",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_dim"],
            anchor="e",
        )
        self.count_lbl.pack(side="right", padx=12)

        # Search bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())

        search_entry = ctk.CTkEntry(
            self,
            textvariable=self.search_var,
            placeholder_text="Filter songs...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=P["bg_card"],
            border_color=P["border"],
            text_color=P["text_primary"],
            placeholder_text_color=P["text_dim"],
            height=34,
        )
        search_entry.pack(fill="x", padx=10, pady=(0, 4))

        # "Missing video only" toggle
        toggle_row = ctk.CTkFrame(self, fg_color="transparent")
        toggle_row.pack(fill="x", padx=10, pady=(0, 6))

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

        # Scrollable list
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
        """Reload the full song list."""
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
        """Clear and re-render all visible song rows."""
        # Destroy existing rows
        for child in self.scroll_frame.winfo_children():
            child.destroy()
        self._row_frames.clear()
        self._selected_index = None

        P = PALETTE
        total = len(self._filtered_songs)
        self.count_lbl.configure(text=str(total))

        for idx, song in enumerate(self._filtered_songs):
            row = self._make_row(idx, song)
            row.pack(fill="x", padx=2, pady=2)
            self._row_frames.append(row)

        if not self._filtered_songs:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No songs found",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=P["text_dim"],
            ).pack(pady=20)

    def _make_row(self, idx: int, song: SongEntry) -> ctk.CTkFrame:
        """Create a single song row frame."""
        P = PALETTE

        row = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=P["bg_card"],
            corner_radius=6,
            height=52,
            cursor="hand2",
        )
        row.pack_propagate(False)

        # Video indicator dot
        dot_color = P["success"] if song.has_video else P["danger"]
        dot = ctk.CTkFrame(row, width=6, height=6, fg_color=dot_color, corner_radius=3)
        dot.place(x=8, rely=0.5, anchor="w")

        # Text block
        text_frame = ctk.CTkFrame(row, fg_color="transparent")
        text_frame.place(x=22, rely=0.5, anchor="w", relwidth=0.92)

        artist_lbl = ctk.CTkLabel(
            text_frame,
            text=song.artist or "Unknown Artist",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_secondary"],
            anchor="w",
        )
        artist_lbl.pack(fill="x")

        title_lbl = ctk.CTkLabel(
            text_frame,
            text=song.title or song.folder.name,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        )
        title_lbl.pack(fill="x")

        # Bind click on all sub-widgets
        for widget in [row, text_frame, artist_lbl, title_lbl, dot]:
            widget.bind("<Button-1>", lambda e, i=idx: self._select_row(i))
            widget.bind("<Enter>", lambda e, r=row: self._on_hover(r, True))
            widget.bind("<Leave>", lambda e, r=row, i=idx: self._on_hover(r, False, i))

        return row

    def _select_row(self, idx: int):
        if idx < 0 or idx >= len(self._filtered_songs):
            return

        # Deselect previous
        if self._selected_index is not None and self._selected_index < len(self._row_frames):
            self._row_frames[self._selected_index].configure(fg_color=PALETTE["bg_card"])

        self._selected_index = idx
        self._row_frames[idx].configure(fg_color=PALETTE["accent_blue"])

        song = self._filtered_songs[idx]
        if self.on_song_selected:
            self.on_song_selected(song)

    def _on_hover(self, row: ctk.CTkFrame, entering: bool, idx: Optional[int] = None):
        is_selected = (idx is not None and idx == self._selected_index)
        if entering and not is_selected:
            row.configure(fg_color=PALETTE["bg_card_hover"])
        elif not entering and not is_selected:
            row.configure(fg_color=PALETTE["bg_card"])
