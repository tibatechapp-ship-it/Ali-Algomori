"""Mirror-independence machinery (ADR-0009): sync script + restore verification.

Every test here is offline and disposable: fixtures build throwaway git
repositories, so no network and no mutation of the real project repo happens.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SYNC = ROOT / "scripts" / "mirror_sync.sh"
VERIFY = ROOT / "scripts" / "mirror_restore_verify.py"
WORKFLOW = ROOT / ".github" / "workflows" / "mirror.yml"

NO_SIGN = ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *NO_SIGN, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def _run_script(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.pop("GEOLOGIA_MIRROR_REMOTE_URL", None)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def _init_source_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "aigeologia@gmail.com")
    _git(path, "config", "user.name", "GEOLOGIA mirror fixture")
    (path / "README.md").write_text("mirror independence fixture\n", encoding="utf-8")
    (path / "src").mkdir()
    (path / "src" / "__init__.py").write_text("", encoding="utf-8")
    (path / "tests").mkdir()
    (path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "fixture commit")
    _git(path, "tag", "-a", "v9.9.9", "-m", "annotated fixture tag")
    _git(path, "tag", "light-fixture-tag")
    return path


def _init_bare(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path.parent, "init", "--bare", "-b", "main", path.name)
    return path


def test_sync_script_parses_and_declares_its_contract():
    subprocess.run(["bash", "-n", str(SYNC)], check=True, capture_output=True, text=True)
    body = SYNC.read_text(encoding="utf-8")
    assert "GEOLOGIA_MIRROR_REMOTE_URL" in body
    assert "refusing to mirror into the origin remote itself" in body
    assert "--force" not in body, "mirror sync must stay fast-forward-only"


def test_sync_skips_cleanly_without_mirror_url(tmp_path):
    src = _init_source_repo(tmp_path / "src")
    proc = _run_script(["bash", str(SYNC), "--repo", str(src)])
    assert proc.returncode == 0
    assert "skipped" in proc.stdout
    assert "external activation is pending" in proc.stdout


def test_sync_rejects_unsupported_url_scheme(tmp_path):
    src = _init_source_repo(tmp_path / "src")
    proc = _run_script(["bash", str(SYNC), "--repo", str(src), "--url", "ftp://example.test/x"])
    assert proc.returncode == 2
    assert "unsupported mirror URL scheme" in proc.stderr


def test_sync_refuses_mirroring_into_origin(tmp_path):
    src = _init_source_repo(tmp_path / "src")
    origin = _init_bare(tmp_path / "origin.git")
    _git(src, "remote", "add", "origin", str(origin))
    proc = _run_script(["bash", str(SYNC), "--repo", str(src), "--url", str(origin)])
    assert proc.returncode == 2
    assert "origin remote itself" in proc.stderr


def test_end_to_end_sync_and_restore_verification(tmp_path):
    src = _init_source_repo(tmp_path / "src")
    mirror = _init_bare(tmp_path / "mirror.git")

    sync = _run_script(["bash", str(SYNC), "--repo", str(src), "--url", str(mirror)])
    assert sync.returncode == 0, sync.stderr
    assert "PASS branch=main@" in sync.stdout
    assert "tags=2" in sync.stdout
    assert "signed_tags=0/2" in sync.stdout  # honest: no release key provisioned yet

    verify = _run_script(
        [
            sys.executable,
            str(VERIFY),
            "--source",
            str(src),
            "--mirror-url",
            str(mirror),
            "--suite",
            "smoke",
        ]
    )
    assert verify.returncode == 0, verify.stderr
    fingerprint = json.loads(verify.stdout.strip().splitlines()[-1])
    assert fingerprint["result"] == "pass"
    assert fingerprint["tags"] == 2
    assert fingerprint["suite"] == "compileall-ok"
    assert fingerprint["commit"] == _git(src, "rev-parse", "refs/heads/main").strip()


def test_restore_verify_detects_missing_tag_on_mirror(tmp_path):
    src = _init_source_repo(tmp_path / "src")
    mirror = _init_bare(tmp_path / "mirror.git")
    sync = _run_script(["bash", str(SYNC), "--repo", str(src), "--url", str(mirror)])
    assert sync.returncode == 0, sync.stderr

    _git(mirror, "tag", "-d", "v9.9.9")  # operates inside the bare repo

    verify = _run_script(
        [
            sys.executable,
            str(VERIFY),
            "--source",
            str(src),
            "--mirror-url",
            str(mirror),
            "--suite",
            "none",
        ]
    )
    assert verify.returncode == 1
    assert "MISMATCH tag v9.9.9" in verify.stderr


def test_restore_verify_detects_diverged_mirror_branch(tmp_path):
    src = _init_source_repo(tmp_path / "src")
    mirror = _init_bare(tmp_path / "mirror.git")
    sync = _run_script(["bash", str(SYNC), "--repo", str(src), "--url", str(mirror)])
    assert sync.returncode == 0, sync.stderr

    # Tamper: move the mirror branch one commit ahead of the source.
    work = tmp_path / "tamper"
    _git(mirror.parent, "clone", "--quiet", str(mirror), str(work))
    _git(work, "config", "user.email", "aigeologia@gmail.com")
    _git(work, "config", "user.name", "mirror tamper")
    (work / "README.md").write_text("diverged\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "tamper commit")
    _git(work, "push", "--quiet", "origin", "main")

    verify = _run_script(
        [
            sys.executable,
            str(VERIFY),
            "--source",
            str(src),
            "--mirror-url",
            str(mirror),
            "--suite",
            "none",
        ]
    )
    assert verify.returncode == 1
    assert "MISMATCH branch main" in verify.stderr


def test_mirror_workflow_is_optional_by_secret():
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets.GEOLOGIA_MIRROR_REMOTE_URL" in body
    assert "enabled=false" in body
    assert "::notice::Mirror disabled" in body
    assert "GIT_TERMINAL_PROMPT" in body
