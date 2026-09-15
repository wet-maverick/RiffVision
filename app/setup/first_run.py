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
    "songs_folder": DEFAULT_SONGS_PATH,
    "theme": "dark",
    "last_search_query": "",
    "show_missing_only": False,
    "setup_complete": False,
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
    """

    def __init__(self, parent, config: dict, on_complete: Callable[[dict], None]):
        super().__init__(parent)
        self.config = config
        self.on_complete = on_complete

        self.title("RiffVision — First Run Setup")
        self.resizable(False, False)
        self.configure(fg_color=PALETTE["bg_dark"])
        self.grab_set()   # Modal

        # Center on screen, never off the top edge
        self.update_idletasks()
        w, h = 620, 520
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - w) // 2)
        y = max(30, (screen_h - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        P = PALETTE

        # Header
        header = ctk.CTkFrame(self, fg_color=P["bg_panel"], corner_radius=0, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="Welcome to RiffVision",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=P["accent_blue"],
        ).pack(side="left", padx=24, pady=18)

        ctk.CTkLabel(
            header,
            text="v1.0",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_dim"],
        ).pack(side="right", padx=20)

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        # -- Songs folder section --
        ctk.CTkLabel(
            body,
            text="Clone Hero Songs Folder",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            body,
            text="Select the folder where your Clone Hero songs are stored.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        folder_row = ctk.CTkFrame(body, fg_color="transparent")
        folder_row.pack(fill="x", pady=(0, 16))

        self.folder_var = ctk.StringVar(value=self.config.get("songs_folder", DEFAULT_SONGS_PATH))
        self.folder_entry = ctk.CTkEntry(
            folder_row,
            textvariable=self.folder_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=P["bg_card"],
            border_color=P["border"],
            text_color=P["text_primary"],
            height=36,
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            folder_row,
            text="Browse",
            width=80,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=P["accent_purple"],
            hover_color=P["accent_blue"],
            command=self._browse_folder,
        ).pack(side="left")

        # -- Dependency section --
        ctk.CTkLabel(
            body,
            text="Dependencies",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=P["text_primary"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            body,
            text="RiffVision needs Deno and ffmpeg. Click 'Install All' to set them up automatically.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=P["text_secondary"],
            wraplength=560,
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(0, 10))

        # Dep status cards
        dep_frame = ctk.CTkFrame(body, fg_color=P["bg_card"], corner_radius=8)
        dep_frame.pack(fill="x", pady=(0, 12))

        self.dep_labels = {}
        for dep_name in ["Deno", "ffmpeg", "PO Token Plugin"]:
            row = ctk.CTkFrame(dep_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(
                row,
                text=dep_name,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=P["text_primary"],
                width=140,
                anchor="w",
            ).pack(side="left")
            lbl = ctk.CTkLabel(
                row,
                text="Checking...",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=P["text_dim"],
                anchor="w",
            )
            lbl.pack(side="left")
            self.dep_labels[dep_name] = lbl

        # Log area
        self.log_text = ctk.CTkTextbox(
            body,
            height=80,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=P["bg_panel"],
            text_color=P["text_secondary"],
            border_color=P["border"],
            border_width=1,
            state="disabled",
        )
        self.log_text.pack(fill="x", pady=(0, 12))

        # Buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        self.install_btn = ctk.CTkButton(
            btn_row,
            text="Install All",
            width=130,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=P["accent_blue"],
            hover_color=P["accent_cyan"],
            text_color="#000000",
            command=self._start_install,
        )
        self.install_btn.pack(side="left", padx=(0, 8))

        self.done_btn = ctk.CTkButton(
            btn_row,
            text="Continue  →",
            width=130,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=P["success"],
            hover_color="#00b85a",
            text_color="#000000",
            state="disabled",
            command=self._finish,
        )
        self.done_btn.pack(side="left")

        # Kick off initial check
        self.after(200, self._run_initial_check)

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

    def _log(self, msg: str):
        """Append a line to the log textbox (thread-safe)."""
        def _do():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(0, _do)

    def _set_dep_status(self, name: str, ok: bool, detail: str = ""):
        def _do():
            lbl = self.dep_labels.get(name)
            if not lbl:
                return
            if ok:
                lbl.configure(text=f"OK  {detail}", text_color=PALETTE["success"])
            else:
                lbl.configure(text=f"Missing  {detail}", text_color=PALETTE["danger"])
        self.after(0, _do)

    def _run_initial_check(self):
        def _check():
            result = check_all()
            self._update_dep_ui(result)
            if result.all_ok:
                self.after(0, lambda: self.done_btn.configure(state="normal"))
        threading.Thread(target=_check, daemon=True).start()

    def _update_dep_ui(self, result: CheckResult):
        self._set_dep_status("Deno", result.deno.found,
                             f"({result.deno.version})" if result.deno.found else "")
        self._set_dep_status("ffmpeg", result.ffmpeg.found,
                             f"({result.ffmpeg.version[:30]})" if result.ffmpeg.found else "")
        self._set_dep_status("PO Token Plugin", result.pot_plugin.found,
                             "(installed)" if result.pot_plugin.found else "(optional)")

    def _start_install(self):
        self.install_btn.configure(state="disabled", text="Installing...")
        self.done_btn.configure(state="disabled")

        def _install_worker():
            result = check_all()

            if not result.deno.found:
                self._log("Installing Deno...")
                status = install_deno(progress_cb=self._log)
                self._set_dep_status("Deno", status.found,
                                     f"({status.version})" if status.found else f"({status.error})")
            else:
                self._log(f"Deno already present: {result.deno.version}")

            if not result.ffmpeg.found:
                self._log("Installing ffmpeg...")
                status = install_ffmpeg(progress_cb=self._log)
                self._set_dep_status("ffmpeg", status.found,
                                     f"({status.version[:30]})" if status.found else f"({status.error})")
            else:
                self._log(f"ffmpeg already present.")

            if not result.pot_plugin.found:
                self._log("Installing PO Token plugin...")
                status = install_pot_plugin(progress_cb=self._log)
                self._set_dep_status("PO Token Plugin", status.found,
                                     "(installed)" if status.found else "(optional — failed)")
            else:
                self._log("PO Token plugin already present.")

            final = check_all()
            self._log("Done." if final.all_ok else "Warning: some dependencies still missing.")

            def _ui_update():
                self.install_btn.configure(state="normal", text="Install All")
                if final.all_ok:
                    self.done_btn.configure(state="normal")

            self.after(0, _ui_update)

        threading.Thread(target=_install_worker, daemon=True).start()

    def _finish(self):
        self.config["songs_folder"] = self.folder_var.get()
        self.config["setup_complete"] = True
        save_config(self.config)
        self.destroy()
        self.on_complete(self.config)
