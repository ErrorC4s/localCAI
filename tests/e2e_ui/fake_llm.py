"""Tiny fake OpenAI-compatible server for UI tests. Records the last request body."""
import json, time
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LAST = sys.argv[2]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "fake-model"}, {"id": "other-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = body["messages"]
        check = msgs[0]["role"] == "system" and msgs[0]["content"].startswith("You are a strict editor")
        scene = msgs[0]["role"] == "system" and msgs[0]["content"].startswith("You keep notes on a role-play scene")
        with open(LAST + (".check" if check else ".scene" if scene else ""), "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        if scene:  # the scene-state note made after a reply
            return self.sse(["Where: the tea room; Luna: sipping tea by the window; Alex: across the table"], "stop")
        if check:  # the OOC guard asking for a verdict
            verdict = "FIX: She has never heard of video games; react with confusion." \
                if "ooc test" in msgs[-1]["content"].lower() else "OK"
            return self.sse([verdict], "stop")
        if "slow reply" in body["messages"][-1]["content"]:   # time to edit the chat while it streams
            return self.sse(["*thinks* ", "Hmm", "m..."], "stop", delay=1.0)
        ramble = "ramble" in body["messages"][-1]["content"]
        if "never heard of video games" in body["messages"][-1]["content"]:
            return self.sse(["*tilts head* A video... what?"], "stop")
        parts = ["She nods. ", "Then she lea"] if ramble else ["*sips tea* ", "Oolong ", "from **Darjeeling**~"]
        self.sse(parts, "length" if ramble else "stop")

    def sse(self, parts, finish, delay=0.0):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for t in parts:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n".encode())
            self.wfile.flush()
            if delay:
                time.sleep(delay)
        fin = {"choices": [{"delta": {}, "finish_reason": finish}]}
        self.wfile.write(f"data: {json.dumps(fin)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
