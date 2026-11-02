"""localCAI as a desktop app: its own window with the localCAI logo in the taskbar.

Runs the local web server in the background and shows it in a native window
(pywebview → Edge WebView2 on Windows, WebKit on macOS, GTK/Qt on Linux).
Closing the window stops everything, including the built-in model engine.
Without pywebview installed it falls back to opening your browser.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from .library import home

PORT = 8765
APP_ID = "ErrorC4s.localCAI"


def resource(rel: str) -> Path:
    """A bundled file, both from source and inside a PyInstaller exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / rel


def _quiet_console() -> None:
    # A windowed exe has no console: send prints to a log file instead of crashing on them.
    if sys.stdout is None or sys.stderr is None:
        log = (home() / "localcai.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        f = open(log, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def _running_here(port: int) -> bool:
    """Is a localCAI already serving on this port? (Then just open another window to it.)"""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers={"Host": f"127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return "version" in json.load(r)
    except (OSError, ValueError):
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _windows_taskbar_identity() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def main() -> int:
    _quiet_console()
    from .engine import ENGINE
    from .webui.server import create_server

    port, httpd = PORT, None
    if not _running_here(port):
        try:
            httpd = create_server(port)
        except OSError:  # port taken by something else
            port = _free_port()
            httpd = create_server(port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"localCAI running at {url}")

    try:
        import webview  # pywebview
    except ImportError:
        webbrowser.open(url)
        if httpd is None:
            return 0
        print("Close this window or press Ctrl+C to stop localCAI.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        _windows_taskbar_identity()
        icon = resource("assets/logo.ico")
        webview.settings["ALLOW_DOWNLOADS"] = True  # ⬇ Card, exports
        webview.create_window("localCAI", url, width=1320, height=860, min_size=(960, 620),
                              background_color="#15161D", text_select=True)
        webview.start(icon=str(icon) if icon.exists() else None, private_mode=False,
                      storage_path=str(home() / "webview"))
    if httpd is not None:
        ENGINE.stop()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
