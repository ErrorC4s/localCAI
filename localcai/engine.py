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
from struct import error as struct_error
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
        "label": "Qwen3 4B Instruct 2507 · general assistant, small and fast", "size_gb": 2.5, "kv_mb": 0.144,
        "repo": "lmstudio-community/Qwen3-4B-Instruct-2507-GGUF",
        "pattern": r"Q4_K_M\.gguf$",
    },
    # Community roleplay fine-tunes: write more like C.ai and refuse less (adult scenes included).
    "stheno-8b": {
        "label": "Stheno 8B v3.2 (Llama 3) · roleplay-tuned, fewer refusals", "size_gb": 4.9, "kv_mb": 0.128,
        "repo": "QuantFactory/L3-8B-Stheno-v3.2-GGUF",
        "pattern": r"Q4_K_M\.gguf$",
    },
    "mag-mell-12b": {
        "label": "Mag Mell 12B R1 (Mistral Nemo) · roleplay & storytelling, fewer refusals", "size_gb": 7.5, "kv_mb": 0.16,
        "repo": "inflatebot/MN-12B-Mag-Mell-R1-GGUF",
        "pattern": r"Q4_K_M\.gguf$",
    },
    "rocinante-12b": {
        "label": "Rocinante 12B v1.1 (Mistral Nemo) · roleplay & adventure, fewer refusals", "size_gb": 7.5, "kv_mb": 0.16,
        "repo": "TheDrummer/Rocinante-12B-v1.1-GGUF",
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


def nvidia_present() -> bool:
    """An NVIDIA driver is installed (nvidia-smi ships with it on Windows and Linux)."""
    if shutil.which("nvidia-smi"):
        return True
    return sys.platform == "win32" and Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe").exists()


def asset_patterns(system: str, arch: str, variant: str, nvidia: bool | None = None) -> list[re.Pattern]:
    """Builds to try, best first. variant: auto | cuda | vulkan | cpu."""
    ext = r"\.zip$" if system == "win" else r"\.(zip|tar\.gz)$"
    if nvidia is None:
        nvidia = nvidia_present()
    cuda = [rf"cuda-1[3-9][\d.]*-{arch}", rf"cuda-12\.(?:[89]|\d\d)[\d.]*-{arch}", rf"cuda-12[\d.]*-{arch}"] \
        if system in ("win", "ubuntu") else []
    vulkan = {("win", "x64"): [r"vulkan-x64"], ("win", "arm64"): [r"vulkan-arm64"],
              ("ubuntu", "x64"): [r"vulkan-x64"], ("ubuntu", "arm64"): [r"vulkan-arm64"]}.get((system, arch), [])
    cpu = {("win", "x64"): [r"cpu-x64"], ("win", "arm64"): [r"cpu-arm64"], ("ubuntu", "x64"): [r"x64"],
           ("ubuntu", "arm64"): [r"arm64"], ("macos", "arm64"): [r"arm64"], ("macos", "x64"): [r"x64"]}.get((system, arch), [])
    order = {"cpu": cpu, "vulkan": vulkan + cpu, "cuda": cuda + vulkan + cpu,
             "auto": (cuda if nvidia else []) + vulkan + cpu}.get(variant, vulkan + cpu)
    return [re.compile(rf"^llama-[^-]+-bin-{system}-{n}{ext}", re.I) for n in order]


def pick_asset(assets: list[dict], system: str, arch: str, variant: str = "auto",
               nvidia: bool | None = None) -> dict | None:
    for pat in asset_patterns(system, arch, variant, nvidia):
        for a in assets:
            if pat.search(a.get("name", "")):
                return a
    return None


def companion_assets(assets: list[dict], main: dict) -> list[dict]:
    """CUDA builds need the matching CUDA runtime zip (cudart-…) unpacked next to them."""
    m = re.search(r"-bin-(\w+)-cuda-([\d.]+)-(\w+)\.", main["name"])
    if not m:
        return []
    system, ver, arch = m.groups()
    return [a for a in assets if a.get("name", "").startswith("cudart-")
            and re.search(rf"-bin-{system}-cuda-{re.escape(ver)}-{arch}\.", a["name"])]


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


def cleanup_old_versions() -> None:
    """Remove engine folders other than the installed one (skips anything still in use)."""
    try:
        keep = Path(json.loads((engine_dir() / "engine.json").read_text("utf-8"))["server"]).resolve()
    except (OSError, ValueError, KeyError):
        return
    for d in engine_dir().iterdir():
        if d.is_dir() and d not in keep.parents:
            shutil.rmtree(d, ignore_errors=True)


def _pid_file() -> Path:
    return engine_dir() / "engine.pid"


def _is_our_engine(pid: int) -> bool:
    """True only if that PID is a llama-server, so we never touch unrelated programs."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, timeout=5, creationflags=0x08000000).stdout
            return "llama-server" in out.lower()
        cmd = Path(f"/proc/{pid}/cmdline")
        if cmd.exists():
            return "llama-server" in cmd.read_bytes().decode("utf-8", "replace")
        out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, timeout=5).stdout
        return "llama-server" in out
    except (OSError, subprocess.SubprocessError):
        return False


def kill_orphan() -> None:
    """Stop an engine a previous localCAI run left behind (crash, closed console, old version)."""
    try:
        pid = int(_pid_file().read_text().strip())
    except (OSError, ValueError):
        return
    if pid != os.getpid() and _is_our_engine(pid):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10,
                               creationflags=0x08000000)
            else:
                os.kill(pid, 15)
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(0.5)
    _pid_file().unlink(missing_ok=True)


_DEV_LINE = re.compile(r"^\s*([A-Za-z]+\d+):\s*(.+?)\s*\((\d+)\s*MiB", re.M)
_INTEGRATED = re.compile(r"intel.*(uhd|iris|hd graphics|arc\(tm\) graphics|graphics$)|radeon\(tm\) graphics|"
                         r"radeon graphics|vega \d+ graphics|apple|llvmpipe|swiftshader|microsoft basic", re.I)


def parse_devices(text: str) -> list[dict]:
    """Parse `llama-server --list-devices` output → [{id, name, mib}]."""
    return [{"id": m.group(1), "name": m.group(2).strip(), "mib": int(m.group(3))} for m in _DEV_LINE.finditer(text)]


def gguf_metadata(path: Path, want: tuple[str, ...] = ("tokenizer.chat_template", "general.architecture",
                                                       "general.name")) -> dict:
    """Read a few metadata values from a .gguf header without loading the model."""
    import struct
    sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    out: dict = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("not a GGUF file")
        version, = struct.unpack("<I", f.read(4))
        if version < 2:
            raise ValueError("GGUF v1 not supported")
        _tensors, kv_count = struct.unpack("<QQ", f.read(16))

        def read_str() -> bytes:
            n, = struct.unpack("<Q", f.read(8))
            return f.read(n)

        def skip(t: int) -> None:
            if t == 8:
                n, = struct.unpack("<Q", f.read(8)); f.seek(n, 1)
            elif t == 9:
                it, cnt = struct.unpack("<IQ", f.read(12))
                if it in sizes:
                    f.seek(sizes[it] * cnt, 1)
                else:
                    for _ in range(cnt):
                        skip(it)
            else:
                f.seek(sizes[t], 1)

        for _ in range(kv_count):
            key = read_str().decode("utf-8", "replace")
            t, = struct.unpack("<I", f.read(4))
            if key in want and t == 8:
                out[key] = read_str().decode("utf-8", "replace")
                if len(out) == len(want):
                    break
            else:
                skip(t)
    return out


def estimate_fit(size_gb: float, ctx: int, vram_mib: int | None, kv_mb: float | None = None) -> dict:
    """Rough memory estimate: model weights + KV cache for the context + compute buffers.

    kv_mb is the KV cache per token (MB); unknown models use a typical value for 4–14B models.
    Returns {"kind": "gpu"|"partial"|"cpu", "need_gb", "gpu_share", "text"}.
    """
    kv_gb = ctx * (kv_mb or 0.15) / 1024
    need = size_gb + kv_gb + 0.5
    if not vram_mib:
        return {"kind": "cpu", "need_gb": round(need, 1), "gpu_share": 0.0,
                "text": f"needs ~{need:.1f} GB · no graphics card found, runs on the CPU (slow)"}
    vram = vram_mib / 1024 * 0.92  # leave room for Windows and other apps
    if need <= vram:
        return {"kind": "gpu", "need_gb": round(need, 1), "gpu_share": 1.0,
                "text": f"needs ~{need:.1f} GB of {vram_mib / 1024:.0f} GB · fits on your GPU (fast)"}
    share = max(0.0, min(1.0, (vram - kv_gb - 0.5) / size_gb))
    if share >= 0.5:
        return {"kind": "partial", "need_gb": round(need, 1), "gpu_share": round(share, 2),
                "text": f"needs ~{need:.1f} GB of {vram_mib / 1024:.0f} GB · about {share:.0%} on the GPU, "
                        "the rest on the CPU (works, but slower)"}
    return {"kind": "cpu", "need_gb": round(need, 1), "gpu_share": round(share, 2),
            "text": f"needs ~{need:.1f} GB of {vram_mib / 1024:.0f} GB · mostly on the CPU (slow)"}


def pick_device(devices: list[dict]) -> dict | None:
    """Prefer a discrete GPU: NVIDIA > AMD > other; never an integrated GPU when a discrete one exists."""
    if not devices:
        return None
    def rank(d):
        n = d["name"].lower()
        discrete = not _INTEGRATED.search(d["name"])
        vendor = 3 if ("nvidia" in n or "geforce" in n or "rtx" in n) else 2 if ("radeon rx" in n or "amd" in n) else 1
        return (discrete, vendor if discrete else 0, d["mib"])
    return max(devices, key=rank)


def list_devices(server: Path) -> list[dict]:
    try:
        out = subprocess.run([str(server), "--list-devices"], capture_output=True, text=True, timeout=60,
                             cwd=server.parent, creationflags=0x08000000 if sys.platform == "win32" else 0)
        return parse_devices(out.stdout + "\n" + out.stderr)
    except (OSError, subprocess.SubprocessError):
        return []


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
        self.device: dict | None = None
        self._devices: tuple[str, list[dict]] | None = None
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
                    "device": self.device, "build_kind": inst and inst.get("build"),
                    "nvidia": nvidia_present(),
                    "cuda_upgrade": bool(inst) and nvidia_present() and inst.get("variant", "auto") == "auto"
                                    and "-cuda-" not in (inst.get("asset") or ""),
                    "models_dir": str(models_dir()), "models": list_slot_models(),
                    "starters": {k: v["label"] for k, v in STARTER_MODELS.items()}}

    def fits(self, ctx: int, device: str = "auto") -> dict:
        """How each local and recommended model would run on this computer at this context size."""
        inst = self.installed()
        devs = self.devices() if inst else []
        dev = next((d for d in devs if d["id"] == device), None) if device not in ("auto", "cpu") else None
        dev = None if device == "cpu" else (dev or pick_device(devs))
        mib = dev["mib"] if dev else None
        local = {m["name"]: estimate_fit(m["size_gb"] * 1e9 / 2**30, ctx, mib) for m in list_slot_models()}
        starters = {k: estimate_fit(v["size_gb"], ctx, mib, v.get("kv_mb")) for k, v in STARTER_MODELS.items()}
        return {"gpu": dev and dev["name"], "vram_mib": mib, "ctx": ctx, "local": local, "starters": starters,
                "known_gpu": bool(inst)}

    def devices(self, server: Path | None = None) -> list[dict]:
        """GPUs llama.cpp can see (cached per engine build)."""
        if server is None:
            inst = self.installed()
            if not inst:
                return []
            server = Path(inst["server"])
        if not self._devices or self._devices[0] != str(server):
            self._devices = (str(server), list_devices(server))
        return self._devices[1]

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
                self.job.update(progress=1.0, done=True,
                                message=self.job.get("final") or "Done")
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
        current = self.installed()
        if current and current.get("asset") == asset["name"]:
            self.job and self.job.update(final=f"Already up to date ({rel.get('tag_name')}).")
            return current
        self.stop()
        kill_orphan()
        target = engine_dir() / rel.get("tag_name", "latest")
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        if target.exists():  # files still locked (e.g. an engine started by another program): use a new folder
            target = engine_dir() / f"{rel.get('tag_name', 'latest')}-{int(time.time())}"
        target.mkdir(parents=True)
        archive = target / asset["name"]
        for a in [asset] + companion_assets(rel.get("assets", []), asset):
            archive = target / a["name"]
            _download(a["browser_download_url"], archive, self._progress(f"Downloading {a['name']}"))
            self.job and self.job.update(message="Unpacking…")
            _safe_extract(archive, target)
            archive.unlink()
        # cudart zips unpack flat; make sure the DLLs sit next to llama-server
        exe_name = "llama-server.exe" if system == "win" else "llama-server"
        servers_found = sorted(target.rglob(exe_name), key=lambda p: len(p.parts))
        if servers_found:
            for dll in target.glob("*.dll"):
                dest = servers_found[0].parent / dll.name
                if dll.parent != dest.parent and not dest.exists():
                    shutil.move(str(dll), dest)
        exe = "llama-server.exe" if system == "win" else "llama-server"
        servers = sorted(target.rglob(exe), key=lambda p: len(p.parts))
        if not servers:
            raise RuntimeError("llama-server was not found in the download")
        server = servers[0]
        if system != "win":
            for f in server.parent.iterdir():
                if f.is_file() and (f.name.startswith("llama-") or f.suffix in (".so", ".dylib")):
                    f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        build = "cuda" if "-cuda-" in asset["name"] else "vulkan" if "vulkan" in asset["name"] else \
            "metal" if "macos-arm64" in asset["name"] else "cpu"
        info = {"tag": rel.get("tag_name"), "asset": asset["name"], "server": str(server), "variant": variant,
                "build": build}
        (engine_dir() / "engine.json").write_text(json.dumps(info, indent=2), "utf-8")
        cleanup_old_versions()
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
    def start(self, model: str, ctx: int = 8192, gpu_layers: int = 999, timeout: float = 300,
              device: str = "auto") -> None:
        """Start (or switch to) a model and wait until it's ready. Raises RuntimeError on failure."""
        with self.lock:
            want = (model, int(ctx), int(gpu_layers), device)
            if self.state == "ready" and getattr(self, "_running", None) == want and self.proc and self.proc.poll() is None:
                return
            self._running = want
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
            # one conversation at a time: the whole context goes to it (no parallel slots sharing it)
            cmd = [str(server), "-m", str(path), "--host", "127.0.0.1", "--port", str(self.port),
                   "-c", str(int(ctx)), "-ngl", str(int(gpu_layers)), "-np", "1", "--jinja"]
            fit_note = ""
            try:
                has_template = bool(gguf_metadata(path).get("tokenizer.chat_template"))
            except (OSError, ValueError, struct_error):
                has_template = True  # can't tell: leave it to llama.cpp
            if not has_template:
                # No chat template inside the file (e.g. Rocinante): without one the model gets a garbled
                # prompt and writes nonsense. ChatML is what most roleplay fine-tunes are trained on.
                cmd += ["--chat-template", "chatml"]
                fit_note += "\n[localCAI] model has no chat template inside: using ChatML"
            if int(gpu_layers) > 0 and device != "cpu":
                if device and device != "auto":
                    chosen = next((d for d in self.devices(server) if d["id"] == device), None)
                else:
                    chosen = pick_device(self.devices(server))
                if chosen:
                    cmd += ["--device", chosen["id"]]
                    size_mib = path.stat().st_size / 2**20
                    fit = estimate_fit(size_mib / 1024, int(ctx), chosen.get("mib"))
                    if int(gpu_layers) >= 999 and chosen.get("mib") and fit["kind"] != "gpu":
                        # Too big to put all of it on the GPU: let llama.cpp work out how much fits.
                        i = cmd.index("-ngl"); del cmd[i:i + 2]
                        fit_note = (f"\n[localCAI] model is {size_mib / 1024:.1f} GB, GPU has {chosen['mib'] / 1024:.1f} GB:"
                                    " letting llama.cpp fit as many layers as possible on the GPU")
                self.device = chosen
            else:
                self.device = None
            flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
            kill_orphan()
            devs = self._devices[1] if self._devices else []
            log.write(f"[localCAI] build: {inst.get('asset')}\n[localCAI] GPUs seen: "
                      + (", ".join(f"{d['id']}={d['name']} ({d['mib']} MiB)" for d in devs) or "none")
                      + f"\n[localCAI] using: {self.device['name'] if self.device else 'CPU'}"
                      + fit_note + f"\n[localCAI] command: {' '.join(cmd)}\n")
            log.flush()
            self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=server.parent,
                                         env=env, creationflags=flags)
            _pid_file().write_text(str(self.proc.pid))
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

    def start_async(self, model: str, ctx: int, gpu_layers: int, device: str = "auto") -> None:
        def run():
            try:
                self.start(model, ctx, gpu_layers, device=device)
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
            _pid_file().unlink(missing_ok=True)


ENGINE = Engine()
