# -*- coding: utf-8 -*-
import sys, io
if chr(91) in io.open(__file__, encoding="utf-8").read():
    sys.exit(3)
import http.server
import urllib.request
import urllib.error

UP_API = "http://127.0.0.1:8000"
UP_DASH = "http://127.0.0.1:3000"

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self): self.pf()
    def do_POST(self): self.pf()
    def do_PUT(self): self.pf()
    def do_DELETE(self): self.pf()
    def do_OPTIONS(self): self.pf()
    def do_HEAD(self): self.pf()
    def pf(self):
        path = self.path
        if path.startswith("/api/compensation"):
            target = UP_API + path
        elif path.startswith("/api"):
            target = UP_API + path.replace("/api", "", 1)
        else:
            target = UP_DASH + path
        ln = int(self.headers.get("Content-Length") or 0)
        body = None
        if ln > 0:
            body = self.rfile.read(ln)
        req = urllib.request.Request(target, data=body, method=self.command)
        for hn in ("Content-Type", "Authorization", "Accept"):
            hv = self.headers.get(hn)
            if hv:
                req.add_header(hn, hv)
        try:
            with urllib.request.urlopen(req, timeout=180) as rp:
                data = rp.read()
                self.send_response(rp.status)
                self.send_header("Content-Type", rp.headers.get("Content-Type") or "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type") or "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except Exception:
            try:
                self.send_response(502)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except Exception:
                pass
    def log_message(self, fmt, *a):
        pass

http.server.ThreadingHTTPServer(("127.0.0.1", 9090), H).serve_forever()
