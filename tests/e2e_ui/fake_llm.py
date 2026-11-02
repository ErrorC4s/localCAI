"""Tiny fake OpenAI-compatible server for UI tests. Records the last request body."""
import json
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
        with open(LAST, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for t in ["*sips tea* ", "Oolong ", "from **Darjeeling**~"]:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
