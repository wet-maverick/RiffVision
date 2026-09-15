"""
main.py
-------
RiffVision entry point.

Responsibilities:
  1. Set Windows DPI awareness before any Tk window is created
  2. Check Python version (3.10+ required)
  3. Run first-run wizard if needed (in its own mainloop)
  4. Launch the main window (in its own fresh mainloop)

Key design: wizard and main window run in SEPARATE mainloop calls.
The wizard mainloop exits cleanly before the main window is created.
This prevents stale after() callbacks from the wizard's root window
from firing against the new window and crashing.
"""

from __future__ import annotations

import sys
import os


def _set_dpi_awareness():
    """
    Tell Windows to render at native DPI instead of letting it scale/blur.
    Must be called before any Tk window is created.
    """
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass


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
    _set_dpi_awareness()
    _check_python_version()

    try:
        import customtkinter as ctk
    except ImportError:
        print(
            "[RiffVision] customtkinter is not installed.\n"
            "  Run:  pip install -r requirements.txt"
        )
        input("Press Enter to exit...")
        sys.exit(1)

    from app.setup.first_run import load_config, needs_setup

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    config = load_config()

    # ── Phase 1: first-run wizard (own root + own mainloop) ───────────
    if needs_setup(config):
        config = _run_wizard(config)
        if config is None:
            # User closed the wizard without completing
            sys.exit(0)

    # ── Phase 2: main window (fresh root + fresh mainloop) ────────────
    _run_main_window(config)


def _run_wizard(config: dict):
    """
    Show the first-run wizard in its own CTk root + mainloop.
    Returns the updated config dict on completion, or None if user closed it.

    The wizard root is fully destroyed before this function returns,
    so no stale after() callbacks can leak into the main window.
    """
    import customtkinter as ctk
    from app.setup.first_run import FirstRunWizard, save_config

    result_holder = {"config": None, "completed": False}

    root = ctk.CTk()
    root.withdraw()

    def _on_complete(updated_config: dict):
        result_holder["config"]    = updated_config
        result_holder["completed"] = True
        # Schedule quit AFTER this callback returns so CTk cleans up properly
        root.after(10, root.quit)

    wizard = FirstRunWizard(root, config, on_complete=_on_complete)

    def _on_close():
        result_holder["completed"] = False
        root.quit()

    wizard.protocol("WM_DELETE_WINDOW", _on_close)

    root.mainloop()     # blocks until root.quit() is called above
    root.destroy()      # fully destroy — kills all pending after() callbacks

    if result_holder["completed"]:
        return result_holder["config"]
    return None


def _run_main_window(config: dict):
    """
    Launch the main application window in a fresh mainloop.
    Called only after any wizard root has been fully destroyed.
    """
    import customtkinter as ctk
    from app.ui.main_window import MainWindow

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = MainWindow(config)
    # _on_close is already registered inside MainWindow.__init__
    app.mainloop()


if __name__ == "__main__":
    main()
