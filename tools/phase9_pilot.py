#!/usr/bin/env python3
"""Bounded local live pilot; never replaces the Phase09 24h/72h evidence gates."""

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.crawling.burnin import assess_pilot  # noqa: E402
from src.crawling.reporting import timestamp  # noqa: E402
from tools.phase9 import (  # noqa: E402
    COMPOSE,
    SOURCE_KEYS,
    command,
    container_json,
    sample,
    scheduler_snapshot,
    write,
)

OUT = ROOT / "artifacts/phase9/pilot"


def read(path):
    return json.loads(path.read_text())


def report(path):
    session = read(path)
    stopped = path.with_suffix(".stop.json")
    if stopped.exists():
        stop = read(stopped)
        if stop["reason"] != "deadline":
            session["stopped_reason"] = stop["reason"]
        if stop["status"] != "PASS":
            session["stopped_reason"] = (
                "Pilot shutdown not verified; inspect stop record"
            )
    result = assess_pilot(session, read(path.with_suffix(".samples.json")))
    write(path.with_suffix(".report.json"), result)
    return result


def stop(path, reason):
    """Attempt every safety action even if an earlier one fails; safe to repeat."""
    session = read(path)
    actions = []
    try:
        result = command(
            COMPOSE
            + [
                "exec",
                "-T",
                "airflow-scheduler",
                "airflow",
                "dags",
                "pause",
                "news_crawling_pipeline",
            ],
            timeout=45,
        )
        actions.append({"action": "pause_dag", "ok": result.returncode == 0})
    except Exception as exc:
        actions.append(
            {"action": "pause_dag", "ok": False, "error": type(exc).__name__}
        )
    for source in session["sources"]:
        try:
            # Use the running scheduler, avoiding an expensive one-off container.
            container_json(
                ["policy", "--source", source, "--live-enabled", "false"],
                scheduler=True,
            )
            actions.append({"action": "disable_live", "source": source, "ok": True})
        except Exception as exc:
            actions.append(
                {
                    "action": "disable_live",
                    "source": source,
                    "ok": False,
                    "error": type(exc).__name__,
                }
            )
    result = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "status": "PASS" if all(a["ok"] for a in actions) else "FAIL",
        "actions": actions,
        "note": "Pause does not cancel in-flight tasks; inspect and settle them before backup/restart.",
    }
    # Preserve a pre-existing incident rather than letting a later timer hide it.
    old_path = path.with_suffix(".stop.json")
    if old_path.exists():
        old = read(old_path)
        if old["reason"] != "deadline":
            result["reason"] = old["reason"]
    with path.with_suffix(".shutdown-attempts.jsonl").open("a") as audit:
        audit.write(json.dumps(result) + "\n")
    write(old_path, result)
    return result


def watch(path):
    session = read(path)
    samples_path = path.with_suffix(".samples.json")
    samples = read(samples_path)
    end = timestamp(session["started_at"]) + timedelta(hours=session["hours"])
    reason = "deadline"

    def interrupted(signum, frame):
        raise InterruptedError("Operator/process signal " + str(signum))

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        while True:
            if path.with_suffix(".stop.json").exists():
                reason = read(path.with_suffix(".stop.json"))["reason"]
                break
            item = sample(session)
            samples.append(item)
            write(samples_path, samples)
            if item.get("collection_error") or item["hard_stop_reasons"]:
                reason = "Hard stop: " + str(
                    item.get("collection_error") or item["hard_stop_reasons"]
                )
                break
            if item["boot_id"] != session["boot_id"]:
                reason = "Host reboot changed pilot window"
                break
            if datetime.now(timezone.utc) >= end:
                break
            remaining = (end - datetime.now(timezone.utc)).total_seconds()
            time.sleep(max(0, min(session["sample_interval_seconds"], remaining)))
    except Exception as exc:
        reason = "Collector interrupted: " + type(exc).__name__
    finally:
        stop(path, reason)
    if reason == "deadline":
        # Let already-running bounded work settle; do not claim a drained queue
        # from a sample collected before the final publication completed.
        settle_until = time.monotonic() + 300
        try:
            while scheduler_snapshot(timestamp(session["started_at"]))[
                "active_scheduled_runs"
            ]:
                if time.monotonic() >= settle_until:
                    break
                time.sleep(10)
            samples.append(sample(session))
            write(samples_path, samples)
        except Exception as exc:
            samples.append(
                {
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "monotonic_seconds": time.monotonic(),
                    "boot_id": session["boot_id"],
                    "collection_error": type(exc).__name__,
                }
            )
            write(samples_path, samples)
    result = report(path)
    print(json.dumps(result, default=str), flush=True)
    return (
        0 if result["status"] == "PASS" else (2 if result["status"] == "PENDING" else 1)
    )


