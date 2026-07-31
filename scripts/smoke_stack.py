from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


def request_json(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    try:
        with opener.open(request, timeout=20) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} failed with {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a running Hearthline stack")
    parser.add_argument("--base-url", default="http://127.0.0.1:3080")
    parser.add_argument(
        "--authenticated",
        action="store_true",
        help="Create a disposable smoke-test account and exercise authenticated APIs",
    )
    args = parser.parse_args()

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    health = request_json(opener, args.base_url, "/api/health")
    readiness = request_json(opener, args.base_url, "/api/ready")
    if health.get("ok") is not True or readiness.get("ok") is not True:
        raise RuntimeError("Health or readiness check did not report ok")

    with opener.open(f"{args.base_url.rstrip('/')}/", timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Frontend returned {response.status}")

    if args.authenticated:
        suffix = int(time.time() * 1000)
        request_json(
            opener,
            args.base_url,
            "/api/auth/register",
            method="POST",
            body={
                "name": "Stack Smoke Test",
                "email": f"smoke-{suffix}@example.invalid",
                "password": "smoketestpass1",
            },
        )
        request_json(opener, args.base_url, "/api/profile")
        risk = request_json(
            opener,
            args.base_url,
            "/api/risk",
            method="POST",
            body={
                "portfolio_value": 1_000_000,
                "loan_amount": 0,
                "maintenance_ltv_max": 0.7,
                "mu_annual": 0.07,
                "sigma_annual": 0.22,
                "horizons_months": [12],
                "runs": 1_000,
            },
        )
        results = risk.get("results")
        if not isinstance(results, list) or results[0]["breach_probability"] != 0:
            raise RuntimeError("Zero-loan risk smoke check failed")

    print(
        f"Hearthline stack smoke test passed at {args.base_url} "
        f"(authenticated={args.authenticated})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
