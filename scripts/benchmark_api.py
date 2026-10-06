"""Measure sequential HTTP requests, with an optional real idle interval."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from math import ceil
from pathlib import Path
from statistics import median
import time

import requests


ENDPOINTS = ("/health", "/v1/sample-types", "/v1/catalog/coverage")


def request_sample(session, base_url, path, timeout=120):
    started = time.perf_counter()
    row = {"path": path}
    try:
        response = session.get(base_url + path, timeout=timeout)
        row["milliseconds"] = round((time.perf_counter() - started) * 1000, 3)
        row["status"] = response.status_code
        payload = response.json()
        row["payload_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        row["ok"] = response.status_code == 200 and (
            payload.get("status") == "ok" if path == "/health"
            else bool(payload.get("sample_types")) if path == "/v1/sample-types"
            else bool(payload.get("families")) and payload.get("dependency_audit") is False
        )
    except (requests.RequestException, ValueError, AttributeError) as exc:
        row["milliseconds"] = round((time.perf_counter() - started) * 1000, 3)
        row["ok"] = False
        row["error"] = str(exc)
    return row


def run(base_url, samples=20, idle_seconds=0):
    result = {"base_url": base_url, "started_at": datetime.now(timezone.utc).isoformat(), "samples_per_endpoint": samples}
    with requests.Session() as session:
        if idle_seconds:
            deadline = time.monotonic() + idle_seconds
            print(f"Waiting {idle_seconds}s without sending application traffic. Close other clients.", flush=True)
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                print(f"Idle interval: {ceil(remaining)}s remaining", flush=True)
                time.sleep(min(60, remaining))
            started = time.perf_counter()
            attempts = []
            while time.perf_counter() - started < 120:
                budget = max(0.1, 120 - (time.perf_counter() - started))
                row = request_sample(session, base_url, "/health", timeout=budget)
                attempts.append(row)
                if row["ok"]:
                    break
                time.sleep(min(1, max(0, 120 - (time.perf_counter() - started))))
            result["after_idle"] = {
                "idle_seconds": idle_seconds,
                "spin_down_confirmed": False,
                "health_attempts": attempts,
                "health_ready_ms": round((time.perf_counter() - started) * 1000, 3),
                "first_coverage": request_sample(session, base_url, ENDPOINTS[2]) if attempts[-1]["ok"] else None,
            }
            if not attempts[-1]["ok"]:
                result["ok"] = False
                return result

        result["warmups"] = []
        for path in ENDPOINTS:
            row = request_sample(session, base_url, path)
            result["warmups"].append(row)
            print("Warmup", path, "ok" if row["ok"] else row.get("error", row.get("status")), flush=True)
            if not row["ok"]:
                result["ok"] = False
                return result
        result["requests"] = []
        result["summary"] = {}
        for path in ENDPOINTS:
            rows = [request_sample(session, base_url, path) for _ in range(samples)]
            result["requests"].extend(rows)
            times = sorted(row["milliseconds"] for row in rows if row["ok"])
            result["summary"][path] = {
                "successful": len(times), "failed": samples - len(times),
                "median_ms": round(median(times), 3) if times else None,
                "p95_ms": times[ceil(len(times) * 0.95) - 1] if times else None,
            }
            print(path, result["summary"][path], flush=True)
        result["ok"] = all(row["ok"] for row in result["requests"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--idle-seconds", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1 or (args.idle_seconds and args.idle_seconds < 960):
        parser.error("Use positive samples and at least 960 seconds for an idle measurement.")
    result = run(args.base_url.rstrip("/"), args.samples, args.idle_seconds)
    result.update(label=args.label, commit=args.commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output}")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
