#!/usr/bin/env python3
"""Read-only audit of provisioned dashboards against Prometheus and Grafana."""

import argparse
import json
import math
import re
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "monitoring/grafana/provisioning/dashboards/json"


def request(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        # Only local PromQL/model diagnostics, never env/credential values.
        raise RuntimeError(exc.read().decode()[:600]) from exc


def interpolate(expression, variables, selected=None):
    selected = selected or {}
    for variable in variables:
        name = variable["name"]
        value = selected.get(name, variable.get("current", {}).get("value", ""))
        if value == "$__all" or value == ["$__all"]:
            regex_value = variable["allValue"]
            plain = regex_value
        else:
            values = value if isinstance(value, list) else [value]
            plain = "|".join(values)
            regex_value = "|".join(re.escape(v).replace("\\", "\\\\") for v in values)
        expression = expression.replace("${" + name + ":regex}", regex_value)
        expression = expression.replace("${" + name + "}", plain)
    if re.search(r"\$\{?\w", expression):
        raise ValueError("Unresolved dashboard variable: " + expression)
    return expression


def audit(prometheus, grafana, output):
    now = time.time()
    rows = []
    errors = []
    for path in sorted(DIRECTORY.glob("*.json")):
        dashboard = json.loads(path.read_text())
        uid = dashboard["uid"]
        variables = dashboard.get("templating", {}).get("list", [])
        try:
            live = request(grafana + "/api/dashboards/uid/" + uid)["dashboard"]
            if [(p["id"], p.get("targets", [])) for p in live["panels"]] != [
                (p["id"], p.get("targets", [])) for p in dashboard["panels"]
            ]:
                errors.append(
                    uid
                    + ": provisioned model differs from file; wait for provider polling"
                )
        except Exception as exc:
            errors.append(uid + ": Grafana model " + str(exc))
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                row = {"dashboard": uid, "panel": panel["id"], "title": panel["title"]}
                try:
                    expression = interpolate(target["expr"], variables)
                    row["expr"] = expression
                    result = request(
                        prometheus + "/api/v1/query?" + urlencode({"query": expression})
                    )
                    if result.get("status") != "success":
                        raise RuntimeError(str(result))
                    values = result["data"]["result"]
                    row["series"] = len(values)
                    row["warnings"] = result.get("warnings", [])
                    row["non_finite"] = sum(
                        not math.isfinite(float(v["value"][1])) for v in values
                    )
                    if row["non_finite"]:
                        errors.append(
                            uid + "/" + str(panel["id"]) + ": non-finite values"
                        )
                    fields = set(
                        re.findall(r"\{\{(\w+)\}\}", target.get("legendFormat", ""))
                    )
                    missing_labels = (
                        sorted(
                            fields - set().union(*(v["metric"].keys() for v in values))
                        )
                        if values
                        else []
                    )
                    row["missing_legend_labels"] = missing_labels
                    if missing_labels:
                        errors.append(
                            uid
                            + "/"
                            + str(panel["id"])
                            + ": nonexistent legend labels "
                            + str(missing_labels)
                        )
                    query = {
                        **target,
                        "expr": expression,
                        "datasource": {"type": "prometheus", "uid": "prometheus-main"},
                        "intervalMs": 10000,
                        "maxDataPoints": 360,
                    }
                    response = request(
                        grafana + "/api/ds/query",
                        {
                            "from": str(int((now - 3600) * 1000)),
                            "to": str(int(now * 1000)),
                            "queries": [query],
                        },
                    )
                    frames = response.get("results", {}).get(target["refId"], {})
                    if frames.get("error") or frames.get("status", 200) >= 400:
                        raise RuntimeError(str(frames.get("error", frames)))
                    row["grafana_frames"] = len(frames.get("frames", []))
                    row["status"] = "PASS"
                except Exception as exc:
                    row.update(status="FAIL", error=str(exc))
                    errors.append(uid + "/" + str(panel["id"]) + ": " + str(exc))
                rows.append(row)
        # Check single-source/topic interpolation, not only the default All regex.
        selected = {
            v["name"]: next(o["value"] for o in v["options"] if o["value"] != "$__all")
            for v in variables
        }
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                try:
                    expression = interpolate(target["expr"], variables, selected)
                    result = request(
                        prometheus + "/api/v1/query?" + urlencode({"query": expression})
                    )
                    if result.get("status") != "success":
                        raise RuntimeError(str(result))
                except Exception as exc:
                    errors.append(
                        uid + "/" + str(panel["id"]) + ": single selection " + str(exc)
                    )
    result = {
        "checked_at_epoch_seconds": now,
        "status": "PASS" if not errors else "FAIL",
        "dashboards": len(list(DIRECTORY.glob("*.json"))),
        "queries": len(rows),
        "errors": errors,
        "panels": rows,
        "scope": "Current/default + single variable selection, Grafana query API and file provisioning; empty optional series remain N/A, not manufactured zero or quality evaluation",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: result[k] for k in ("status", "dashboards", "queries", "errors")},
            ensure_ascii=False,
            indent=2,
        )
    )
    for row in rows:
        if row.get("series") == 0:
            print("N/A:", row["dashboard"], row["panel"], row["title"])
    return 0 if not errors else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus", default="http://localhost:9090")
    parser.add_argument("--grafana", default="http://localhost:3000")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/phase9/dashboard-review/queries-after.json",
    )
    args = parser.parse_args()
    return audit(args.prometheus.rstrip("/"), args.grafana.rstrip("/"), args.output)


if __name__ == "__main__":
    raise SystemExit(main())
