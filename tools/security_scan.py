#!/usr/bin/env python3
"""Pinned, offline secret scanning with metadata-only output. No issuer requests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "8.30.1"
ARCHIVE_SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
CACHE = Path.home() / ".cache" / "financial-news-security" / f"gitleaks-{VERSION}"
MODES = ("working-tree", "staged", "history", "ignored-config")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def install() -> Path:
    """Install a verified release outside the repository; never execute a pipe."""
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
        raise ValueError(
            "install_requires_linux_x64; install verified pinned version manually"
        )
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = f"gitleaks_{VERSION}_linux_x64.tar.gz"
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/{name}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "financial-news-security"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read()
    if hashlib.sha256(body).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("release_checksum_mismatch")
    with tempfile.TemporaryFile() as archive:
        archive.write(body)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as package:
            member = package.getmember("gitleaks")
            if not member.isfile():
                raise ValueError("invalid_release_member")
            binary = package.extractfile(member).read()
    fd, temporary = tempfile.mkstemp(prefix="gitleaks-", dir=CACHE)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(binary)
        os.chmod(temporary, 0o700)
        os.replace(temporary, CACHE / "gitleaks")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return CACHE / "gitleaks"


def resolve_binary(explicit: str | None = None) -> str:
    candidate = explicit or os.getenv("GITLEAKS_BIN") or shutil.which("gitleaks")
    if not candidate and (CACHE / "gitleaks").exists():
        candidate = str(CACHE / "gitleaks")
    if not candidate:
        raise ValueError("scanner_missing; run make phase10-security-tools")
    completed = subprocess.run(
        [candidate, "version"], capture_output=True, text=True, timeout=15
    )
    if completed.returncode or completed.stdout.strip() != VERSION:
        raise ValueError("scanner_version_mismatch")
    return candidate


def git_paths(root: Path, *args: str) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", *args], cwd=root, capture_output=True, check=True
    )
    return [Path(os.fsdecode(item)) for item in completed.stdout.split(b"\0") if item]


def snapshot(root: Path, target: Path, mode: str) -> tuple[int, list[str]]:
    """Snapshot only intended files; private temporary tree is outside the repo."""
    args = (
        ("--others", "--ignored", "--exclude-standard")
        if mode == "ignored-config"
        else ("--cached", "--others", "--exclude-standard")
    )
    paths = git_paths(root, *args)
    if mode == "ignored-config":
        # Explicitly inspect local env/key material without traversing all caches/data.
        paths = [
            p
            for p in paths
            if (
                p.name == ".env"
                or p.name.startswith(".env.")
                or p.suffix in {".pem", ".key", ".p12", ".pfx"}
                or p.parts[0] in {"secrets", ".secrets"}
            )
        ]
    count = 0
    gaps = []
    for relative in sorted(set(paths)):
        source = root / relative
        if source.is_symlink():
            gaps.append("symlink_not_followed")
            continue
        if (
            not source.exists()
        ):  # Deleted worktree file; staged mode inspects index separately.
            continue
        if not source.is_file():
            gaps.append("non_regular_file")
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Do not chmod a hardlink: its permission bits belong to the source inode.
        try:
            os.link(source, destination)
        except OSError:
            with source.open("rb") as stream, destination.open("xb") as output:
                os.chmod(destination, 0o600)
                shutil.copyfileobj(stream, output)
        count += 1
    return count, sorted(set(gaps))


def safe_findings(rows: list[dict], scan_root: Path) -> list[dict]:
    """Never export Match, Secret, Fingerprint, author, message, or entropy."""
    findings = []
    for row in rows:
        filename = str(row.get("File", ""))
        try:
            filename = str(Path(filename).relative_to(scan_root))
        except ValueError:
            pass  # Git reports relative paths already.
        commit = str(row.get("Commit", ""))
        findings.append(
            {
                "rule": str(row.get("RuleID", "unknown")),
                "file": filename,
                "line": int(row.get("StartLine", 0)),
                "commit": commit
                if len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)
                else None,
                "state": "OPEN_REVIEW_REQUIRED",
                "credential_validity": "UNKNOWN_NOT_CONTACTED",
            }
        )
    return findings


def scan(mode: str, root: Path = ROOT, binary: str | None = None) -> dict:
    started = now()
    root = root.resolve()
    result = {
        "mode": mode,
        "started_at": started,
        "scanner_version": VERSION,
        "status": "BLOCKED",
        "exit_code": 2,
        "findings": [],
        "provider_validation": "NOT_PERFORMED",
        "secret_values_retained": False,
        "coverage_gaps": [],
    }
    try:
        executable = resolve_binary(binary)
        if mode not in MODES:
            raise ValueError("unsupported_scan_mode")
        with tempfile.TemporaryDirectory(prefix="financial-news-security-") as private:
            directory = Path(private)
            os.chmod(directory, 0o700)
            report = directory / "scanner-redacted.json"
            config = ROOT / ".gitleaks.toml"
            # An empty, private ignore directory prevents implicit fingerprint baselines.
            ignore = directory / "ignore"
            ignore.mkdir()
            scan_root = root
            if mode in ("working-tree", "ignored-config"):
                scan_root = directory / "snapshot"
                scan_root.mkdir(mode=0o700)
                count, gaps = snapshot(root, scan_root, mode)
                result.update(scanned_files=count, coverage_gaps=gaps)
                command = [executable, "dir", str(scan_root)]
            else:
                command = [executable, "git", str(root)]
                if mode == "history":
                    shallow = subprocess.run(
                        ["git", "rev-parse", "--is-shallow-repository"],
                        cwd=root,
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout.strip()
                    if shallow != "false":
                        raise ValueError("history_scan_requires_full_local_history")
                    command.append("--log-opts=--all --full-history")
                else:
                    command.extend(["--pre-commit", "--staged"])
            command.extend(
                [
                    "--config",
                    str(config),
                    "--redact=100",
                    "--ignore-gitleaks-allow",
                    "--gitleaks-ignore-path",
                    str(ignore),
                    "--no-banner",
                    "--no-color",
                    "--report-format=json",
                    "--report-path",
                    str(report),
                    "--timeout=600",
                ]
            )
            # Even redacted scanner streams may contain context; neither stream is emitted.
            completed = subprocess.run(
                command, cwd=root, capture_output=True, timeout=660
            )
            if completed.returncode not in (0, 1) or not report.exists():
                raise ValueError("scanner_execution_failed; raw_streams_withheld")
            rows = json.loads(report.read_text()) or []
            if not isinstance(rows, list):
                raise ValueError("invalid_scanner_report")
            if completed.returncode == 1 and not rows:
                raise ValueError("scanner_failed_without_findings")
            result["findings"] = safe_findings(rows, scan_root)
            if result["coverage_gaps"]:
                result["status"] = "BLOCKED"
            else:
                result["status"] = "FAIL" if rows else "PASS"
                result["exit_code"] = 1 if rows else 0
            result["scanner_exit_code"] = completed.returncode
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        # Exception strings can contain raw command output/URLs; expose the type only.
        result["error_kind"] = type(exc).__name__
    result["finished_at"] = now()
    result["coverage"] = {
        "history": "all local reachable refs; remote-only PR/fork/cache/unreachable objects not claimed",
        "staged": "Git index diff only; unstaged bytes cannot mask a staged secret",
        "working-tree": "tracked plus untracked non-ignored files; no symlink following",
        "ignored-config": "ignored local env/key files only; not a clean-release gate by itself",
    }[mode]
    result["format_limits"] = (
        "No image OCR or archive expansion; external CI logs/images require separate scans"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(*MODES, "install"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--gitleaks")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "install":
        path = install()
        print(json.dumps({"status": "PASS", "version": VERSION, "binary": str(path)}))
        return 0
    result = scan(args.mode, args.root, args.gitleaks)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    # Full sanitized metadata is opt-in via --output; stdout stays small.
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("mode", "status", "exit_code", "coverage_gaps")
            }
        )
    )
    print(json.dumps({"finding_count": len(result["findings"])}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
