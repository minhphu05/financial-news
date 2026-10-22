#!/usr/bin/env python3
"""Audit installed local images/packages; output only package/CVE metadata."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TRIVY_VERSION = "0.76.1"
PIP_AUDIT_VERSION = "2.10.1"


def execute(args, timeout=420):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 2, "", "withheld")


def audit_image(image, trivy):
    result = {
        "image": image,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "image_scan_status": "BLOCKED",
        "dependency_status": "BLOCKED",
    }
    identity = execute(["docker", "image", "inspect", image])
    if identity.returncode:
        return result
    metadata = json.loads(identity.stdout)[0]
    result.update(
        image_id=metadata["Id"],
        image_user=metadata.get("Config", {}).get("User") or "root/default",
        repo_digests=metadata.get("RepoDigests", []),
    )
    version = execute([trivy, "--version"])
    with tempfile.TemporaryDirectory(prefix="financial-news-image-audit-") as private:
        directory = Path(private)
        os.chmod(directory, 0o700)
        if version.returncode == 0 and f"Version: {TRIVY_VERSION}" in version.stdout:
            report = directory / "vulnerabilities.json"
            command = [
                trivy,
                "image",
                "--image-src",
                "docker",
                "--scanners",
                "vuln",
                "--format",
                "json",
                "--output",
                str(report),
                "--quiet",
                "--timeout",
                "5m",
                "--exit-code",
                "1",
                "--severity",
                "HIGH,CRITICAL",
                image,
            ]
            completed = execute(command, timeout=360)
            result["trivy_exit_code"] = completed.returncode
            if completed.returncode in (0, 1) and report.exists():
                raw = json.loads(report.read_text())
                findings = [
                    {
                        key: v.get(key)
                        for key in (
                            "VulnerabilityID",
                            "PkgName",
                            "InstalledVersion",
                            "FixedVersion",
                            "Severity",
                        )
                    }
                    for r in raw.get("Results", [])
                    for v in r.get("Vulnerabilities", [])
                ]
                result["vulnerabilities"] = findings
                result["severity_counts"] = dict(
                    Counter(v["Severity"] for v in findings)
                )
                result["image_scan_status"] = (
                    "FAIL"
                    if findings
                    else ("PASS" if completed.returncode == 0 else "BLOCKED")
                )
        # Enumerate installed metadata in a read-only, networkless, unmounted container.
        program = "import importlib.metadata as m,json;print(json.dumps(sorted((d.metadata['Name'],d.version) for d in m.distributions())))"
        inventory = execute(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                "python3",
                image,
                "-c",
                program,
            ],
            timeout=90,
        )
        if inventory.returncode == 0 and shutil.which("uv"):
            packages = json.loads(inventory.stdout)
            requirements = directory / "installed.txt"
            # Conservative PEP440 subset. Distro-only versions stay explicit gaps;
            # they must not abort collection of all other package findings.
            valid = [
                (n, v)
                for n, v in packages
                if re.fullmatch(r"[A-Za-z0-9_.-]+", n)
                and re.fullmatch(
                    r"\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?(?:\+[A-Za-z0-9.]+)?",
                    v,
                )
            ]
            requirements.write_text("".join(f"{n}=={v}\n" for n, v in valid))
            result["installed_packages"] = [{"name": n, "version": v} for n, v in valid]
            result["unqueryable_package_count"] = len(packages) - len(valid)
            result["unqueryable_packages"] = [
                {"name": n, "version": v} for n, v in packages if (n, v) not in valid
            ]
            groups = independent_requirement_groups(valid)
            findings, skipped, errors, codes = [], [], [], []
            for number, group in enumerate(groups):
                # Two installed distributions of one package must both be audited,
                # rather than silently discarding the older one or causing a solver conflict.
                requirements.write_text("".join(f"{n}=={v}\n" for n, v in group))
                report = directory / f"python-audit-{number}.json"
                command = [
                    "uv",
                    "tool",
                    "run",
                    "--from",
                    f"pip-audit=={PIP_AUDIT_VERSION}",
                    "pip-audit",
                    "--no-deps",
                    "--disable-pip",
                    "--progress-spinner",
                    "off",
                    "--desc",
                    "off",
                    "--aliases",
                    "off",
                    "-r",
                    str(requirements),
                    "-f",
                    "json",
                    "-o",
                    str(report),
                ]
                completed = execute(command, timeout=600)
                codes.append(completed.returncode)
                if completed.returncode not in (0, 1) or not report.exists():
                    errors.append(number)
                    continue
                data = json.loads(report.read_text())
                dependencies = data.get("dependencies", [])
                if not dependencies:
                    errors.append(number)
                elif completed.returncode == 1 and not any(
                    d.get("vulns") or d.get("skip_reason") for d in dependencies
                ):
                    errors.append(number)
                findings.extend(
                    {
                        "name": d.get("name"),
                        "version": d.get("version"),
                        "vulnerabilities": [
                            {
                                "id": v.get("id"),
                                "fix_versions": v.get("fix_versions", []),
                            }
                            for v in d.get("vulns", [])
                        ],
                    }
                    for d in dependencies
                    if d.get("vulns")
                )
                skipped.extend(
                    d.get("name") for d in dependencies if d.get("skip_reason")
                )
            result.update(
                python_findings=findings,
                skipped_package_names=skipped,
                pip_audit_exit_codes=codes,
                collection_error_groups=errors,
                audit_groups=len(groups),
            )
            result["dependency_status"] = (
                "BLOCKED"
                if skipped or errors or len(valid) != len(packages)
                else ("FAIL" if findings else "PASS")
            )
    result["limits"] = (
        "Local image ID and installed packages only; Trivy HIGH/CRITICAL. Not an exploit test, full deleted-layer secret scan, remote registry audit, or automatic upgrade."
    )
    return result


def independent_requirement_groups(packages):
    """Place conflicting installed versions into separate, complete advisory queries."""
    groups = []
    seen = set()
    for name, version in packages:
        canonical = re.sub(r"[-_.]+", "-", name).lower()
        if (canonical, version) in seen:
            continue
        seen.add((canonical, version))
        for group in groups:
            if all(re.sub(r"[-_.]+", "-", n).lower() != canonical for n, _ in group):
                group.append((name, version))
                break
        else:
            groups.append([(name, version)])
    return groups


def audit_direct():
    """CI check for exact direct declarations only; never claim transitive coverage."""
    dockerfiles = [
        ROOT / f"docker/{name}/Dockerfile"
        for name in ("news-pipeline", "airflow", "metadata-tools")
    ]
    declarations = sorted(
        set(
            match.group(0)
            for file in dockerfiles
            for match in re.finditer(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?==[0-9][A-Za-z0-9_.+-]*",
                file.read_text(),
            )
        )
    )
    result = {
        "scope": "exact direct Python declarations in three active Dockerfiles; not transitive or OS dependencies",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED",
        "requirements": declarations,
        "pip_audit_version": PIP_AUDIT_VERSION,
    }
    with tempfile.TemporaryDirectory(prefix="financial-news-direct-audit-") as private:
        req = Path(private) / "requirements.txt"
        req.write_text("\n".join(declarations) + "\n")
        report = Path(private) / "report.json"
        prefix = (
            [
                "uv",
                "tool",
                "run",
                "--from",
                f"pip-audit=={PIP_AUDIT_VERSION}",
                "pip-audit",
            ]
            if shutil.which("uv")
            else [sys.executable, "-m", "pip_audit"]
        )
        command = [
            *prefix,
            "--no-deps",
            "--disable-pip",
            "--strict",
            "--desc",
            "off",
            "--aliases",
            "off",
            "--progress-spinner",
            "off",
            "-r",
            str(req),
            "-f",
            "json",
            "-o",
            str(report),
        ]
        completed = execute(command, timeout=600)
        result["exit_code"] = completed.returncode
        if completed.returncode in (0, 1) and report.exists():
            data = json.loads(report.read_text())
            rows = data.get("dependencies", [])
            result["findings"] = [
                {
                    "name": r.get("name"),
                    "version": r.get("version"),
                    "vulns": [
                        {"id": v.get("id"), "fix_versions": v.get("fix_versions", [])}
                        for v in r.get("vulns", [])
                    ],
                }
                for r in rows
                if r.get("vulns")
            ]
            result["skipped_packages"] = [
                r.get("name") for r in rows if r.get("skip_reason")
            ]
            if rows and not result["skipped_packages"]:
                result["status"] = (
                    "FAIL"
                    if result["findings"]
                    else ("PASS" if completed.returncode == 0 else "BLOCKED")
                )
    out = ROOT / "artifacts/phase10"
    out.mkdir(parents=True, exist_ok=True)
    (out / "direct-dependency-audit.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "exit_code": result.get("exit_code"),
                "findings": len(result.get("findings", [])),
            }
        )
    )
    return 0 if result["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--direct-only", action="store_true")
    parser.add_argument("--trivy", default=os.getenv("TRIVY_BIN", "trivy"))
    args = parser.parse_args()
    if args.direct_only:
        return audit_direct()
    if not args.image:
        parser.error("use --image or --direct-only")
    results = []
    out = ROOT / "artifacts/phase10"
    out.mkdir(parents=True, exist_ok=True)
    for image in args.image:
        result = audit_image(image, args.trivy)
        results.append(result)
        (out / "supply-chain.json").write_text(
            json.dumps(
                {
                    "trivy_version": TRIVY_VERSION,
                    "pip_audit_version": PIP_AUDIT_VERSION,
                    "images": results,
                },
                indent=2,
            )
            + "\n"
        )
        print(
            json.dumps(
                {
                    key: result.get(key)
                    for key in (
                        "image",
                        "image_scan_status",
                        "dependency_status",
                        "severity_counts",
                    )
                }
            ),
            flush=True,
        )
    return (
        0
        if all(
            r["image_scan_status"] == r["dependency_status"] == "PASS" for r in results
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