def start(args):
    latest = OUT / "latest.json"
    if latest.exists():
        previous = ROOT / read(latest)["session"]
        previous_data = read(previous)
        previous_end = timestamp(previous_data["started_at"]) + timedelta(
            hours=previous_data["hours"]
        )
        if (
            datetime.now(timezone.utc) < previous_end
            and not previous.with_suffix(".stop.json").exists()
        ):
            raise ValueError(
                "An existing pilot is active; stop/review it before starting another"
            )
    if not args.backup_reference.is_file():
        raise ValueError("Existing reviewed recovery/backup reference required")
    if not args.policy_reference.is_file():
        raise ValueError("Existing technical source-policy review required")
    accepted = read(ROOT / "artifacts/phase9/acceptance.json")
    if accepted.get("status") != "PASS":
        raise ValueError("Functional acceptance must pass first")
    config = container_json(["config-check"], scheduler=True)
    if (
        config["schedule_config"] != "*/30 * * * *"
        or not config["scheduled_live_switch"]
    ):
        raise ValueError(
            "Pilot requires explicit 30-minute scheduled-live configuration"
        )
    if config["scheduled_batch_limit"] != 1:
        raise ValueError("Pilot requires per-source batch limit 1")
    if any(
        not config["sources"][s]["enabled"]
        or not config["sources"][s]["live_enabled"]
        or not config["sources"][s]["policy_review_recorded"]
        for s in args.sources
    ):
        raise ValueError("Selected live source policies must be reviewed and enabled")
    if any(
        v["live_enabled"] for k, v in config["sources"].items() if k not in args.sources
    ):
        raise ValueError("Unselected sources must remain live-disabled")
    now = datetime.now(timezone.utc)
    deadline = (now + timedelta(hours=args.hours)).isoformat()
    for source in args.sources:
        container_json(
            [
                "policy",
                "--source",
                source,
                "--live-enabled",
                "true",
                "--policy-reviewed",
                "--policy-reference",
                str(args.policy_reference.resolve()),
                "--live-until",
                deadline,
            ],
            scheduler=True,
        )
    data = {
        "kind": "pilot",
        "hours": args.hours,
        "sources": args.sources,
        "started_at": now.isoformat(),
        "sample_interval_seconds": 300,
        "monotonic_start": time.monotonic(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "live_opt_in": True,
        "backup_reference": str(args.backup_reference.resolve()),
        "scope": "User-authorized short pilot; 24h/72h remain PENDING",
    }
    first = sample(data)
    if (
        first.get("collection_error")
        or first["hard_stop_reasons"]
        or first["scheduler"]["is_paused"]
    ):
        raise ValueError("Pilot requires healthy telemetry and unpaused scheduler")
    path = OUT / (
        "pilot-" + now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6] + ".json"
    )
    write(path, data)
    write(path.with_suffix(".samples.json"), [first])
    write(OUT / "latest.json", {"session": str(path.relative_to(ROOT))})
    print(
        json.dumps(
            {
                "session": str(path.relative_to(ROOT)),
                "status": "STARTED",
                "required_end": (now + timedelta(hours=args.hours)).isoformat(),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("start")
    begin.add_argument("--hours", type=int, choices=(1, 2, 4), default=4)
    begin.add_argument("--sources", nargs="+", choices=SOURCE_KEYS, required=True)
    begin.add_argument("--backup-reference", type=Path, required=True)
    begin.add_argument("--policy-reference", type=Path, required=True)
    begin.add_argument("--live-opt-in", action="store_true", required=True)
    for name in ("watch", "report", "stop"):
        action = sub.add_parser(name)
        action.add_argument("--session", type=Path)
        if name == "stop":
            action.add_argument("--reason", default="operator_stop")
    args = parser.parse_args()
    if args.command == "start":
        start(args)
        return 0
    if args.session is None:
        args.session = ROOT / read(OUT / "latest.json")["session"]
    if args.command == "watch":
        return watch(args.session)
    result = (
        stop(args.session, args.reason)
        if args.command == "stop"
        else report(args.session)
    )
    print(json.dumps(result, default=str, indent=2))
    if args.command == "report":
        return 0  # Informational status; the JSON verdict remains authoritative.
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
