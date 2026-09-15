"""
first_run.py
------------
First-run wizard: sets the songs folder path and runs dependency installation.
Stores config at ~/.riffvision/config.json.
This module provides both the config model and the CTk wizard window.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk
from tkinter import filedialog

from app.setup.dependency_check import (
    APP_DATA_DIR,
    CheckResult,
    check_all,
    install_deno,
    install_ffmpeg,
    install_pot_plugin,
)

# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

CONFIG_PATH = APP_DATA_DIR / "config.json"
DEFAULT_SONGS_PATH = "D:/CloneHeroSongs"

_DEFAULTS = {
    "songs_folder":       DEFAULT_SONGS_PATH,
    "theme":              "dark",
    "last_search_query":  "",
    "show_missing_only":  False,
    "setup_complete":     False,
    "auto_sync":          True,
    "max_results":        8,
    "query_template":     "{artist} {title} official music video",
    "auto_update_ytdlp":  True,
    "cookie_browser":     "chrome",
}


def load_config() -> dict:
    """Load config from disk, merging with defaults for any missing keys."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config = {**_DEFAULTS, **saved}
            return config
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def save_config(config: dict) -> None:
    """Persist config to disk."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def needs_setup(config: dict) -> bool:
    """Return True if first-run setup hasn't been completed."""
    return not config.get("setup_complete", False)


# ---------------------------------------------------------------------------
# Colors (shared palette — imported by UI modules)
# ---------------------------------------------------------------------------

PALETTE = {
    "bg_dark":       "#0a0e1a",   # near-black navy
    "bg_panel":      "#0f1525",   # slightly lighter navy
    "bg_card":       "#151e33",   # card background
    "bg_card_hover": "#1a2540",   # card hover
    "accent_blue":   "#1e90ff",   # electric blue (primary)
    "accent_cyan":   "#00d4ff",   # cyan highlight
    "accent_purple": "#7b5ea7",   # blue-raspberry purple
    "accent_glow":   "#4db8ff",   # glow/hover tint
    "text_primary":  "#e8f0fe",   # near-white
    "text_secondary":"#8899cc",   # muted blue-grey
    "text_dim":      "#445577",   # very dim
    "success":       "#00e676",   # green (has video)
    "warning":       "#ffab00",   # amber
    "danger":        "#ff4444",   # red (missing video)
    "progress_bar":  "#1e90ff",
    "border":        "#1e2d4d",
}


# ---------------------------------------------------------------------------
# First-Run Wizard Window
# ---------------------------------------------------------------------------

