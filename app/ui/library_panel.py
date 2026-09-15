"""
library_panel.py
----------------
Left-side song library panel.

Uses a native tk.Listbox for the song list — single widget, zero lag,
hardware-accelerated scrolling, handles thousands of songs instantly.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

import customtkinter as ctk

from app.setup.first_run import PALETTE
from app.core.song_scanner import SongEntry


class LibraryPanel(ctk.CTkFrame):
    """Left panel: song library with a native tk.Listbox for fast scrolling."""

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
        self.app_state = state
        self.on_song_selected: Optional[Callable[[SongEntry], None]] = None

        self._all_songs: list[SongEntry] = []
        self._filtered_songs: list[SongEntry] = []
        self._selected_index: Optional[int] = None

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

        ctk.CTkFrame(hdr, fg_color=P["accent_purple"], height=2,
                     corner_radius=0).pack(fill="x", side="top")

        hdr_inner = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_inner.pack(fill="both", expand=True, padx=14)

        ctk.CTkLabel(
            hdr_inner,
            text="LIBRARY",
            font=ctk.CTkFont(family="Segoe UI Black", size=11, weight="bold"),
            text_color=P["text_secondary"],
            anchor="w",
        ).pack(side="left", fill="y")

        self.count_badge = ctk.CTkFrame(
            hdr_inner, fg_color=P["accent_blue"],
            corner_radius=10, height=22, width=44,
        )
        self.count_badge.pack(side="right", pady=14)
        self.count_badge.pack_propagate(False)

        self.count_lbl = ctk.CTkLabel(
            self.count_badge, text="0",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#000000",
        )
        self.count_lbl.pack(fill="both", expand=True)

        # ── Search bar ────────────────────────────────────────────────
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=(10, 4))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())

        ctk.CTkEntry(
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
        ).pack(fill="x")

        # ── Filter toggle ─────────────────────────────────────────────
        toggle_row = ctk.CTkFrame(self, fg_color="transparent")
        toggle_row.pack(fill="x", padx=12, pady=(2, 6))

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

        # ── Listbox + scrollbar ───────────────────────────────────────
        list_frame = tk.Frame(self, bg=P["bg_dark"])
        list_frame.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        # Try to get a nice font; fall back to default
        try:
            list_font = tkfont.Font(family="Segoe UI", size=11)
        except Exception:
            list_font = tkfont.Font(size=11)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=list_font,
            bg=PALETTE["bg_panel"],
            fg=PALETTE["text_primary"],
            selectbackground=PALETTE["accent_blue"],
            selectforeground="#000000",
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            cursor="hand2",
        )
        self._listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._listbox.yview)

        # Mouse wheel scroll (Windows uses delta, Linux uses Button-4/5)
        self._listbox.bind("<MouseWheel>",
                           lambda e: self._listbox.yview_scroll(
                               int(-1 * (e.delta / 120)), "units"))
        self._listbox.bind("<Button-4>",
                           lambda e: self._listbox.yview_scroll(-1, "units"))
        self._listbox.bind("<Button-5>",
                           lambda e: self._listbox.yview_scroll(1, "units"))

        # Selection
        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

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
        self._render_listbox()

    def _render_listbox(self):
        """Repopulate the Listbox — single bulk insert, extremely fast."""
        self._listbox.delete(0, "end")
        self._selected_index = None

        n = len(self._filtered_songs)
        self.count_lbl.configure(text=str(n))
        self.count_badge.configure(
            fg_color=PALETTE["accent_blue"] if n > 0 else PALETTE["text_dim"]
        )

        # Build display strings — prefix with ▶ if video present
        for song in self._filtered_songs:
            has_vid  = "▶ " if song.has_video else "  "
            artist   = song.artist or "Unknown Artist"
            title    = song.title  or song.folder.name
            display  = f"{has_vid}{artist}  —  {title}"
            self._listbox.insert("end", display)

        # Colour rows: green tint for songs with video, normal for missing
        for i, song in enumerate(self._filtered_songs):
            if song.has_video:
                self._listbox.itemconfig(
                    i,
                    fg=PALETTE["success"],
                    selectforeground="#000000",
                )
            else:
                self._listbox.itemconfig(
                    i,
                    fg=PALETTE["text_primary"],
                    selectforeground="#000000",
                )

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_listbox_select(self, _event):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._filtered_songs):
            return
        self._selected_index = idx
        song = self._filtered_songs[idx]
        if self.on_song_selected:
            self.on_song_selected(song)
