"""Platform sign-in over HTTP: real ES256 contexts through the real routes.

These prove the request seam end to end (flag, key set, replay, Origin,
caching, isolation across workspaces, subjects and a legacy account). Data
isolation for every record kind is covered in test_platform_scope.py.
"""

from __future__ import annotations

import base64
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
from platform_context import Verifier

from app.core import platform
from app.core.config import settings
from app.main import app

WS_A = "ws_aaaaaaaaaaaaaaaaaaaa"
WS_B = "ws_bbbbbbbbbbbbbbbbbbbb"
SUB_1 = "usr_1111111111111111111111"
SUB_2 = "usr_2222222222222222222222"
NOW = int(time.time())
ORIGIN = {"origin": "https://example.invalid"}


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Key:
    def __init__(self, kid: str = "edge-test-1") -> None:
        self.kid = kid
        self.private = ec.generate_private_key(ec.SECP256R1())

    def jwks(self) -> dict:
        n = self.private.public_key().public_numbers()
        return {"keys": [{"kty": "EC", "crv": "P-256", "kid": self.kid, "alg": "ES256", "use": "sig",
                          "x": b64(n.x.to_bytes(32, "big")), "y": b64(n.y.to_bytes(32, "big"))}]}

    def sign(self, claims: dict) -> str:
        head = b64(json.dumps({"alg": "ES256", "kid": self.kid, "typ": "platform-context+jwt"}).encode())
        body = b64(json.dumps(claims).encode())
        r, s = decode_dss_signature(self.private.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
        return f"{head}.{body}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


KEY, OTHER = Key(), Key()
counter = 0


def context(ws: str = WS_A, sub: str = SUB_1, **patch: object) -> str:
    global counter
    counter += 1
    claims = {
        "v": "1", "typ": "user", "iss": "platform-edge", "aud": "module:hearthline",
        "iat": NOW - 5, "exp": NOW + 55, "jti": f"jti_{counter:016d}", "ws": {"id": ws, "role": "member"},
        "sid": "ses_aaaaaaaaaaaaaaaaaaaa", "sub": sub, "acr": "pwd", "auth_time": NOW - 600, "ent": ["hearthline"],
    }
    claims.update(patch)
    return KEY.sign(claims)


class PlatformContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original = {k: getattr(settings, k) for k in (
            "database_path", "rate_limit_enabled", "registration_enabled", "platform_context", "platform_jwks_url", "platform_origin")}
        settings.database_path = str(Path(self.temp.name) / "app.db")
        settings.rate_limit_enabled = False
        settings.registration_enabled = True
        settings.platform_context = "on"
        settings.platform_origin = "https://example.invalid"
        settings.platform_jwks_url = "http://127.0.0.1:9190/.well-known/platform-jwks.json"
        platform._verifier = (settings.platform_jwks_url, Verifier("hearthline", jwks=KEY.jwks(), now=lambda: NOW))
        self.context = TestClient(app)
        self.client = self.context.__enter__()

    def tearDown(self) -> None:
        self.context.__exit__(None, None, None)
        platform._verifier = None
        for key, value in self.original.items():
            setattr(settings, key, value)
        self.temp.cleanup()

    def get(self, path: str, header: str | None, **extra: object):
        headers = {} if header is None else {"x-platform-context": header}
        return self.client.get(path, headers=headers, **extra)

    def write(self, method: str, path: str, header: str, body: dict | None = None, origin: bool = True):
        headers = {"x-platform-context": header, **(ORIGIN if origin else {})}
        return self.client.request(method, path, json=body, headers=headers)

    def test_a_verified_context_reaches_the_routes_without_any_legacy_account(self) -> None:
        r = self.get("/api/auth/me", context())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["sign_in"], r.json()["user"]["id"], r.json()["user"]["email"], r.json()["workspace_id"]), ("platform", SUB_1, "", WS_A))
        r = self.write("POST", "/api/simulations", context(), {"name": "Mine", "inputs": {"a": 1}})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(len(self.get("/api/simulations", context()).json()), 1)
        from app.core.database import connection
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users").fetchone()[0], 0)

    def test_refused_contexts_answer_with_the_contract_code(self) -> None:
        cases = [
            ("missing", "", 401, "context_missing"),
            ("garbage", "not-a-jws", 401, "context_invalid"),
            ("other key", OTHER.sign({**json.loads(base64.urlsafe_b64decode(context().split(".")[1] + "==")), "jti": "jti_forged000000000"}), 401, "context_invalid"),
            ("expired", context(iat=NOW - 200, exp=NOW - 140), 401, "context_expired"),
            ("other app", context(aud="module:kinscope"), 401, "audience_mismatch"),
            ("not entitled", context(ent=["kinscope"]), 403, "module_not_entitled"),
        ]
        for name, header, status, code in cases:
            with self.subTest(name):
                r = self.get("/api/simulations", header)
                self.assertEqual((r.status_code, r.json()["error"]["code"]), (status, code), r.text)
                self.assertEqual(r.headers["cache-control"], "private, no-store")

    def test_a_service_context_is_refused(self) -> None:
        service = {"v": "1", "typ": "service", "iss": "platform-edge", "aud": "module:hearthline", "iat": NOW - 5,
                   "exp": NOW + 100, "jti": "jti_serviceaaaaaaaaa", "ws": {"id": WS_A, "role": "member"},
                   "sub": "svc:digest", "act": {"sub": SUB_1}, "scope": ["hearthline.simulations:read"], "purpose": "digest"}
        r = self.get("/api/simulations", KEY.sign(service))
        self.assertEqual(r.status_code, 403, r.text)

    def test_nothing_is_accepted_while_platform_sign_in_is_off(self) -> None:
        for value in ("off", "", "no", "true"):
            settings.platform_context = value
            r = self.get("/api/simulations", context())
            self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "context_not_accepted"), value)

    def test_the_key_set_must_be_on_loopback(self) -> None:
        for url in ("https://evil.test/jwks.json", "http://10.0.0.5:9190/jwks", "file:///etc/passwd",
                    "not a url", "http://user:pw@127.0.0.1:9190/jwks"):
            settings.platform_jwks_url = url
            platform._verifier = None
            r = self.get("/api/simulations", context())
            self.assertEqual((r.status_code, r.json()["error"]["code"]), (503, "context_unavailable"), url)
        settings.platform_jwks_url = "http://localhost:9190/k"
        self.assertIsNone(platform.jwks_url())  # a name could resolve elsewhere: literal addresses only
        settings.platform_jwks_url = "http://[::1]:9190/k"
        self.assertEqual(platform.jwks_url(), "http://[::1]:9190/k")

    def test_a_write_context_cannot_be_replayed_but_a_read_context_can(self) -> None:
        read = context()
        self.assertEqual([self.get("/api/simulations", read).status_code for _ in range(2)], [200, 200])
        write = context()
        body = {"name": "Once", "inputs": {"a": 1}}
        self.assertEqual(self.write("POST", "/api/simulations", write, body).status_code, 201)
        again = self.write("POST", "/api/simulations", write, body)
        self.assertEqual((again.status_code, again.json()["error"]["code"]), (401, "context_replayed"))
        self.assertEqual(len(self.get("/api/simulations", context()).json()), 1)

    def test_a_platform_write_needs_an_origin_and_every_platform_response_is_not_cached(self) -> None:
        r = self.write("POST", "/api/simulations", context(), {"name": "No origin", "inputs": {"a": 1}}, origin=False)
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "origin_required"))
        self.assertEqual(r.headers["cache-control"], "private, no-store")
        self.assertEqual(self.get("/api/simulations", context()).json(), [])
        ok = self.get("/api/simulations", context())
        self.assertEqual(ok.headers["cache-control"], "private, no-store")
        # A request without a context is untouched by the guard.
        legacy = self.client.get("/api/health") if self.client.get("/api/health").status_code == 200 else None
        if legacy is not None:
            self.assertNotEqual(legacy.headers.get("cache-control"), "private, no-store")

    def test_only_the_configured_origin_is_accepted_for_a_platform_write(self) -> None:
        body = {"name": "Origin check", "inputs": {"a": 1}}
        for name, origin in {"other site": "https://evil.invalid", "scheme": "http://example.invalid",
                             "subdomain": "https://x.example.invalid", "null": "null"}.items():
            r = self.client.post("/api/simulations", json=body, headers={"x-platform-context": context(), "origin": origin})
            self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "origin_required"), name)
        # Two Origin fields are ambiguous.
        r = self.client.post("/api/simulations", json=body, headers=[
            ("x-platform-context", context()), ("origin", "https://example.invalid"), ("origin", "https://example.invalid")])
        self.assertEqual(r.status_code, 403)
        # A trailing slash is the same origin; and with no origin configured every platform write is refused.
        r = self.client.post("/api/simulations", json=body, headers={"x-platform-context": context(), "origin": "https://example.invalid/"})
        self.assertEqual(r.status_code, 201, r.text)
        settings.platform_origin = ""
        r = self.client.post("/api/simulations", json=body, headers={"x-platform-context": context(), "origin": "https://example.invalid"})
        self.assertEqual(r.status_code, 403)

    def test_two_context_header_fields_are_refused_and_an_unhandled_error_is_still_not_cacheable(self) -> None:
        r = self.client.get("/api/simulations", headers=[("x-platform-context", context()), ("x-platform-context", context())])
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "context_invalid"))
        from unittest.mock import patch
        with patch("app.routes.product.calculate_affordability", side_effect=RuntimeError("boom")):
            failing = TestClient(app, raise_server_exceptions=False)
            r = failing.get("/api/affordability", headers={"x-platform-context": context()})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.headers["cache-control"], "private, no-store")

    def test_the_context_is_the_only_credential_the_legacy_session_is_never_consulted(self) -> None:
        reg = self.client.post("/api/auth/register", json={
            "name": "Legacy Person", "email": "legacy@example.invalid", "password": "syntheticpass1"})
        self.assertEqual(reg.status_code, 201, reg.text)
        self.client.post("/api/simulations", json={"name": "Legacy sim", "inputs": {"a": 1}})
        cookie = self.client.cookies.get(settings.session_cookie_name)
        token = {"authorization": f"Bearer {cookie}"}
        self.assertEqual([s["name"] for s in self.client.get("/api/simulations").json()], ["Legacy sim"])

        # A verified context, with the legacy cookie and bearer present: only the platform scope is seen.
        both = self.client.get("/api/simulations", headers={"x-platform-context": context(), **token})
        self.assertEqual(both.json(), [])
        me = self.client.get("/api/auth/me", headers={"x-platform-context": context(), **token}).json()
        self.assertEqual((me["sign_in"], me["user"]["id"]), ("platform", SUB_1))
        # An invalid context is never retried against the cookie or bearer, and an empty one is still a context.
        for bad in ("garbage", ""):
            r = self.client.get("/api/simulations", headers={"x-platform-context": bad, **token})
            self.assertEqual(r.status_code, 401, bad)
        settings.platform_context = "off"
        r = self.client.get("/api/simulations", headers={"x-platform-context": context(), **token})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "context_not_accepted"))
        # Without a context the cookie still works as before.
        self.assertEqual(self.client.get("/api/simulations").status_code, 200)

    def test_sign_in_registration_and_sign_out_are_unavailable_to_platform_requests(self) -> None:
        creds = {"name": "Nope Person", "email": "nope@example.invalid", "password": "syntheticpass1"}
        for path, body in (("/api/auth/register", creds), ("/api/auth/login", {"email": creds["email"], "password": creds["password"]}),
                           ("/api/auth/logout", None)):
            r = self.write("POST", path, context(), body)
            self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "context_not_accepted"), path)
        from app.core.database import connection
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users").fetchone()[0], 0)

    def test_two_workspaces_two_subjects_and_a_legacy_account_never_see_each_other(self) -> None:
        mine = {"name": "Mine", "criteria": {"max_price": 300000}}
        ids = {}
        for label, (ws, sub) in {"a1": (WS_A, SUB_1), "b1": (WS_B, SUB_1), "a2": (WS_A, SUB_2)}.items():
            r = self.write("POST", "/api/searches", context(ws, sub), {**mine, "name": f"Search {label}"})
            self.assertEqual(r.status_code, 201, r.text)
            ids[label] = r.json()["id"]
            self.assertEqual(self.write("PUT", "/api/profile", context(ws, sub), {"annual_gross_income": {"a1": 1, "b1": 2, "a2": 3}[label]}).status_code, 200)
        for label, (ws, sub) in {"a1": (WS_A, SUB_1), "b1": (WS_B, SUB_1), "a2": (WS_A, SUB_2)}.items():
            names = [s["name"] for s in self.get("/api/searches", context(ws, sub)).json()]
            self.assertEqual(names, [f"Search {label}"], label)
            for other, target in ids.items():
                if other == label:
                    continue
                self.assertEqual(self.write("DELETE", f"/api/searches/{target}", context(ws, sub)).status_code, 404, (label, other))
                self.assertEqual(self.get(f"/api/searches/{target}/matches", context(ws, sub)).status_code, 404, (label, other))
        self.assertEqual(self.get("/api/profile", context(WS_B, SUB_1)).json()["annual_gross_income"], 2)
        # A legacy account sees none of it, and a platform scope sees none of the legacy account's.
        self.client.post("/api/auth/register", json={"name": "Legacy Person", "email": "l@example.invalid", "password": "syntheticpass1"})
        self.assertEqual(self.client.get("/api/searches").json(), [])
        legacy_search = self.client.post("/api/searches", json={"name": "Legacy search", "criteria": {}}).json()["id"]
        self.client.cookies.clear()
        self.assertEqual(self.write("DELETE", f"/api/searches/{legacy_search}", context()).status_code, 404)

    def test_forwarded_requests_with_a_platform_context_are_decided_by_the_context_alone(self) -> None:
        # Another subject's id in the path or body can never change the scope.
        r = self.write("POST", "/api/simulations", context(WS_A, SUB_1), {"name": f"{SUB_2} {WS_B}", "inputs": {"a": 1}})
        self.assertEqual(r.status_code, 201, r.text)
        from app.core.database import connection
        with connection() as db:
            row = db.execute("SELECT workspace_id, owner_sub FROM saved_simulations").fetchone()
        self.assertEqual((row[0], row[1]), (WS_A, SUB_1))


if __name__ == "__main__":
    unittest.main()
