#!/usr/bin/env python3
"""Stands in for llama.cpp's llama-server in tests: same flags, same endpoints."""
import json, sys, time, os
from http.server import BaseHTTPRequestHandler, HTTPServer
args = sys.argv[1:]
if "--list-devices" in args:  # like a laptop with integrated + dedicated graphics
    print("Available devices:\n  Vulkan0: Intel(R) Arc(TM) Graphics (18432 MiB, 17000 MiB free)\n"
          "  Vulkan1: NVIDIA GeForce RTX 4060 Laptop GPU (8151 MiB, 7600 MiB free)")
    sys.exit(0)
if "--help" in args:
    print("-fa,    --flash-attn [on|off|auto]   set Flash Attention use ('on', 'off', or 'auto', default: 'auto')\n"
          "-ctk,   --cache-type-k TYPE          KV cache data type for K\n"
          "-fit,   --fit [on|off]               whether to adjust unset arguments to fit in device memory\n"
          "-fitt,  --fit-target MiB             target margin per device for --fit")
    sys.exit(0)
print("args:", " ".join(args), flush=True)
model = os.path.basename(args[args.index("-m") + 1])
port = int(args[args.index("--port") + 1])
ready_at = time.time() + 1.0
print(f"fake llama-server loading {model} on {port}", flush=True)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/health":
            ok = time.time() >= ready_at
            self.send_response(200 if ok else 503); self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "loading model"}).encode())
        else:
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": model}]}).encode())
    def do_POST(self):
        req = self.rfile.read(int(self.headers["Content-Length"]))
        if os.environ.get("FAKE_LLAMA_LAST"):
            open(os.environ["FAKE_LLAMA_LAST"], "wb").write(req)
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for t in ["<think>let me th", "ink</think>", "Hello from ", model]:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n".encode()); self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")

HTTPServer(("127.0.0.1", port), H).serve_forever()
