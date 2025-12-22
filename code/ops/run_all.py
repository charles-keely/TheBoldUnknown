"""
Run TheBoldUnknown web apps together on a single machine.

Starts:
- Pre-Assembler   (FastAPI) on PRE_ASSEMBLER_PORT (default 8000)
- Pipeline Manager(FastAPI) on PIPELINE_PORT      (default 8001)
- Scheduler UI    (FastAPI) on SCHEDULER_PORT     (default 8002)  # default changed here to avoid 8001 conflict

This is intentionally a thin process supervisor (no external deps).
For production, you can translate these commands into systemd services.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        raise SystemExit(f"Invalid int for {name}={raw!r}")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def main() -> int:
    # Preflight: fail fast if the active Python env can't run these apps.
    try:
        import uvicorn  # noqa: F401
    except Exception as e:
        raise SystemExit(
            "Missing dependency: uvicorn is not importable in the current Python environment.\n"
            "Activate the correct venv, then rerun.\n"
            f"Import error: {e}"
        )

    repo_root = Path(__file__).resolve().parents[1]
    host = (os.getenv("TBU_HOST") or "0.0.0.0").strip()
    reload_enabled = _env_bool("TBU_RELOAD", False)

    pre_port = _env_int("PRE_ASSEMBLER_PORT", 8000)
    pipe_port = _env_int("PIPELINE_PORT", 8001)
    # Scheduler's internal default is 8001, but when running alongside pipeline_manager we default to 8002.
    sched_port = _env_int("SCHEDULER_PORT", 8002)

    # Avoid easy foot-guns.
    ports = [pre_port, pipe_port, sched_port]
    if len(set(ports)) != len(ports):
        raise SystemExit(f"Port collision detected: PRE_ASSEMBLER_PORT/PIPELINE_PORT/SCHEDULER_PORT = {ports}")

    # Ensure the package imports resolve when launched from anywhere.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    # Make sure the scheduler UI doesn't collide with pipeline_manager unless user explicitly wants it.
    env.setdefault("SCHEDULER_PORT", str(sched_port))

    def uvicorn_cmd(app: str, port: int) -> list[str]:
        cmd = [sys.executable, "-m", "uvicorn", app, "--host", host, "--port", str(port)]
        if reload_enabled:
            cmd.append("--reload")
        return cmd

    services: list[tuple[str, list[str]]] = [
        ("pre_assembler", uvicorn_cmd("pre_assembler.main:app", pre_port)),
        ("pipeline_manager", uvicorn_cmd("pipeline_manager.main:app", pipe_port)),
        ("scheduler_ui", uvicorn_cmd("scheduler.api:app", sched_port)),
    ]

    print("Starting TheBoldUnknown web apps…", flush=True)
    print(f"- Pre-Assembler:    http://localhost:{pre_port}", flush=True)
    print(f"- Pipeline Manager: http://localhost:{pipe_port}", flush=True)
    print(f"- Scheduler UI:     http://localhost:{sched_port}", flush=True)
    print("", flush=True)

    procs: list[subprocess.Popen] = []

    def terminate_all(sig: int | None = None) -> None:
        for p in procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        # Give them a moment, then hard kill anything still alive.
        deadline = time.time() + 8.0
        while time.time() < deadline and any(p.poll() is None for p in procs):
            time.sleep(0.1)
        for p in procs:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass

    def handle_signal(sig: int, _frame) -> None:  # type: ignore[no-untyped-def]
        print(f"\nReceived signal {sig}; stopping…", flush=True)
        terminate_all(sig)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        for name, cmd in services:
            print(f"[boot] {name}: {' '.join(cmd)}", flush=True)
            procs.append(subprocess.Popen(cmd, cwd=str(repo_root), env=env))

        # Monitor: if any service dies, stop everything.
        while True:
            for name, p in zip([s[0] for s in services], procs):
                rc = p.poll()
                if rc is not None:
                    print(f"[exit] {name} exited with code {rc}; stopping the rest.", flush=True)
                    terminate_all()
                    return int(rc or 1)
            time.sleep(0.5)
    finally:
        terminate_all()


if __name__ == "__main__":
    raise SystemExit(main())


