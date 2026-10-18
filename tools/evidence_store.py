"""Minimal in-cluster evidence store for the kind e2e (cluster/README.md).

GET  /evidence/<file>   evidence packages baked into the image (evidence/)
GET  /fixtures/<file>   cluster fixtures (cluster/fixtures/), e.g. a tampered package
PUT  /records/<name>    retain a gate decision record (write-once)
GET  /records           list retained records as JSON
GET  /records/<name>    read one record
GET  /healthz           liveness

Records live in ACME_RECORDS_DIR (default /var/lib/acme/records), a PersistentVolumeClaim in the e2e,
so they survive the store being scaled to zero. This is a teaching store, not a retention system:
no authentication, no replication, no retention policy.
"""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tools.common import ROOT

SERVED = {"evidence": ROOT / "evidence", "fixtures": ROOT / "cluster" / "fixtures"}
NAME = re.compile(r"^[A-Za-z0-9._-]+\.json$")
RECORDS = Path(os.environ.get("ACME_RECORDS_DIR", "/var/lib/acme/records"))


class Handler(BaseHTTPRequestHandler):
    server_version = "acme-evidence-store/1"

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _split(self) -> tuple[str, str]:
        parts = self.path.strip("/").split("/", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    def do_GET(self) -> None:  # noqa: N802
        area, name = self._split()
        if area == "healthz":
            return self._send(200, b'{"ok":true}')
        if area == "records" and not name:
            names = sorted(p.name for p in RECORDS.glob("*.json")) if RECORDS.exists() else []
            return self._send(200, json.dumps(names).encode())
        base = RECORDS if area == "records" else SERVED.get(area)
        if base is None or not NAME.match(name) or not (base / name).is_file():
            return self._send(404, b'{"error":"not found"}')
        return self._send(200, (base / name).read_bytes())

    def do_PUT(self) -> None:  # noqa: N802
        area, name = self._split()
        if area != "records" or not NAME.match(name):
            return self._send(400, b'{"error":"bad path"}')
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            json.loads(body)
        except ValueError:
            return self._send(400, b'{"error":"not json"}')
        RECORDS.mkdir(parents=True, exist_ok=True)
        target = RECORDS / name
        if target.exists():
            return self._send(409, b'{"error":"record exists"}')
        target.write_bytes(body)
        return self._send(201, b'{"ok":true}')

    def log_message(self, fmt: str, *args) -> None:  # one line per request on stdout
        print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
