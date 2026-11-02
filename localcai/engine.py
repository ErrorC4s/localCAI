"""Built-in model engine: llama.cpp's `llama-server`, managed by localCAI.

No Ollama needed. localCAI downloads the official llama.cpp build for this
computer once, then runs any .gguf model you put in the models folder (the
"model slot"). It speaks the same OpenAI-compatible API as every other backend.

    ~/.localcai/engine/   llama.cpp binaries + engine.json
    ~/.localcai/models/   your .gguf models (drop files here)

Build choice: Vulkan where available (works on NVIDIA, AMD and Intel GPUs without
installing CUDA), Metal on Apple Silicon, CPU otherwise or on request.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from .library import home

# llama.cpp's "latest" release can be a tag without binaries (e.g. v0.8.0); the builds live in the
# frequent bNNNNN releases. So we list recent releases and take the newest one with a matching build.
RELEASE_API = os.environ.get("LOCALCAI_LLAMA_RELEASE_API",
                             "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20")
HF_BASE = os.environ.get("LOCALCAI_HF_BASE", "https://huggingface.co").rstrip("/")
UA = {"User-Agent": "localCAI (+https://github.com/ErrorC4s/localCAI)"}

# One-click starter model. The exact file is looked up via the Hugging Face API at download time.
STARTER_MODELS = {
    "qwen3-4b-instruct": {
        "label": "Qwen3 4B Instruct 2507 (Q4_K_M, ~2.5 GB, runs on 4+ GB VRAM)",
        "repo": "lmstudio-community/Qwen3-4B-Instruct-2507-GGUF",
        "pattern": r"Q4_K_M\.gguf$",
    },
}


def engine_dir() -> Path:
    return home() / "engine"


def models_dir() -> Path:
    d = home() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── which build fits this computer ─────────────────────────────────────────
def platform_key() -> tuple[str, str]:
    system = {"Windows": "win", "Darwin": "macos", "Linux": "ubuntu"}.get(platform.system(), "")
    m = platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "x64" if m in ("x86_64", "amd64", "x64") else m
    return system, arch


def asset_patterns(system: str, arch: str, variant: str) -> list[re.Pattern]:
    ext = r"\.zip$" if system == "win" else r"\.(zip|tar\.gz)$"
    gpu = {("win", "x64"): ["vulkan-x64"], ("win", "arm64"): ["vulkan-arm64"],
           ("ubuntu", "x64"): ["vulkan-x64"], ("ubuntu", "arm64"): ["vulkan-arm64"]}
    cpu = {("win", "x64"): ["cpu-x64"], ("win", "arm64"): ["cpu-arm64"], ("ubuntu", "x64"): ["x64"],
           ("ubuntu", "arm64"): ["arm64"], ("macos", "arm64"): ["arm64"], ("macos", "x64"): ["x64"]}
    names = ([] if variant == "cpu" else gpu.get((system, arch), [])) + cpu.get((system, arch), [])
    return [re.compile(rf"-bin-{system}-{re.escape(n)}{ext}", re.I) for n in names]


def pick_asset(assets: list[dict], system: str, arch: str, variant: str = "auto") -> dict | None:
    for pat in asset_patterns(system, arch, variant):
        for a in assets:
            if pat.search(a.get("name", "")):
                return a
    return None


# ── small helpers ──────────────────────────────────────────────────────────
def _get_json(url: str, timeout: float = 30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def _download(url: str, dest: Path, progress) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done, total)
    tmp.replace(dest)


def _safe_extract(archive: Path, dest: Path) -> None:
    root = dest.resolve()

    def ok(name: str) -> bool:
        target = (dest / name).resolve()
        return target == root or root in target.parents

    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            bad = [n for n in z.namelist() if not ok(n)]
            if bad:
                raise ValueError(f"unsafe path in archive: {bad[0]}")
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            members = t.getmembers()
            bad = [m.name for m in members if not ok(m.name) or m.isdev()
                   or ((m.issym() or m.islnk()) and not ok(os.path.join(os.path.dirname(m.name), m.linkname)))]
            if bad:
                raise ValueError(f"unsafe path in archive: {bad[0]}")
            t.extractall(dest, members=members)


def _free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise OSError("no free port")


def list_slot_models() -> list[dict]:
    """.gguf files in the models folder (skipping vision projectors and extra split parts)."""
    out = []
    for p in sorted(models_dir().rglob("*.gguf")):
        n = p.name.lower()
        if "mmproj" in n or re.search(r"-0000[2-9]-of-\d+\.gguf$|-000[1-9]\d-of-\d+\.gguf$", n):
            continue
        out.append({"name": str(p.relative_to(models_dir())).replace("\\", "/"),
                    "size_gb": round(p.stat().st_size / 1e9, 2)})
    return out


# ── the engine ─────────────────────────────────────────────────────────────
class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.proc: subprocess.Popen | None = None
        self.model: str | None = None
        self.port: int | None = None
        self.state = "off"            # off | starting | ready | error
        self.error = ""
        self.job: dict | None = None  # background install / download progress
        self._job_seq = 0

    # info --------------------------------------------------------------
    def installed(self) -> dict | None:
        try:
            info = json.loads((engine_dir() / "engine.json").read_text("utf-8"))
            return info if Path(info["server"]).exists() else None
        except (OSError, ValueError, KeyError):
            return None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def status(self) -> dict:
        with self.lock:
            if self.proc and self.proc.poll() is not None and self.state in ("ready", "starting"):
                self.state, self.error = "error", "The engine stopped unexpectedly.\n" + self.log_tail()
            inst = self.installed()
            return {"installed": bool(inst), "build": inst and inst.get("asset"), "version": inst and inst.get("tag"),
                    "state": self.state, "model": self.model, "error": self.error, "job": self.job,
                    "models_dir": str(models_dir()), "models": list_slot_models(),
                    "starters": {k: v["label"] for k, v in STARTER_MODELS.items()}}

    def log_tail(self, n: int = 12) -> str:
        try:
            lines = (engine_dir() / "engine.log").read_text("utf-8", "replace").splitlines()
            return "\n".join(lines[-n:])
        except OSError:
            return ""

    # background jobs -------------------------------------------------------
    def _run_job(self, kind: str, fn) -> bool:
        with self.lock:
            if self.job and not self.job.get("done"):
                return False
            self._job_seq += 1
            self.job = {"id": self._job_seq, "kind": kind, "progress": 0.0, "message": "Starting…",
                        "done": False, "error": ""}

        def run():
            try:
                fn()
                self.job.update(progress=1.0, done=True, message="Done")
            except Exception as e:  # report any failure to the UI
                self.job.update(done=True, error=str(e) or e.__class__.__name__, message="Failed")
        threading.Thread(target=run, daemon=True).start()
        return True

    def _progress(self, label: str):
        def cb(done: int, total: int):
            self.job["progress"] = (done / total) if total else 0.0
            mb = done / 1e6
            self.job["message"] = f"{label} {mb:,.0f} MB" + (f" / {total / 1e6:,.0f} MB" if total else "")
        return cb

    def install_async(self, variant: str = "auto") -> bool:
        return self._run_job("install", lambda: self.install(variant))

    def install(self, variant: str = "auto") -> dict:
        system, arch = platform_key()
        self.job and self.job.update(message="Finding the right llama.cpp build…")
        data = _get_json(RELEASE_API)
        releases = data if isinstance(data, list) else [data]
        rel, asset = None, None
        for r in releases:  # newest first; skip drafts and releases without binaries
            if r.get("draft"):
                continue
            asset = pick_asset(r.get("assets", []), system, arch, variant)
            if asset:
                rel = r
                break
        if not asset:
            raise RuntimeError(f"Couldn't find a llama.cpp build for {system}-{arch} in the {len(releases)} newest "
                               "releases. Try again later, or use Ollama / LM Studio as the backend.")
        self.stop()
        target = engine_dir() / rel.get("tag_name", "latest")
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        archive = target / asset["name"]
        _download(asset["browser_download_url"], archive, self._progress(f"Downloading {asset['name']}"))
        self.job and self.job.update(message="Unpacking…")
        _safe_extract(archive, target)
        archive.unlink()
        exe = "llama-server.exe" if system == "win" else "llama-server"
        servers = sorted(target.rglob(exe), key=lambda p: len(p.parts))
        if not servers:
            raise RuntimeError("llama-server was not found in the download")
        server = servers[0]
        if system != "win":
            for f in server.parent.iterdir():
                if f.is_file() and (f.name.startswith("llama-") or f.suffix in (".so", ".dylib")):
                    f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        info = {"tag": rel.get("tag_name"), "asset": asset["name"], "server": str(server), "variant": variant}
        (engine_dir() / "engine.json").write_text(json.dumps(info, indent=2), "utf-8")
        for old in engine_dir().iterdir():  # keep only the current version
            if old.is_dir() and old != target:
                shutil.rmtree(old, ignore_errors=True)
        return info

    def download_model_async(self, key: str) -> bool:
        if key not in STARTER_MODELS:
            raise ValueError("unknown model")
        return self._run_job("model", lambda: self.download_model(key))

    def download_model(self, key: str) -> str:
        spec = STARTER_MODELS[key]
        self.job and self.job.update(message="Looking up the model…")
        info = _get_json(f"{HF_BASE}/api/models/{spec['repo']}")
        files = [s["rfilename"] for s in info.get("siblings", []) if re.search(spec["pattern"], s["rfilename"], re.I)]
        if not files:
            raise RuntimeError("Couldn't find the model file on Hugging Face.")
        name = Path(files[0]).name
        dest = models_dir() / name
        if not dest.exists():
            _download(f"{HF_BASE}/{spec['repo']}/resolve/main/{files[0]}", dest, self._progress(f"Downloading {name}"))
        return name

    # process control ---------------------------------------------------------
    def start(self, model: str, ctx: int = 8192, gpu_layers: int = 999, timeout: float = 300) -> None:
        """Start (or switch to) a model and wait until it's ready. Raises RuntimeError on failure."""
        with self.lock:
            if self.state == "ready" and self.model == model and self.proc and self.proc.poll() is None:
                return
            inst = self.installed()
            path = (models_dir() / model).resolve()
            problem = None
            if not inst:
                problem = "The built-in engine isn't installed yet. Open 🧠 Engine and click Install."
            elif models_dir().resolve() not in path.parents or not path.is_file() or path.suffix.lower() != ".gguf":
                problem = f"Model not found in the models folder: {model}"
            if problem:  # record it so the UI never sits on "loading…"
                self.state, self.error = ("off" if not inst else "error"), problem
                raise RuntimeError(problem)
            self.stop()
            self.port = _free_port(8766)
            server = Path(inst["server"])
            env = dict(os.environ)
            if sys.platform.startswith("linux"):
                env["LD_LIBRARY_PATH"] = f"{server.parent}:{env.get('LD_LIBRARY_PATH', '')}"
            log = (engine_dir() / "engine.log").open("w", encoding="utf-8")
            cmd = [str(server), "-m", str(path), "--host", "127.0.0.1", "--port", str(self.port),
                   "-c", str(int(ctx)), "-ngl", str(int(gpu_layers)), "--jinja"]
            flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
            self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=server.parent,
                                         env=env, creationflags=flags)
            self.model, self.state, self.error = model, "starting", ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                with self.lock:
                    self.state = "error"
                    self.error = ("The engine couldn't start this model. If it mentions memory, lower "
                                  "GPU layers or context size in Settings; if it mentions Vulkan, choose the CPU "
                                  "build.\n\n" + self.log_tail())
                raise RuntimeError(self.error)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        with self.lock:
                            self.state = "ready"
                        return
            except OSError:
                pass  # 503 while loading, or not listening yet
            time.sleep(0.4)
        self.stop()
        with self.lock:
            self.state, self.error = "error", "The model took too long to load."
        raise RuntimeError(self.error)

    def start_async(self, model: str, ctx: int, gpu_layers: int) -> None:
        def run():
            try:
                self.start(model, ctx, gpu_layers)
            except RuntimeError:
                pass  # state/error already recorded for the UI
        with self.lock:
            self.model, self.state, self.error = model, "starting", ""
        threading.Thread(target=run, daemon=True).start()

    def stop(self) -> None:
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            self.proc, self.state = None, "off"


ENGINE = Engine()
