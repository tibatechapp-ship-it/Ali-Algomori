#!/usr/bin/env python3
"""Restore-verification for the GEOLOGIA second mirror (ADR-0009).

Clones the mirror into a scratch directory, proves the restored history is
byte-identical to the source (branch commit + every tag), and optionally
runs a suite from the restored tree:

  none   hashes only
  smoke  hashes + ``python -m compileall -q src tests`` in the restored tree
         (dependency-free, safe on any runner)
  full   hashes + editable install + the full pytest gate inside the
         restored tree (what CI runs when a real mirror is configured)

Prints a one-line JSON fingerprint (the last stdout line) so runs can be
pinned in reports. Exit codes: 0 pass, 1 verification mismatch,
2 usage error, 3 command failure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command, echoing it for evidence; raise SystemExit(3) on failure."""
    printable = " ".join(cmd)
    print(f"[restore-verify] $ {printable}", flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-6:]
        for line in tail:
            print(f"[restore-verify]   | {line}", file=sys.stderr, flush=True)
        print(f"[restore-verify] command failed rc={proc.returncode}: {printable}", file=sys.stderr)
        raise SystemExit(3)
    return proc.stdout


def rev(repo: Path, ref: str) -> str:
    return run(["git", "rev-parse", ref], cwd=repo).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".", help="source work tree (default: cwd)")
    parser.add_argument("--mirror-url", required=True, help="mirror URL or bare-repo path")
    parser.add_argument("--branch", default="main", help="governing branch to verify")
    parser.add_argument("--suite", choices=["none", "smoke", "full"], default="smoke")
    parser.add_argument("--workdir", default=None, help="scratch dir (default: temp)")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not (source / ".git").exists():
        print(f"[restore-verify] --source is not a git work tree: {source}", file=sys.stderr)
        raise SystemExit(2)

    with tempfile.TemporaryDirectory(prefix="geologia-mirror-restore-", dir=args.workdir) as tmp:
        restore = Path(tmp) / "restore"
        run(
            [
                "git",
                "clone",
                "--no-local",
                "--quiet",
                "--branch",
                args.branch,
                args.mirror_url,
                str(restore),
            ]
        )

        mismatches: list[str] = []
        local_branch = rev(source, f"refs/heads/{args.branch}")
        restored_branch = rev(restore, f"refs/heads/{args.branch}")
        if local_branch != restored_branch:
            mismatches.append(f"branch {args.branch}: {local_branch} != {restored_branch}")

        source_tags: dict[str, str] = {}
        listing = run(
            ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/tags"],
            cwd=source,
        )
        for line in listing.splitlines():
            name, obj = line.split()
            source_tags[name] = obj
        restored_listing = run(
            ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/tags"],
            cwd=restore,
        )
        restored_tags = dict(line.split() for line in restored_listing.splitlines())
        for name, obj in sorted(source_tags.items()):
            if restored_tags.get(name) != obj:
                mismatches.append(
                    f"tag {name}: {obj} != {restored_tags.get(name, 'absent')}"
                )

        suite_result = "skipped"
        if not mismatches and args.suite != "none":
            if args.suite == "smoke":
                run([sys.executable, "-m", "compileall", "-q", "src", "tests"], cwd=restore)
                suite_result = "compileall-ok"
            else:
                run(
                    [sys.executable, "-m", "pip", "install", "-q", "-e", ".[dev,lint,geo]"],
                    cwd=restore,
                )
                run([sys.executable, "-m", "pytest", "-q"], cwd=restore)
                suite_result = "pytest-ok"

        if mismatches:
            for item in mismatches:
                print(f"[restore-verify] MISMATCH {item}", file=sys.stderr)
            print("[restore-verify] FAILED: restored history is not identical", file=sys.stderr)
            raise SystemExit(1)

        fingerprint = {
            "result": "pass",
            "branch": args.branch,
            "commit": local_branch,
            "tags": len(source_tags),
            "suite": suite_result,
            "mirror": args.mirror_url,
            "python": sys.version.split()[0],
            "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        print("[restore-verify] PASS restored history identical to source")
        print(json.dumps(fingerprint, ensure_ascii=False))


if __name__ == "__main__":
    main()
