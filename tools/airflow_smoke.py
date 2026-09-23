#!/usr/bin/env python3
"""Trigger a real scheduler-managed DAG run and wait through Airflow's REST API."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4


TERMINAL_STATES = {"success", "failed"}


def _request(url: str, username: str, password: str, payload: dict | None = None) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(
        url,
        data=body,
        method="GET" if payload is None else "POST",
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            value = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Airflow API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach Airflow API at {url}: {exc.reason}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Airflow API returned an unexpected payload for {url}")
    return value


def _wait_for_api(base_url: str, username: str, password: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    last_error = "Airflow API is not ready"
    while time.monotonic() < deadline:
        try:
            health = _request(f"{base_url}/health", username, password)
            if health.get("metadatabase", {}).get("status") == "healthy":
                print(json.dumps({"event": "api_ready", "metadatabase": "healthy"}), flush=True)
                return
            last_error = f"Airflow health payload is not healthy: {health}"
        except RuntimeError as exc:
            last_error = str(exc)
        time.sleep(2)
    raise TimeoutError(f"Timed out after {timeout}s waiting for Airflow API: {last_error}")


def run_smoke(dag_id: str, timeout: int, interval: int, conf: dict) -> dict:
    base_url = os.getenv("AIRFLOW_API_BASE_URL", "http://airflow-webserver:8080").rstrip("/")
    username = os.getenv("AIRFLOW_ADMIN_USERNAME")
    password = os.getenv("AIRFLOW_ADMIN_PASSWORD")
    if not username or not password:
        raise RuntimeError("AIRFLOW_ADMIN_USERNAME and AIRFLOW_ADMIN_PASSWORD are required")
    _wait_for_api(base_url, username, password)

    logical_date = datetime.now(timezone.utc) - timedelta(seconds=2)
    timestamp = logical_date.strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"smoke__{timestamp}__{uuid4().hex[:8]}"
    dag_path = quote(dag_id, safe="")
    run_path = quote(run_id, safe="")
    collection_url = f"{base_url}/api/v1/dags/{dag_path}/dagRuns"
    detail_url = f"{collection_url}/{run_path}"
    created = _request(
        collection_url,
        username,
        password,
        {"dag_run_id": run_id, "logical_date": logical_date.isoformat(), "conf": conf},
    )
    print(json.dumps({
        "event": "triggered",
        "dag_id": dag_id,
        "dag_run_id": created.get("dag_run_id", run_id),
        "logical_date": created.get("logical_date", logical_date.isoformat()),
        "state": created.get("state"),
    }), flush=True)

    deadline = time.monotonic() + timeout
    last_state = None
    while time.monotonic() < deadline:
        current = _request(detail_url, username, password)
        state = current.get("state")
        if state != last_state:
            print(json.dumps({"event": "state", "dag_id": dag_id, "dag_run_id": run_id, "state": state}), flush=True)
            last_state = state
        if state in TERMINAL_STATES:
            if state != "success":
                raise RuntimeError(f"DAG {dag_id} run {run_id} finished with state {state}")
            print(json.dumps({"event": "completed", "dag_id": dag_id, "dag_run_id": run_id, "state": state}), flush=True)
            return current
        time.sleep(interval)
    raise TimeoutError(f"Timed out after {timeout}s waiting for DAG {dag_id} run {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dag_id")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--conf", default="{}", help="JSON object passed as DagRun conf")
    args = parser.parse_args()
    try:
        conf = json.loads(args.conf)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid --conf JSON: {exc}") from exc
    if not isinstance(conf, dict):
        raise SystemExit("--conf must be a JSON object")
    if args.timeout <= 0 or args.interval <= 0:
        raise SystemExit("--timeout and --interval must be positive")
    try:
        run_smoke(args.dag_id, args.timeout, args.interval, conf)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
