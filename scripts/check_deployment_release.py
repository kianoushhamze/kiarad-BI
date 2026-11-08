"""Offline safety checks for deployment artifacts. Makes no external writes."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "deploy.ps1",
    "docker-compose.yml",
    "Dockerfile.backend",
    "kiarad-dashboard/Dockerfile",
    "scripts/backup_release.ps1",
    "scripts/release_health.ps1",
    "scripts/run_migrations.py",
    "migrations/0001_baseline.sql",
]
DOCKER_IGNORES = {".env", ".env.*", "secrets/", "private_exports/", "private_uploads/", "logs/", "audit-*/"}
SENSITIVE_NAMES = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "PRIVATE_KEY")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)


def candidate_files() -> list[Path]:
    result = run("git", "ls-files", "--cached", "--others", "--exclude-standard")
    if result.returncode:
        raise RuntimeError("git_file_inventory_failed")
    files = []
    for line in result.stdout.splitlines():
        path = ROOT / line.strip()
        if path.is_file() and path.stat().st_size <= 5_000_000:
            files.append(path)
    return files


def main() -> int:
    checks = []
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    checks.append({"name": "required_files", "passed": not missing, "missing": missing})

    dockerignore = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    missing_ignores = sorted(DOCKER_IGNORES - dockerignore)
    checks.append({"name": "docker_context_excludes_secrets", "passed": not missing_ignores,
                   "missing": missing_ignores})
    checks.append({"name": "docker_context_includes_migrations",
                   "passed": "!migrations/*.sql" in dockerignore})

    tracked_env = run("git", "ls-files", "--error-unmatch", ".env").returncode == 0
    checks.append({"name": "env_not_tracked", "passed": not tracked_env})

    compose = run("docker", "compose", "config", "--quiet")
    checks.append({"name": "compose_config", "passed": compose.returncode == 0})

    secret_values = []
    for name, value in dotenv_values(ROOT / ".env").items():
        if value and len(value) >= 6 and any(marker in name for marker in SENSITIVE_NAMES):
            secret_values.append((name, value.encode("utf-8")))
    leaks = []
    for path in candidate_files():
        if path.name == ".env" or path.match(".env.*"):
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        for name, value in secret_values:
            if value in content:
                leaks.append({"file": str(path.relative_to(ROOT)), "key": name})
    checks.append({"name": "no_known_secret_values_in_release_candidates", "passed": not leaks,
                   "leaks": leaks})

    migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
    checks.append({"name": "migration_files_present", "passed": bool(migrations),
                   "count": len(migrations)})

    report = {"passed": all(item["passed"] for item in checks), "checks": checks,
              "external_writes": False}
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
