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


def _running_version(port: int) -> str | None:
    """The version of the localCAI already serving on this port, or None."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers={"Host": f"127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return str(json.load(r).get("version") or "") or None
    except (OSError, ValueError, AttributeError):
        return None


def _ask_to_quit(port: int, wait: float = 10.0) -> bool:
    """Ask an older localCAI on this port to close; True once the port is free."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}", method="POST",
                                     headers={"Host": f"127.0.0.1:{port}", "X-LocalCAI": "1",
                                              "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
    except OSError:
        return False  # versions before 0.8.6 can't be asked
    end = time.time() + wait
    while time.time() < end:
        if _running_version(port) is None:
            return True
        time.sleep(0.3)
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

    from . import __version__
    port, httpd = PORT, None
    running = _running_version(port)
    if running and running != __version__:
        # An older (or other) version is open: ask it to close so this one is what you see.
        if not _ask_to_quit(port):
            port = _free_port()  # it couldn't be asked: run side by side instead of reusing it
        running = None
    if running is None:
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
        stop = threading.Event()
        httpd.quit_hook = stop.set  # a newer version asked us to close
        print("Close this window or press Ctrl+C to stop localCAI.")
        try:
            while not stop.wait(1):
                pass
        except KeyboardInterrupt:
            pass
    else:
        _windows_taskbar_identity()
        icon = resource("assets/logo.ico")
        webview.settings["ALLOW_DOWNLOADS"] = True  # ⬇ Card, exports
        window = webview.create_window("localCAI", url, width=1320, height=860, min_size=(960, 620),
                              background_color="#15161D", text_select=True)
        if httpd is not None:
            httpd.quit_hook = window.destroy  # a newer version asked us to close
        webview.start(icon=str(icon) if icon.exists() else None, private_mode=False,
                      storage_path=str(home() / "webview"))
    if httpd is not None:
        ENGINE.stop()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
