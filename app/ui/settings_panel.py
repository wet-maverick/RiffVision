"""
settings_panel.py
-----------------
Settings tab — user preferences stored in config.json.

Options:
  - Songs folder path
  - Auto-sync after download (on/off)
  - Max YouTube search results (1–15)
  - Search query format (artist + title, title only, custom template)
  - Auto-update yt-dlp on launch (on/off)
  - yt-dlp manual update button
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk
from tkinter import filedialog

from app.setup.first_run import PALETTE, save_config


class SettingsPanel(ctk.CTkFrame):
    """Settings tab."""

    def __init__(self, parent, app_state, status_cb: Callable[[str, float], None],
                 on_folder_change: Callable[[str], None], **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app_state       = app_state
        self.status_cb       = status_cb
        self.on_folder_change = on_folder_change
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

        # Scrollable container so settings don't get clipped on small windows
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=P["bg_card_hover"],
            scrollbar_button_hover_color=P["accent_blue"],
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(scroll, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Title ──────────────────────────────────────────────────────
        ctk.CTkLabel(
            inner,
            text="Settings",
            font=ctk.CTkFont(family="Segoe UI Black", size=18, weight="bold"),
            text_color=P["accent_blue"],
            anchor="w",
        ).pack(fill="x", pady=(0, 16))

        # ── Songs folder ───────────────────────────────────────────────
        self._section(inner, "Songs Folder")

        folder_card = self._card(inner)
        folder_inner = ctk.CTkFrame(folder_card, fg_color="transparent")
        folder_inner.pack(fill="x", padx=14, pady=12)

        self._folder_var = ctk.StringVar(
            value=self.app_state.config.get("songs_folder", "D:/CloneHeroSongs")
        )
        ctk.CTkEntry(
            folder_inner,
            textvariable=self._folder_var,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=P["bg_dark"],
            border_color=P["border"],
            text_color=P["accent_cyan"],
            height=36,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            folder_inner,
            text="Browse",
            width=90, height=36,
            fg_color=P["accent_purple"],
            hover_color=P["accent_blue"],
            corner_radius=6,
            command=self._browse_folder,
        ).pack(side="left")

        ctk.CTkButton(
            folder_inner,
            text="Apply",
            width=70, height=36,
            fg_color=P["accent_blue"],
            hover_color=P["accent_cyan"],
            text_color="#000000",
            corner_radius=6,
            command=self._apply_folder,
        ).pack(side="left", padx=(8, 0))

        # ── Download options ───────────────────────────────────────────
        self._section(inner, "Download Options")

        dl_card = self._card(inner)
        dl_inner = ctk.CTkFrame(dl_card, fg_color="transparent")
        dl_inner.pack(fill="x", padx=14, pady=12)

        # Auto-sync toggle
        self._auto_sync_var = ctk.BooleanVar(
            value=self.app_state.config.get("auto_sync", True)
        )
        self._row_toggle(
            dl_inner,
            label="Auto-sync after download",
            desc="Run audio cross-correlation offset detection automatically "
                 "after each video downloads.",
            var=self._auto_sync_var,
            command=self._save,
        )

        ctk.CTkFrame(dl_inner, fg_color=P["border"], height=1).pack(
            fill="x", pady=8
        )

        # Max search results
        results_row = ctk.CTkFrame(dl_inner, fg_color="transparent")
        results_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            results_row,
            text="Max search results",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(side="left", fill="y")

        self._max_results_var = ctk.IntVar(
            value=self.app_state.config.get("max_results", 8)
        )
        ctk.CTkSlider(
            results_row,
            from_=1, to=15,
            number_of_steps=14,
            variable=self._max_results_var,
            width=150,
            button_color=P["accent_blue"],
            button_hover_color=P["accent_cyan"],
            progress_color=P["accent_blue"],
            fg_color=P["bg_panel"],
            command=lambda v: (
                self._max_results_var.set(int(v)),
                self._max_results_lbl.configure(text=str(int(v))),
                self._save(),
            ),
        ).pack(side="right", padx=(12, 8))

        self._max_results_lbl = ctk.CTkLabel(
            results_row,
            text=str(self._max_results_var.get()),
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color=P["accent_cyan"],
            width=28,
            anchor="e",
        )
        self._max_results_lbl.pack(side="right")

        ctk.CTkFrame(dl_inner, fg_color=P["border"], height=1).pack(
            fill="x", pady=8
        )

        # Cookie browser for age-gated videos
        browser_row = ctk.CTkFrame(dl_inner, fg_color="transparent")
        browser_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            browser_row,
            text="Browser for cookies",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(side="left", fill="y")

        self._browser_var = ctk.StringVar(
            value=self.app_state.config.get("cookie_browser", "chrome")
        )
        ctk.CTkOptionMenu(
            browser_row,
            variable=self._browser_var,
            values=["chrome", "firefox", "edge", "brave", "opera", "none"],
            width=120, height=32,
            fg_color=P["bg_panel"],
            button_color=P["accent_blue"],
            button_hover_color=P["accent_cyan"],
            dropdown_fg_color=P["bg_card"],
            dropdown_hover_color=P["bg_card_hover"],
            text_color=P["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=lambda _: self._save(),
        ).pack(side="right")

        ctk.CTkLabel(
            dl_inner,
            text="Used to bypass age-restricted videos. Pick the browser you use for YouTube.\n"
                 "Select 'none' to disable (age-gated videos will fail to download).",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"],
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(2, 0))

        ctk.CTkFrame(dl_inner, fg_color=P["border"], height=1).pack(
            fill="x", pady=8
        )

        # Search query format
        query_row = ctk.CTkFrame(dl_inner, fg_color="transparent")
        query_row.pack(fill="x")

        ctk.CTkLabel(
            query_row,
            text="Search query template",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            dl_inner,
            text="Use {artist} and {title} as placeholders.  "
                 "Default: {artist} {title} official music video",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"],
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(2, 6))

        self._query_template_var = ctk.StringVar(
            value=self.app_state.config.get(
                "query_template", "{artist} {title} official music video"
            )
        )
        ctk.CTkEntry(
            dl_inner,
            textvariable=self._query_template_var,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=P["bg_dark"],
            border_color=P["border"],
            text_color=P["accent_cyan"],
            height=34,
        ).pack(fill="x")
        self._query_template_var.trace_add("write", lambda *_: self._save())

        # ── Maintenance ────────────────────────────────────────────────
        self._section(inner, "Maintenance")

        maint_card = self._card(inner)
        maint_inner = ctk.CTkFrame(maint_card, fg_color="transparent")
        maint_inner.pack(fill="x", padx=14, pady=12)

        # Auto-update yt-dlp on launch
        self._auto_update_var = ctk.BooleanVar(
            value=self.app_state.config.get("auto_update_ytdlp", True)
        )
        self._row_toggle(
            maint_inner,
            label="Auto-update yt-dlp on launch",
            desc="yt-dlp updates frequently to keep up with YouTube changes. "
                 "Recommended to keep on.",
            var=self._auto_update_var,
            command=self._save,
        )

        ctk.CTkFrame(maint_inner, fg_color=P["border"], height=1).pack(
            fill="x", pady=8
        )

        # Manual update button
        update_row = ctk.CTkFrame(maint_inner, fg_color="transparent")
        update_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            update_row,
            text="Update yt-dlp now",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(side="left", fill="y")

        self._update_btn = ctk.CTkButton(
            update_row,
            text="Update Now",
            width=110, height=32,
            fg_color=P["accent_blue"],
            hover_color=P["accent_cyan"],
            text_color="#000000",
            corner_radius=16,
            command=self._manual_update_ytdlp,
        )
        self._update_btn.pack(side="right")

        self._update_lbl = ctk.CTkLabel(
            maint_inner,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"],
            anchor="w",
        )
        self._update_lbl.pack(fill="x")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _section(self, parent, text: str):
        P = PALETTE
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(14, 6))
        ctk.CTkLabel(
            frame,
            text=text.upper(),
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=P["accent_blue"],
            anchor="w",
        ).pack(fill="x")
        ctk.CTkFrame(frame, fg_color=P["border"], height=1,
                     corner_radius=0).pack(fill="x", pady=(3, 0))

    def _card(self, parent) -> ctk.CTkFrame:
        P = PALETTE
        card = ctk.CTkFrame(parent, fg_color=P["bg_card"], corner_radius=10,
                            border_color=P["border"], border_width=1)
        card.pack(fill="x", pady=(0, 4))
        return card

    def _row_toggle(self, parent, label: str, desc: str,
                    var: ctk.BooleanVar, command: Callable):
        P = PALETTE
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 2))
        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(
            text_col, text=label,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=P["text_primary"], anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_col, text=desc,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=P["text_dim"], anchor="w", wraplength=400,
            justify="left",
        ).pack(anchor="w")
        ctk.CTkSwitch(
            row, variable=var, text="",
            onvalue=True, offvalue=False,
            button_color=P["accent_blue"],
            button_hover_color=P["accent_cyan"],
            progress_color=P["accent_blue"],
            fg_color=P["bg_panel"],
            command=command,
        ).pack(side="right", padx=(12, 0))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_folder(self):
        chosen = filedialog.askdirectory(
            title="Select Clone Hero Songs Folder",
            initialdir=self._folder_var.get(),
        )
        if chosen:
            self._folder_var.set(chosen)

    def _apply_folder(self):
        new_path = self._folder_var.get().strip()
        if new_path:
            self.app_state.config["songs_folder"] = new_path
            self._save()
            self.on_folder_change(new_path)

    def _save(self):
        """Persist all current settings to config.json."""
        cfg = self.app_state.config
        cfg["songs_folder"]       = self._folder_var.get()
        cfg["auto_sync"]          = self._auto_sync_var.get()
        cfg["max_results"]        = int(self._max_results_var.get())
        cfg["query_template"]     = self._query_template_var.get()
        cfg["auto_update_ytdlp"]  = self._auto_update_var.get()
        cfg["cookie_browser"]     = self._browser_var.get()
        save_config(cfg)

    def _manual_update_ytdlp(self):
        import threading
        from app.setup.dependency_check import update_ytdlp

        self._update_btn.configure(state="disabled", text="Updating...")
        self._update_lbl.configure(
            text="Updating yt-dlp...", text_color=PALETTE["text_secondary"]
        )

        def _worker():
            changed, version = update_ytdlp()

            def _done():
                self._update_btn.configure(state="normal", text="Update Now")
                if changed:
                    self._update_lbl.configure(
                        text=f"Updated to {version}",
                        text_color=PALETTE["success"],
                    )
                else:
                    self._update_lbl.configure(
                        text=f"Already up to date ({version})",
                        text_color=PALETTE["text_dim"],
                    )
            self._safe_after(_done)

        threading.Thread(target=_worker, daemon=True).start()
