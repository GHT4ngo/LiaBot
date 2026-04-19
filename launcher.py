"""
launcher.py — Bakgrundsprocess som kan starta LiaBot-API:t från webbläsaren.

Körs på port 8003. Startas av run.ps1 och lever kvar när api.py startas om.
Webbläsaren kan anropa POST http://localhost:8003/start för att starta api.py
även när api.py är nere.
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

API_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api.py")
PORT = 8003


class _Handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/start":
            # Kill any process still listening on port 8002 before spawning.
            # This prevents port conflicts when the old reloader hasn't fully
            # exited yet (e.g. if restart was called from the in-app terminal).
            import time

            try:
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-NetTCPConnection -LocalPort 8002 -State Listen "
                        "-ErrorAction SilentlyContinue | "
                        "Select-Object -ExpandProperty OwningProcess | "
                        "Sort-Object -Unique | "
                        "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }",
                    ],
                    capture_output=True,
                    timeout=5,
                )
                time.sleep(0.8)  # give OS time to release the port
            except Exception:
                pass

            subprocess.Popen(
                [sys.executable, API_SCRIPT],
                cwd=os.path.dirname(API_SCRIPT),
            )
            body = json.dumps({"ok": True, "message": "API startas..."}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # Tystar standard-HTTP-loggar


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), _Handler)
    print(f"  Launcher kör på port {PORT} — redo att starta API vid behov")
    server.serve_forever()
