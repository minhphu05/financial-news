"""Conservative real-time burn-in evidence gates; never sleep or simulate runtime."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .reporting import timestamp


def assess(session, samples, *, now=None):
    if session.get("kind", "burnin") != "burnin" or session["hours"] not in (24, 72):
        raise ValueError("burnin_duration_must_be_24_or_72_real_hours")
    return _assess_window(session, samples, now=now)


def assess_pilot(session, samples, *, now=None):
    """A short live pilot never satisfies the formal 24h/72h burn-in gates."""
    if session.get("kind") != "pilot" or session["hours"] not in (1, 2, 4):
        raise ValueError("pilot_requires_explicit_kind_and_1_2_or_4_hours")
    result = {
        **_assess_window(session, samples, now=now),
        "kind": "pilot",
        "scope": "Short live scheduled pilot only; not Phase09 24h/72h acceptance",
        "burnin_24h": "PENDING",
        "burnin_72h": "PENDING",
        "cloud_verdict": "NOT READY FOR CLOUD MIGRATION",
    }
    if samples and samples[-1].get("scheduler", {}).get("active_scheduled_runs"):
        result["gaps"].append("Scheduled tasks have not settled after pilot shutdown")
        if result["status"] == "PASS":
            result["status"] = "PENDING"
    return result


def _assess_window(session, samples, *, now=None):
    now = timestamp(now or datetime.now(timezone.utc))
    start = timestamp(session["started_at"])
    hours = session["hours"]
    end = start + timedelta(hours=hours)
    result = {
        "started_at": start,
        "required_end": end,
        "observed_at": now,
        "required_hours": hours,
        "elapsed_hours": max(0, (now - start).total_seconds() / 3600),
        "sample_count": len(samples),
        "status": "PENDING",
        "gaps": [],
    }
    if session.get("stopped_reason"):
        return {**result, "status": "FAIL", "gaps": [session["stopped_reason"]]}
    if not samples:
        return {
            **result,
            "gaps": [
                "No real evidence samples; elapsed wall time alone is insufficient"
            ],
        }
    interval = session["sample_interval_seconds"]
    times = [timestamp(s["observed_at"]) for s in samples]
    result["sampled_end"] = times[-1]
    if any(
        t < start or t > now + timedelta(seconds=5) for t in times
    ) or times != sorted(times):
        return {
            **result,
            "status": "FAIL",
            "gaps": ["Invalid sample time ordering/window"],
        }
    if any(s.get("boot_id") != session["boot_id"] for s in samples):
        return {
            **result,
            "status": "FAIL",
            "gaps": ["Host reboot changed the measured unattended window"],
        }
    if now < end:
        result["gaps"].append("Required real-time duration has not elapsed")
        return result
    if (
        times[-1] < end
        or samples[-1]["monotonic_seconds"] - session["monotonic_start"] < hours * 3600
    ):
        result["gaps"].append(
            "Samples do not cover the full wall-clock and monotonic duration"
        )
    observed_times = [start, *[t for t in times if t <= end], end]
    if any(
        (b - a).total_seconds() > interval * 2.5
        for a, b in zip(observed_times, observed_times[1:])
    ):
        result["gaps"].append(
            "Evidence gap exceeds 2.5 sample intervals (sleep/outage cannot be hidden)"
        )
    if not session.get("backup_reference") or not session.get("live_opt_in"):
        result["gaps"].append("Missing backup reference or explicit live authorization")
    if any(s.get("collection_error") for s in samples):
        result["gaps"].append("At least one evidence sample could not be collected")
    if any(s.get("hard_stop_reasons") for s in samples):
        return {
            **result,
            "status": "FAIL",
            "gaps": [
                "Hard-stop condition occurred; inspect recorded samples/incidents"
            ],
        }
    if samples[-1].get("scheduler", {}).get("overlapping_runs"):
        return {**result, "status": "FAIL", "gaps": ["Scheduled DAG runs overlap"]}
    if (
        samples[-1].get("scheduler", {}).get("truncated")
        or len(samples[-1].get("scheduler", {}).get("scheduled_runs", [])) < 2
    ):
        result["gaps"].append(
            "Insufficient actual scheduler history or truncated history"
        )
    report = samples[-1].get("report", {})
    if report.get("data_kind") != "live":
        result["gaps"].append("Fixture observations cannot satisfy live burn-in")
    for source in session["sources"]:
        row = report.get("sources", {}).get(source, {})
        if row.get("scheduled_runs", 0) < 2:
            result["gaps"].append(
                source + ": fewer than two actual scheduled source runs"
            )
        if (
            not row.get("latest_successful_crawl")
            or timestamp(row["latest_successful_crawl"]) < start
        ):
            result["gaps"].append(
                source + ": no successful live crawl in the measured window"
            )
        if (
            row.get("pending_batches_end", 0)
            or row.get("failed_runs", 0)
            or row.get("partial_runs", 0)
            or row.get("reconciliation", {}).get("FAIL", 0)
        ):
            result["gaps"].append(
                source
                + ": backlog/failures need review; conservative automatic go/no-go is not PASS"
            )
    if not result["gaps"]:
        result["status"] = "PASS"
    return result


def verified_24h_report(path):
    """A functional PASS JSON cannot authorize the 72h stage."""
    path = Path(path)
    report = json.loads(path.read_text())
    if (
        report.get("status") != "PASS"
        or report.get("required_hours") != 24
        or not path.name.endswith(".report.json")
    ):
        raise ValueError("72h_requires_a_real_24h_report_and_underlying_samples")
    session_path = path.with_name(path.name.removesuffix(".report.json") + ".json")
    session = json.loads(session_path.read_text())
    samples = json.loads(session_path.with_suffix(".samples.json").read_text())
    assessed = assess(session, samples)
    if session.get("hours") != 24 or assessed["status"] != "PASS":
        raise ValueError("prior_24h_evidence_does_not_satisfy_real_time_gates")
    return assessed
