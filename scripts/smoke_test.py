"""One real end-to-end check against a running Verity (local or deployed).

Usage: python scripts/smoke_test.py [--url http://localhost:8000]
Exits non-zero if the check fails, times out or finds no claim to check.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

GREAT_WALL = "The Great Wall of China is visible from space with the naked eye."
POLL_SECONDS = 2
TIMEOUT_SECONDS = 300


def request(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body_text = resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise SystemExit(f"{method} {url} -> HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"{method} {url} -> cannot connect: {e.reason}") from None
    except TimeoutError:
        raise SystemExit(f"{method} {url} -> no response within 30 s") from None
    except ValueError as e:  # e.g. a --url without http:// or https://
        raise SystemExit(f"{method} {url} -> bad URL: {e}") from None
    try:
        return json.loads(body_text)
    except ValueError:
        raise SystemExit(
            f"{method} {url} -> not a JSON reply (is this the Verity API?): {body_text[:200]!r}"
        ) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000", help="Verity base URL")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    health = request("GET", f"{base}/api/health")
    print(f"Health OK. fast={health['models']['fast']} judge={health['models']['judge']}")

    started = time.monotonic()
    check_id = request("POST", f"{base}/api/checks", {"text": GREAT_WALL})["id"]
    print(f"Check {check_id} started: {GREAT_WALL!r}")

    record: dict = {}
    status = ""
    while time.monotonic() - started < TIMEOUT_SECONDS:
        record = request("GET", f"{base}/api/checks/{check_id}")
        if record["status"] != status:
            status = record["status"]
            print(f"  status: {status} ({time.monotonic() - started:.0f} s)")
        if status in ("done", "error"):
            break
        time.sleep(POLL_SECONDS)
    else:
        print(f"FAIL: timed out after {TIMEOUT_SECONDS} s (last status {status!r})")
        return 1

    elapsed = time.monotonic() - started
    if status == "error":
        print(f"FAIL: check ended with error: {record.get('error')}")
        return 1

    claims = record.get("claims", [])
    if not claims:
        print("FAIL: no checkable claims found (the test sentence has one).")
        return 1
    for claim in claims:
        result = claim["result"]
        verified = sum(1 for e in claim["evidence"] if e["quote_verified"])
        print(
            f"\nClaim {claim['id']}: {claim['text']}\n"
            f"  final: {result['final']['label']} ({result['final']['confidence']}%)"
            f"  agreed: {result['agreed']}  debated: {result['debated']}"
            f"  verified quotes: {verified}"
        )

    totals = record.get("totals", {})
    cost = totals.get("cost_usd")
    cost_text = f"${cost:.4f}" if isinstance(cost, int | float) else "n/a"
    print(
        f"\nTotals: {totals.get('model_calls', '?')} model calls, cost {cost_text}, "
        f"duration {totals.get('duration_s', round(elapsed, 1))} s"
    )
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
