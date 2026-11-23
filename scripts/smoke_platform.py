"""Real-server check of platform sign-in: uvicorn, a local key set, real signed contexts.

Run with `make smoke-platform` (from the repo root, after `make bootstrap`). It proves, over HTTP and
without the test client, that a verified context is accepted, that the legacy cookie is ignored for a
platform request, that a refused context never falls back, that a platform write needs an Origin and
cannot be replayed, and that responses to platform requests are not cacheable. Ids are random per run.
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

ROOT = Path(__file__).resolve().parents[1]


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


private = ec.generate_private_key(ec.SECP256R1())
numbers = private.public_key().public_numbers()
JWKS = json.dumps({"keys": [{"kty": "EC", "crv": "P-256", "kid": "smoke-1", "alg": "ES256", "use": "sig",
                             "x": b64(numbers.x.to_bytes(32, "big")), "y": b64(numbers.y.to_bytes(32, "big"))}]}).encode()


def sign(sub: str, ws: str, **patch: object) -> str:
    now = int(time.time())
    claims = {"v": "1", "typ": "user", "iss": "platform-edge", "aud": "module:hearthline", "iat": now - 2, "exp": now + 55,
              "jti": b64(secrets.token_bytes(18)), "ws": {"id": ws, "role": "member"}, "sid": "ses_" + secrets.token_hex(10),
              "sub": sub, "acr": "pwd", "auth_time": now - 60, "ent": ["hearthline"], **patch}
    head = b64(json.dumps({"alg": "ES256", "kid": "smoke-1", "typ": "platform-context+jwt"}).encode())
    body = b64(json.dumps(claims).encode())
    r, s = decode_dss_signature(private.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{head}.{body}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


class Jwks(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(JWKS)

    def log_message(self, *_args: object) -> None:
        pass


def call(base: str, method: str, path: str, headers: dict[str, str] | None = None, body: object | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"content-type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None), {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, (json.loads(raw) if raw else None), {k.lower(): v for k, v in error.headers.items()}


def check(label: str, condition: bool, detail: object = "") -> None:
    print(("ok   " if condition else "FAIL ") + label + ("" if condition else f"  {detail}"))
    if not condition:
        raise SystemExit(1)


def main() -> None:
    jwks_port, port = free_port(), free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", jwks_port), Jwks)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "PLATFORM_CONTEXT": "on", "PLATFORM_ORIGIN": "https://example.invalid", "PLATFORM_JWKS_URL": f"http://127.0.0.1:{jwks_port}/jwks",
               "DATABASE_PATH": str(Path(directory) / "smoke.db"), "RATE_LIMIT_ENABLED": "false", "ENVIRONMENT": "test",
               "PYTHONPATH": str(ROOT / "backend")}
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                    "--port", str(port), "--workers", "1"], env=env, cwd=ROOT / "backend",
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/api/health", timeout=1)
                    break
                except OSError:
                    time.sleep(0.2)
            ws_a, ws_b = "ws_" + secrets.token_hex(10), "ws_" + secrets.token_hex(10)
            sub_1, sub_2 = "usr_" + secrets.token_hex(11), "usr_" + secrets.token_hex(11)
            origin = {"origin": "https://example.invalid"}

            status, body, headers = call(base, "GET", "/api/auth/me", {"x-platform-context": sign(sub_1, ws_a)})
            check("a verified context is accepted", status == 200 and body["sign_in"] == "platform" and body["user"]["id"] == sub_1, (status, body))
            check("the response is not cacheable", headers.get("cache-control") == "private, no-store", headers)

            write = sign(sub_1, ws_a)
            payload = {"name": "Smoke simulation", "inputs": {"a": 1}}
            status, body, _ = call(base, "POST", "/api/simulations", {"x-platform-context": write, **origin}, payload)
            check("a write with an Origin succeeds", status == 201, (status, body))
            status, body, _ = call(base, "POST", "/api/simulations", {"x-platform-context": write, **origin}, payload)
            check("the same write context cannot be replayed", status == 401 and body["error"]["code"] == "context_replayed", (status, body))
            status, body, _ = call(base, "POST", "/api/simulations", {"x-platform-context": sign(sub_1, ws_a)}, payload)
            check("a write without an Origin is refused", status == 403 and body["error"]["code"] == "origin_required", (status, body))

            for label, ws, sub in (("another workspace", ws_b, sub_1), ("another subject", ws_a, sub_2)):
                status, body, _ = call(base, "GET", "/api/simulations", {"x-platform-context": sign(sub, ws)})
                check(f"{label} sees nothing", status == 200 and body == [], (status, body))
            status, body, _ = call(base, "GET", "/api/simulations", {"x-platform-context": sign(sub_1, ws_a)})
            check("the owner sees the record", status == 200 and len(body) == 1, (status, body))

            status, _, headers = call(base, "POST", "/api/auth/register", {"origin": "https://example.invalid"},
                                      {"name": "Smoke Person", "email": f"{secrets.token_hex(4)}@example.invalid", "password": "syntheticpass1"})
            cookie = headers.get("set-cookie", "").split(";")[0]
            check("a legacy account can still register", status == 201 and cookie, (status, headers))
            status, body, _ = call(base, "GET", "/api/simulations", {"cookie": cookie})
            check("and use its cookie", status == 200 and body == [], (status, body))
            status, body, _ = call(base, "GET", "/api/simulations", {"cookie": cookie, "x-platform-context": "garbage"})
            check("a refused context never falls back to the cookie", status == 401 and body["error"]["code"] == "context_invalid", (status, body))
            status, body, _ = call(base, "GET", "/api/simulations", {"cookie": cookie, "x-platform-context": ""})
            check("an empty context header is still a platform request", status == 401 and body["error"]["code"] == "context_missing", (status, body))
            status, body, _ = call(base, "GET", "/api/simulations", {"cookie": cookie, "x-platform-context": sign(sub_1, ws_a)})
            check("with both, only the context counts", status == 200 and len(body) == 1, (status, body))
            status, body, _ = call(base, "GET", "/api/simulations", {"x-platform-context": sign(sub_1, ws_a, aud="module:kinscope")})
            check("a context for another app is refused", status == 401 and body["error"]["code"] == "audience_mismatch", (status, body))
        finally:
            process.terminate()
            process.wait(10)
            server.shutdown()
    print("Platform smoke passed.")


if __name__ == "__main__":
    main()