class FirstRunWizard(ctk.CTkToplevel):
    """
    Modal wizard that:
      1. Asks user to confirm / change songs folder
      2. Checks + installs Deno, ffmpeg, PO Token plugin
      3. Writes config and calls on_complete when done

    Layout uses a strict 3-zone approach:
      - HEADER  (fixed height, never shrinks)
      - BODY    (scrollable content, expands to fill)
      - FOOTER  (fixed height, buttons always visible)
    """

    WIZARD_W = 660
    WIZARD_H = 600

    def __init__(self, parent, config: dict, on_complete: Callable[[dict], None]):
        super().__init__(parent)
        self.config = config
        self.on_complete = on_complete

        self.title("RiffVision — First Run Setup")
        self.resizable(False, False)
        self.configure(fg_color=PALETTE["bg_dark"])
        self.grab_set()

        # Center on screen, never off the top edge
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - self.WIZARD_W) // 2)
        y = max(30, (screen_h - self.WIZARD_H) // 2)
        self.geometry(f"{self.WIZARD_W}x{self.WIZARD_H}+{x}+{y}")

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        P = PALETTE

        # ── HEADER ────────────────────────────────────────────────────
        header = ctk.CTkFrame(
            self,
            fg_color=P["bg_panel"],
            corner_radius=0,
            height=90,
        )
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # Accent bar at very top
        ctk.CTkFrame(
            header,
            fg_color=P["accent_blue"],
            height=3,
            corner_radius=0,
        ).pack(fill="x", side="top")

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.pack(fill="both", expand=True, padx=28)

        name_row = ctk.CTkFrame(title_block, fg_color="transparent")
        name_row.pack(side="left", fill="y")

        ctk.CTkLabel(
            name_row,
            text="RIFF",
            font=ctk.CTkFont(family="Segoe UI Black", size=28, weight="bold"),
            text_color=P["accent_blue"],
        ).pack(side="left", pady=18)

        ctk.CTkLabel(
            name_row,
            text="VISION",
            font=ctk.CTkFont(family="Segoe UI Black", size=28, weight="bold"),
            text_color=P["accent_cyan"],
        ).pack(side="left")

        ctk.CTkLabel(
            title_block,
            text="First Run Setup",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=P["text_dim"],
            anchor="e",
        ).pack(side="right", pady=18)

        # ── FOOTER ────────────────────────────────────────────────────
        # Built BEFORE body so pack order puts it at the bottom reliably
        footer = ctk.CTkFrame(
            self,
            fg_color=P["bg_panel"],
            corner_radius=0,
            height=76,
        )
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # Separator line at top of footer
        ctk.CTkFrame(
            footer,
            fg_color=P["border"],
            height=1,
            corner_radius=0,
        ).pack(fill="x", side="top")

        btn_container = ctk.CTkFrame(footer, fg_color="transparent")
        btn_container.pack(fill="both", expand=True, padx=24, pady=14)

        self.install_btn = ctk.CTkButton(
            btn_container,
            text="⬇  Install All",
            height=44,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=P["accent_blue"],
            hover_color=P["accent_cyan"],
            text_color="#000000",
            corner_radius=8,
            command=self._start_install,
        )
        self.install_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.done_btn = ctk.CTkButton(
            btn_container,
            text="Continue  →",
            height=44,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=P["success"],
            hover_color="#00b85a",
            text_color="#000000",
            corner_radius=8,
            state="disabled",
            command=self._finish,
        )
        self.done_btn.pack(side="left", fill="x", expand=True)

        # ── BODY (scrollable, fills between header and footer) ────────
        body = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=P["bg_card_hover"],
            scrollbar_button_hover_color=P["accent_blue"],
        )
        body.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(body, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=28, pady=(20, 16))

        # ── Songs folder section ──────────────────────────────────────
        self._section_label(inner, "Clone Hero Songs Folder")

        ctk.CTkLabel(
            inner,
            text="Set the folder where your Clone Hero songs are stored.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        folder_card = ctk.CTkFrame(
            inner,
            fg_color=P["bg_card"],
            corner_radius=10,
            border_color=P["border"],
            border_width=1,
        )
        folder_card.pack(fill="x", pady=(0, 22))

        folder_inner = ctk.CTkFrame(folder_card, fg_color="transparent")
        folder_inner.pack(fill="x", padx=14, pady=12)

        self.folder_var = ctk.StringVar(
            value=self.config.get("songs_folder", DEFAULT_SONGS_PATH)
        )
        self.folder_entry = ctk.CTkEntry(
            folder_inner,
            textvariable=self.folder_var,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=P["bg_dark"],
            border_color=P["border"],
            text_color=P["accent_cyan"],
            height=38,
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            folder_inner,
            text="Browse",
            width=90,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=P["accent_purple"],
            hover_color=P["accent_blue"],
            corner_radius=6,
            command=self._browse_folder,
        ).pack(side="left")

        # ── Dependencies section ──────────────────────────────────────
        self._section_label(inner, "Dependencies")

        ctk.CTkLabel(
            inner,
            text="RiffVision needs Deno (JS runtime) and ffmpeg (audio processing).\nClick Install All below — they download automatically, no manual steps needed.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(0, 10))

        # Dep status cards
        dep_card = ctk.CTkFrame(
            inner,
            fg_color=P["bg_card"],
            corner_radius=10,
            border_color=P["border"],
            border_width=1,
        )
        dep_card.pack(fill="x", pady=(0, 16))

        self.dep_labels = {}
        deps = [
            ("Deno",           "JS challenge solver for YouTube"),
            ("ffmpeg",         "Audio extraction for sync"),
            ("PO Token Plugin","YouTube bot-detection bypass (optional)"),
        ]

        for i, (dep_name, dep_desc) in enumerate(deps):
            row = ctk.CTkFrame(dep_card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(10 if i == 0 else 4, 10 if i == len(deps)-1 else 4))

            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", fill="y")

            ctk.CTkLabel(
                left,
                text=dep_name,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=P["text_primary"],
                anchor="w",
                width=160,
            ).pack(anchor="w")

            ctk.CTkLabel(
                left,
                text=dep_desc,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=P["text_dim"],
                anchor="w",
            ).pack(anchor="w")

            status_lbl = ctk.CTkLabel(
                row,
                text="Checking...",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=P["text_dim"],
                anchor="e",
            )
            status_lbl.pack(side="right")
            self.dep_labels[dep_name] = status_lbl

            # Divider between rows
            if i < len(deps) - 1:
                ctk.CTkFrame(
                    dep_card,
                    fg_color=P["border"],
                    height=1,
                    corner_radius=0,
                ).pack(fill="x", padx=14)

        # ── Install log ───────────────────────────────────────────────
        self._section_label(inner, "Install Log")

        self.log_text = ctk.CTkTextbox(
            inner,
            height=100,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=P["bg_dark"],
            text_color=P["accent_cyan"],
            border_color=P["border"],
            border_width=1,
            corner_radius=8,
            state="disabled",
        )
        self.log_text.pack(fill="x")

        # Kick off initial check
        self.after(200, self._run_initial_check)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _section_label(self, parent, text: str):
        """Styled section heading with an accent underline."""
        P = PALETTE
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            frame,
            text=text.upper(),
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=P["accent_blue"],
            anchor="w",
        ).pack(fill="x")

        ctk.CTkFrame(
            frame,
            fg_color=P["border"],
            height=1,
            corner_radius=0,
        ).pack(fill="x", pady=(4, 0))

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------

    def _browse_folder(self):
        chosen = filedialog.askdirectory(
            title="Select Clone Hero Songs Folder",
            initialdir=self.folder_var.get(),
        )
        if chosen:
            self.folder_var.set(chosen)

    def _safe_after(self, fn):
        """Post fn() to the main thread only if this window still exists."""
        try:
            if self.winfo_exists():
                self.after(0, fn)
        except Exception:
            pass

    def _log(self, msg: str):
        """Append a line to the log textbox (thread-safe)."""
        def _do():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self._safe_after(_do)

    def _set_dep_status(self, name: str, ok: bool, detail: str = ""):
        def _do():
            lbl = self.dep_labels.get(name)
            if not lbl:
                return
            if ok:
                lbl.configure(text=f"✓  {detail}", text_color=PALETTE["success"])
            elif name == "PO Token Plugin":
                # Optional dep — amber, not red
                lbl.configure(text=f"○  {detail or 'optional'}", text_color=PALETTE["warning"])
            else:
                lbl.configure(text=f"✗  Missing", text_color=PALETTE["danger"])
        self._safe_after(_do)

    def _run_initial_check(self):
        def _check():
            result = check_all()
            self._update_dep_ui(result)
            if result.all_ok:
                self._safe_after(lambda: self.done_btn.configure(state="normal"))
        threading.Thread(target=_check, daemon=True).start()

    def _update_dep_ui(self, result: CheckResult):
        self._set_dep_status("Deno", result.deno.found,
                             result.deno.version.split()[0] if result.deno.found else "")
        self._set_dep_status("ffmpeg", result.ffmpeg.found,
                             "installed" if result.ffmpeg.found else "")
        # PO Token is optional — pass found=True with amber detail when missing
        # so _set_dep_status uses the neutral amber branch, not red
        self._set_dep_status("PO Token Plugin", result.pot_plugin.found,
                             "installed" if result.pot_plugin.found else "optional")

    def _start_install(self):
        self.install_btn.configure(state="disabled", text="Installing...")
        self.done_btn.configure(state="disabled")

        def _install_worker():
            result = check_all()

            if not result.deno.found:
                self._log("Installing Deno...")
                status = install_deno(progress_cb=self._log)
                self._set_dep_status("Deno", status.found,
                                     status.version.split()[0] if status.found else status.error[:40])
            else:
                self._log(f"Deno already present: {result.deno.version}")
                self._set_dep_status("Deno", True, result.deno.version.split()[0])

            if not result.ffmpeg.found:
                self._log("Installing ffmpeg...")
                status = install_ffmpeg(progress_cb=self._log)
                self._set_dep_status("ffmpeg", status.found,
                                     "installed" if status.found else status.error[:40])
            else:
                self._log("ffmpeg already present.")
                self._set_dep_status("ffmpeg", True, "installed")

            if not result.pot_plugin.found:
                self._log("Installing PO Token plugin...")
                status = install_pot_plugin(progress_cb=self._log)
                self._set_dep_status("PO Token Plugin", status.found,
                                     "installed" if status.found else "optional")
            else:
                self._log("PO Token plugin already present.")
                self._set_dep_status("PO Token Plugin", True, "installed")

            final = check_all()
            self._log("All done — ready to launch!" if final.all_ok
                      else "Warning: some dependencies still missing.")

            def _ui_update():
                self.install_btn.configure(state="normal", text="⬇  Install All")
                if final.all_ok:
                    self.done_btn.configure(state="normal")

            self._safe_after(_ui_update)

        threading.Thread(target=_install_worker, daemon=True).start()

    def _finish(self):
        self.config["songs_folder"] = self.folder_var.get()
        self.config["setup_complete"] = True
        save_config(self.config)
        # Call on_complete BEFORE destroying so the callback can call root.quit()
        # which exits the mainloop cleanly. The root is then destroyed by _run_wizard().
        self.on_complete(self.config)
        self.destroy()
