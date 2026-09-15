"""
search_panel.py
---------------
Right-pane "Search YouTube" tab.

Features:
  - Auto-populates search query from song metadata when a song is selected
  - Editable query field + Search button
  - Displays up to 8 results as cards in a scrollable grid
  - Each card: thumbnail image, title, channel, duration, view count
  - Thumbnail images loaded asynchronously (no UI freeze)
  - "Select" button on each card triggers download in the main window
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image

from app.setup.first_run import PALETTE
from app.core.song_scanner import SongEntry
from app.core.downloader import VideoResult, search_youtube, fetch_thumbnail
from app.setup.dependency_check import get_deno_path


# ---------------------------------------------------------------------------
# Single result card
# ---------------------------------------------------------------------------

class VideoCard(ctk.CTkFrame):
    """A single YouTube result card."""

    THUMB_W = 213
    THUMB_H = 120

    def __init__(self, parent, video: VideoResult, on_select: Callable[[VideoResult], None]):
        super().__init__(
            parent,
            fg_color=PALETTE["bg_card"],
            corner_radius=10,
            border_color=PALETTE["border"],
            border_width=1,
        )
        self.video = video
        self.on_select = on_select
        self._build_ui()

    def _build_ui(self):
        P = PALETTE

        # Thumbnail placeholder
        self.thumb_label = ctk.CTkLabel(
            self,
            text="Loading...",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"],
            fg_color=P["bg_panel"],
            width=self.THUMB_W,
            height=self.THUMB_H,
            corner_radius=6,
        )
        self.thumb_label.pack(padx=8, pady=(8, 4))

        # Title
        ctk.CTkLabel(
            self,
            text=self.video.title,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=P["text_primary"],
            wraplength=self.THUMB_W,
            justify="left",
            anchor="w",
        ).pack(padx=8, pady=(0, 2), fill="x")

        # Channel + duration row
        meta_row = ctk.CTkFrame(self, fg_color="transparent")
        meta_row.pack(fill="x", padx=8, pady=(0, 2))

        ctk.CTkLabel(
            meta_row,
            text=self.video.channel,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_secondary"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            meta_row,
            text=self.video.duration_fmt,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["accent_cyan"],
            anchor="e",
        ).pack(side="right")

        # View count
        ctk.CTkLabel(
            self,
            text=self.video.view_count_fmt,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"],
            anchor="w",
        ).pack(padx=8, pady=(0, 6), fill="x")

        # Select button
        ctk.CTkButton(
            self,
            text="Download This Video",
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=P["accent_blue"],
            hover_color=P["accent_cyan"],
            text_color="#000000",
            corner_radius=6,
            command=lambda: self.on_select(self.video),
        ).pack(padx=8, pady=(0, 8), fill="x")

        # Hover highlight
        self.bind("<Enter>", lambda e: self.configure(fg_color=PALETTE["bg_card_hover"]))
        self.bind("<Leave>", lambda e: self.configure(fg_color=PALETTE["bg_card"]))

    def set_thumbnail(self, img: Optional[Image.Image]):
        """Update the thumbnail image (called from main thread)."""
        if img is None:
            return
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                               size=(self.THUMB_W, self.THUMB_H))
        self.thumb_label.configure(image=ctk_img, text="")
        self.thumb_label._image = ctk_img   # prevent GC


# ---------------------------------------------------------------------------
# Search Panel
# ---------------------------------------------------------------------------

class SearchPanel(ctk.CTkFrame):
    """Right-pane Search tab."""

    CARDS_PER_ROW = 4

    def __init__(self, parent, state, status_cb: Callable[[str, float], None], **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app_state = state
        self.status_cb = status_cb
        self._current_song: Optional[SongEntry] = None
        self._cards: list[VideoCard] = []

        self.on_video_selected: Optional[Callable[[VideoResult], None]] = None

        self._build_ui()

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

        # ── Top: search bar ───────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 6))

        self.query_var = ctk.StringVar()
        self.query_entry = ctk.CTkEntry(
            top,
            textvariable=self.query_var,
            placeholder_text="Select a song first, or type a search query...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=P["bg_card"],
            border_color=P["border"],
            text_color=P["text_primary"],
            placeholder_text_color=P["text_dim"],
            height=40,
        )
        self.query_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.query_entry.bind("<Return>", lambda e: self._do_search())

        self.search_btn = ctk.CTkButton(
            top,
            text="Search",
            width=100,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=P["accent_blue"],
            hover_color=P["accent_cyan"],
            text_color="#000000",
            command=self._do_search,
        )
        self.search_btn.pack(side="left")

        # ── Song context info ─────────────────────────────────────────
        self.context_lbl = ctk.CTkLabel(
            self,
            text="No song selected  —  click a song in the library to begin",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_dim"],
            anchor="w",
        )
        self.context_lbl.pack(fill="x", padx=14, pady=(0, 8))

        # ── Scrollable results grid ───────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=P["bg_card_hover"],
            scrollbar_button_hover_color=P["accent_blue"],
        )
        self.scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Grid layout inside scroll frame
        self.grid_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True)

        # Show initial empty state
        self._show_empty("Select a song from the library, then click Search.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_song(self, song: SongEntry):
        """Called by main window when user selects a song."""
        self._current_song = song

        # Respect query_template from config if available
        template = self.app_state.config.get(
            "query_template", "{artist} {title} official music video"
        )
        try:
            query = template.format(
                artist=song.artist or "",
                title=song.title or song.folder.name,
            ).strip()
        except (KeyError, IndexError):
            query = song.search_query
        self.query_var.set(query)

        has = "Video present" if song.has_video else "No video"
        self.context_lbl.configure(
            text=f"{song.display_name}  |  {has}  |  Click Search or edit the query above",
            text_color=PALETTE["text_secondary"],
        )
        self._do_search()

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------

    def _do_search(self):
        query = self.query_var.get().strip()
        if not query:
            return

        self._show_loading()
        self.search_btn.configure(state="disabled", text="Searching...")
        self.status_cb("Searching YouTube...", 0.05)

        deno_path   = get_deno_path()
        max_results = int(self.app_state.config.get("max_results", 8))

        def _worker():
            try:
                results = search_youtube(query, max_results=max_results, deno_path=deno_path)
            except RuntimeError as exc:
                def _err():
                    self._show_empty(f"Search failed: {exc}")
                    self.search_btn.configure(state="normal", text="Search")
                    self.status_cb(f"Search failed: {exc}", 0)
                self._safe_after(_err)
                return

            def _show():
                self._display_results(results)
                self.search_btn.configure(state="normal", text="Search")
                self.status_cb(f"Found {len(results)} results for: {query}", 0)
            self._safe_after(_show)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Results display
    # ------------------------------------------------------------------

    def _clear_grid(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self._cards.clear()

    def _show_empty(self, message: str):
        self._clear_grid()
        ctk.CTkLabel(
            self.grid_frame,
            text=message,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=PALETTE["text_dim"],
        ).pack(pady=40)

    def _show_loading(self):
        self._clear_grid()
        ctk.CTkLabel(
            self.grid_frame,
            text="Searching YouTube...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=PALETTE["text_secondary"],
        ).pack(pady=40)

    def _display_results(self, results: list[VideoResult]):
        self._clear_grid()

        if not results:
            self._show_empty("No results found. Try a different search query.")
            return

        # Grid layout: CARDS_PER_ROW columns
        n = self.CARDS_PER_ROW
        for i, video in enumerate(results):
            row_idx = i // n
            col_idx = i % n

            card = VideoCard(
                self.grid_frame,
                video=video,
                on_select=self._video_chosen,
            )
            card.grid(row=row_idx, column=col_idx, padx=6, pady=6, sticky="nsew")
            self._cards.append(card)

            # Load thumbnail in background
            self._load_thumb_async(card, video.video_id)

        # Make columns equal width
        for c in range(n):
            self.grid_frame.columnconfigure(c, weight=1)

    def _load_thumb_async(self, card: VideoCard, video_id: str):
        def _fetch():
            img = fetch_thumbnail(video_id)
            if img:
                self._safe_after(lambda: card.set_thumbnail(img))
        threading.Thread(target=_fetch, daemon=True).start()

    def _video_chosen(self, video: VideoResult):
        if not self._current_song:
            from tkinter import messagebox
            messagebox.showwarning("No Song Selected", "Please select a song from the library first.")
            return
        if self.on_video_selected:
            self.on_video_selected(video)
