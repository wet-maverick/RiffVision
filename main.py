"""
main.py
-------
RiffVision entry point.

Responsibilities:
  1. Check Python version (3.10+ required)
  2. Load config from ~/.riffvision/config.json
  3. Show the first-run wizard if setup is incomplete
  4. Launch the main window
"""

from __future__ import annotations

import sys
import os


def _check_python_version():
    if sys.version_info < (3, 10):
        print(
            f"[RiffVision] Python 3.10 or newer is required.\n"
            f"  You are running Python {sys.version.split()[0]}\n"
            f"  Download Python: https://python.org/downloads/"
        )
        input("Press Enter to exit...")
        sys.exit(1)


def main():
    _check_python_version()

    # ── Imports after version check ────────────────────────────────────
    try:
        import customtkinter as ctk
    except ImportError:
        print(
            "[RiffVision] customtkinter is not installed.\n"
            "  Run:  pip install -r requirements.txt"
        )
        input("Press Enter to exit...")
        sys.exit(1)

    from app.setup.first_run import (
        load_config,
        save_config,
        needs_setup,
        FirstRunWizard,
        PALETTE,
    )
    from app.ui.main_window import MainWindow

    # ── Configure CTk appearance ───────────────────────────────────────
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # ── Load config ────────────────────────────────────────────────────
    config = load_config()

    # ── Build root window (hidden initially) ──────────────────────────
    # We need a root window for the wizard (CTkToplevel requires a parent).
    root = ctk.CTk()
    root.withdraw()   # hide until setup is done

    if needs_setup(config):
        # ── First-run wizard ───────────────────────────────────────────
        # We show the wizard as a modal Toplevel over a hidden root.
        # When wizard calls on_complete, we launch the main window.

        def _on_setup_complete(updated_config: dict):
            root.destroy()
            _launch_main(updated_config)

        wizard = FirstRunWizard(root, config, on_complete=_on_setup_complete)

        # If user closes the wizard without completing, exit gracefully
        def _on_wizard_close():
            root.destroy()
            sys.exit(0)

        wizard.protocol("WM_DELETE_WINDOW", _on_wizard_close)
        root.mainloop()

    else:
        # ── Skip setup, go straight to main window ─────────────────────
        root.destroy()
        _launch_main(config)


def _launch_main(config: dict):
    """Create and run the main application window."""
    import customtkinter as ctk
    from app.ui.main_window import MainWindow

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = MainWindow(config)
    app.protocol("WM_DELETE_WINDOW", app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()
