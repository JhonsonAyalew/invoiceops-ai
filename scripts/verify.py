import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
LOGS = ROOT / "docs" / "proof" / "logs"

PY = sys.executable
NPM = (
    shutil.which("npm.cmd") or shutil.which("npm") or r"C:\Program Files\nodejs\npm.cmd"
)
ALEMBIC_URL = f"sqlite:///{(Path(os.environ.get('TEMP', '/tmp')) / 'invoiceops-verify-migrations.db').as_posix()}"


def run(name, cmd, cwd, env=None):
    result = subprocess.run(
        cmd,
        check=False,
        cwd=cwd,
        env=env or os.environ.copy(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    label = " ".join([Path(cmd[0]).name, *(str(x) for x in cmd[1:])])
    where = cwd.relative_to(ROOT).as_posix()
    log = LOGS / f"{name}.txt"
    body = f"$ {label}\n$ cwd: {where}\n\n{result.stdout}{result.stderr}\n[exit code: {result.returncode}]\n"
    log.write_text(body, encoding="utf-8")
    print(
        f"{'PASS' if result.returncode == 0 else 'FAIL'}  {name}  ->  docs/proof/logs/{name}.txt"
    )
    return {
        "name": name,
        "command": label,
        "cwd": where,
        "exit_code": result.returncode,
        "log": f"docs/proof/logs/{name}.txt",
    }


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    checks = [
        run("backend_tests", [PY, "-m", "pytest", "-q"], BACKEND),
        run("backend_lint", [PY, "-m", "ruff", "check", "."], BACKEND),
        run("backend_format", [PY, "-m", "ruff", "format", "--check", "."], BACKEND),
        run("frontend_typecheck", [NPM, "run", "typecheck"], FRONTEND),
        run("frontend_lint", [NPM, "run", "lint"], FRONTEND),
        run("frontend_format", [NPM, "run", "format:check"], FRONTEND),
        run("frontend_build", [NPM, "run", "build"], FRONTEND),
    ]
    alembic_env = {**os.environ, "DATABASE_URL": ALEMBIC_URL}
    db = Path(alembic_env["DATABASE_URL"].split(":///", 1)[1])
    db.unlink(missing_ok=True)
    checks.append(
        run(
            "migrations_upgrade",
            [PY, "-m", "alembic", "upgrade", "head"],
            BACKEND,
            alembic_env,
        )
    )
    checks.append(
        run("migrations_check", [PY, "-m", "alembic", "check"], BACKEND, alembic_env)
    )
    checks.append(
        run(
            "migrations_downgrade",
            [PY, "-m", "alembic", "downgrade", "base"],
            BACKEND,
            alembic_env,
        )
    )

    report = {
        "verified_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "node": subprocess.run(
            ["node", "--version"], check=False, capture_output=True, text=True
        ).stdout.strip(),
        "summary": {
            "total": len(checks),
            "passed": sum(1 for c in checks if c["exit_code"] == 0),
            "failed": sum(1 for c in checks if c["exit_code"] != 0),
        },
        "checks": checks,
    }
    (LOGS / "verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
