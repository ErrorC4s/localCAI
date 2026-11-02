#!/usr/bin/env python3
"""Stands in for llama.cpp's llama-server in tests: same flags, same endpoints."""
import json, sys, time, os
from http.server import BaseHTTPRequestHandler, HTTPServer
args = sys.argv[1:]
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
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for t in ["<think>let me th", "ink</think>", "Hello from ", model]:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n".encode()); self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")

HTTPServer(("127.0.0.1", port), H).serve_forever()
