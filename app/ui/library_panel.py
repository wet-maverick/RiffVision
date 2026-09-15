"""
library_panel.py
----------------
Left-side song library panel — virtualised for performance.

Instead of creating one CTkFrame per song (hundreds of widgets = slow),
we maintain a small fixed pool of row widgets (~20) and rebind them to
different songs as the user scrolls. This is a recycling-list pattern
identical to what Android RecyclerView / iOS UITableView use.

Result: silky-smooth scrolling regardless of library size.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from app.setup.first_run import PALETTE
from app.core.song_scanner import SongEntry

ROW_H      = 60    # px height of each row
POOL_EXTRA = 4     # extra rows above/below visible area to pre-render

# Plain tk colors for the row shell (tk.Frame uses bg=, not fg_color=)
_COL_ROW_NORMAL   = PALETTE["bg_card"]       # "#151e33"
_COL_ROW_HOVER    = PALETTE["bg_card_hover"] # "#1a2540"
_COL_ROW_SELECTED = "#0d2245"


class _SongRow(tk.Frame):
    """
    A single reusable row widget. Extends plain tk.Frame so that
    .place(width=, height=) works without CustomTkinter's restriction.
    Inner content widgets are still CTk for styling.
    Call bind_song() to rebind to a different SongEntry.
    """

    def __init__(self, parent, on_click: Callable[[int], None],
                 on_enter: Callable[[int], None],
                 on_leave: Callable[[int], None]):
        super().__init__(
            parent,
            bg=_COL_ROW_NORMAL,
            cursor="hand2",
        )
        self._on_click = on_click
        self._on_enter = on_enter
        self._on_leave = on_leave
        self._idx: int = -1

        P = PALETTE

        # Accent bar — CTkFrame inside plain tk.Frame is fine
        self._accent = ctk.CTkFrame(self, fg_color=P["success"], width=4, corner_radius=2)
        self._accent.pack(side="left", fill="y", padx=(2, 0), pady=6)

        # Text block
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.pack(side="left", fill="both", expand=True, padx=(8, 4))

        self._artist_lbl = ctk.CTkLabel(
            text_frame, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_secondary"],
            anchor="w",
        )
        self._artist_lbl.pack(fill="x", pady=(8, 0))

        self._title_lbl = ctk.CTkLabel(
            text_frame, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        )
        self._title_lbl.pack(fill="x")

        # Video badge (always built, shown/hidden via pack)
        self._badge = ctk.CTkFrame(
            self, fg_color="#0a2a1a", corner_radius=4, width=22, height=22,
        )
        self._badge.pack_propagate(False)
        ctk.CTkLabel(
            self._badge, text="▶",
            font=ctk.CTkFont(family="Segoe UI", size=8),
            text_color=P["success"],
        ).pack(expand=True)

        # Bind events
        for w in [self, self._accent, text_frame, self._artist_lbl, self._title_lbl]:
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>",    self._enter)
            w.bind("<Leave>",    self._leave)

    def bind_song(self, idx: int, song: SongEntry, selected: bool):
        """Rebind this row to a new song — no widget creation."""
        P = PALETTE
        self._idx = idx
        self._artist_lbl.configure(text=song.artist or "Unknown Artist")
        self._title_lbl.configure(text=song.title or song.folder.name,
                                  text_color=P["text_primary"])
        self._accent.configure(fg_color=P["success"] if song.has_video else P["danger"])
        if song.has_video:
            self._badge.pack(side="right", padx=(0, 8))
        else:
            self._badge.pack_forget()
        self._set_bg(_COL_ROW_SELECTED if selected else _COL_ROW_NORMAL)

    def set_selected(self, selected: bool):
        self._set_bg(_COL_ROW_SELECTED if selected else _COL_ROW_NORMAL)

    def set_hovered(self, hovered: bool):
        self._set_bg(_COL_ROW_HOVER if hovered else _COL_ROW_NORMAL)

    def _set_bg(self, color: str):
        self.configure(bg=color)

    def _click(self, _e):
        if self._idx >= 0:
            self._on_click(self._idx)

    def _enter(self, _e):
        if self._idx >= 0:
            self._on_enter(self._idx)

    def _leave(self, _e):
        if self._idx >= 0:
            self._on_leave(self._idx)


class LibraryPanel(ctk.CTkFrame):
    """Left panel: song library list with virtualised rendering."""

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

        # Virtual list state
        self._first_visible: int = 0   # index of topmost rendered song
        self._pool: list[_SongRow] = []

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

        self.count_badge = ctk.CTkFrame(
            hdr_inner, fg_color=P["accent_blue"], corner_radius=10, height=22, width=44,
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

        # ── Virtual scroll area ───────────────────────────────────────
        # We use a plain tk.Canvas (NOT CTkScrollableFrame) so we can
        # control scrolling precisely without recreating widgets.
        scroll_container = ctk.CTkFrame(self, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        self._canvas = tk.Canvas(
            scroll_container,
            bg=PALETTE["bg_panel"],
            highlightthickness=0,
            bd=0,
        )

        self._scrollbar = ctk.CTkScrollbar(
            scroll_container,
            orientation="vertical",
            command=self._canvas.yview,
            button_color=PALETTE["bg_card_hover"],
            button_hover_color=PALETTE["accent_blue"],
        )
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        # Inner frame that holds the row widgets — sized to total list height
        self._inner = tk.Frame(self._canvas, bg=PALETTE["bg_panel"])
        self._canvas_window = self._canvas.create_window(
            0, 0, anchor="nw", window=self._inner
        )

        # Bind resize and scroll events
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._inner.bind("<Configure>", self._on_inner_resize)
        self._canvas.bind("<MouseWheel>",      self._on_mousewheel)
        self._canvas.bind("<Button-4>",        self._on_mousewheel)   # Linux scroll up
        self._canvas.bind("<Button-5>",        self._on_mousewheel)   # Linux scroll down
        self._inner.bind("<MouseWheel>",       self._on_mousewheel)

        # Empty state label
        self._empty_lbl = ctk.CTkLabel(
            self._inner,
            text="No songs found",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=PALETTE["text_dim"],
            fg_color="transparent",
        )

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self, songs: list[SongEntry]):
        self._all_songs = songs
        self._selected_index = None
        self._first_visible = 0
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
        self._first_visible = 0
        self._canvas.yview_moveto(0)
        self._rebuild_virtual()

    # ------------------------------------------------------------------
    # Virtual list implementation
    # ------------------------------------------------------------------

    def _visible_rows(self) -> int:
        """How many rows fit in the visible canvas height."""
        h = self._canvas.winfo_height()
        if h <= 1:
            h = 600   # fallback before first layout
        return max(1, h // ROW_H)

    def _pool_size(self) -> int:
        return self._visible_rows() + POOL_EXTRA * 2

    def _rebuild_virtual(self):
        """
        Called when the data set changes (new filter, new songs).
        Resizes the inner frame, resizes/creates the row pool,
        then fills from the current scroll position.
        """
        n = len(self._filtered_songs)

        # Update count badge
        self.count_lbl.configure(text=str(n))
        self.count_badge.configure(
            fg_color=PALETTE["accent_blue"] if n > 0 else PALETTE["text_dim"]
        )

        if n == 0:
            # Hide pool, show empty label
            for row in self._pool:
                row.place_forget()
            self._empty_lbl.place(x=10, y=20)
            self._canvas.configure(scrollregion=(0, 0, 0, 60))
            return

        self._empty_lbl.place_forget()

        # Resize inner frame to total list height so scrollbar is correct
        total_h = n * ROW_H + 4
        canvas_w = max(self._canvas.winfo_width() - 4, self.PANEL_WIDTH - 20)
        self._inner.configure(width=canvas_w, height=total_h)
        self._canvas.configure(scrollregion=(0, 0, canvas_w, total_h))

        # Grow pool if needed (never shrink — reuse is free)
        needed = self._pool_size()
        while len(self._pool) < needed:
            row = _SongRow(
                self._inner,
                on_click=self._select_row,
                on_enter=self._on_enter,
                on_leave=self._on_leave,
            )
            self._pool.append(row)

        self._fill_visible()

    def _fill_visible(self):
        """
        Place pool rows at the correct y positions for the current
        scroll offset. Rows outside the visible window are hidden.
        """
        n = len(self._filtered_songs)
        if n == 0:
            return

        canvas_h  = self._canvas.winfo_height()
        if canvas_h <= 1:
            canvas_h = 600
        canvas_w  = max(self._canvas.winfo_width() - 4, self.PANEL_WIDTH - 20)

        # Top index: which song is at y=0 of canvas (scroll offset)
        scroll_top = self._canvas.yview()[0]
        top_idx  = max(0, int(scroll_top * n * ROW_H / max(1, n * ROW_H)) )
        # More precisely:
        total_h  = n * ROW_H
        top_px   = scroll_top * total_h
        top_idx  = max(0, int(top_px // ROW_H) - POOL_EXTRA)
        bottom_idx = min(n - 1, top_idx + self._pool_size() - 1)

        # Assign songs to pool rows
        pool_idx = 0
        for song_idx in range(top_idx, bottom_idx + 1):
            if pool_idx >= len(self._pool):
                break
            row = self._pool[pool_idx]
            song = self._filtered_songs[song_idx]
            is_selected = (song_idx == self._selected_index)
            row.bind_song(song_idx, song, is_selected)

            y = song_idx * ROW_H + 2
            row.place(x=2, y=y, width=canvas_w - 4, height=ROW_H - 4)
            pool_idx += 1

        # Hide unused pool rows
        for i in range(pool_idx, len(self._pool)):
            self._pool[i].place_forget()
            self._pool[i]._idx = -1

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)
        self._fill_visible()

    def _on_inner_resize(self, event):
        self._canvas.configure(
            scrollregion=self._canvas.bbox("all")
        )

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            # Windows/macOS — delta is ±120 per notch
            units = -1 * (event.delta // 120)
            self._canvas.yview_scroll(units, "units")
        self._fill_visible()

    def _select_row(self, idx: int):
        if idx < 0 or idx >= len(self._filtered_songs):
            return

        prev = self._selected_index
        self._selected_index = idx

        # Update visuals for affected rows in the pool
        for row in self._pool:
            if row._idx == prev:
                row.set_selected(False)
            elif row._idx == idx:
                row.set_selected(True)

        song = self._filtered_songs[idx]
        if self.on_song_selected:
            self.on_song_selected(song)

    def _on_enter(self, idx: int):
        for row in self._pool:
            if row._idx == idx and idx != self._selected_index:
                row.set_hovered(True)

    def _on_leave(self, idx: int):
        for row in self._pool:
            if row._idx == idx and idx != self._selected_index:
                row.set_hovered(False)
