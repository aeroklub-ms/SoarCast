# upload_server.py — tiny one-shot file receiver used by the in-browser
# meshopt decode step (see fix_gltf_for_cesium.py header). The preview page
# decodes EXT_meshopt_compression buffers with the official meshopt_decoder
# WASM and POSTs the rebuilt .gltf/.bin here.
#
#   POST http://127.0.0.1:8124/save?path=assets/Glider%20models/...  (body = bytes)
#
# Only paths under "assets/Glider models/" are accepted. Ctrl+C to stop.

import http.server
import os
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
ALLOWED = os.path.join(ROOT, "assets", "Glider models")


class Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        q = urllib.parse.urlparse(self.path)
        rel = urllib.parse.parse_qs(q.query).get("path", [""])[0]
        dest = os.path.abspath(os.path.join(ROOT, rel))
        if q.path != "/save" or not dest.startswith(ALLOWED) or ".." in rel:
            self.send_response(403)
            self._cors()
            self.end_headers()
            self.wfile.write(b"path must be under assets/Glider models/")
            return
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"saved {rel} ({n} bytes)")
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


print("[upload] listening on http://127.0.0.1:8124/save?path=...")
http.server.HTTPServer(("127.0.0.1", 8124), Handler).serve_forever()
