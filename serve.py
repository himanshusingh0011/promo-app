"""Local web server: same API as Vercel, plus the static page.

    python serve.py            # http://localhost:8000
"""
import mimetypes
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from promo.web import handle

PUBLIC = Path(__file__).parent / "public"


class Handler(BaseHTTPRequestHandler):
    def _api(self, method):
        route = self.path.split("?")[0].rstrip("/").split("/")[-1]
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)) if method == "POST" else b""
        code, payload = handle(route, method, raw, self.headers)
        import json
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        self.send_error(404)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        rel = self.path.split("?")[0].lstrip("/") or "index.html"
        f = (PUBLIC / rel).resolve()
        if not str(f).startswith(str(PUBLIC.resolve())) or not f.is_file():
            return self.send_error(404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Promo finder on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
